import logging
from fastapi import FastAPI, UploadFile, File, Form, Request, Depends, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool # Import for running sync code in thread pool
from helpers.flash_utils import get_flash_message, set_flash_message
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import mysql.connector
from database_op.database import get_db
import asyncio
import json
from datetime import datetime, timezone
from helpers.blob_op import refresh_sas_token_if_needed

load_dotenv()

import os
from api import converter, users, qrcode, system, feedback, secure_links
from core.main_converter import conversion_progress as pdf_conversion_progress

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("server.log"),
                        logging.StreamHandler()
                    ])

# Create an instance of FastAPI with custom 404 handler
app = FastAPI(docs_url=None, redoc_url=None)

# Add reCAPTCHA site key to app state for use in templates
app.state.RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY')

# Custom exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    Custom handler for HTTP exceptions to provide a better user experience.
    """
    # Check if this is a file size limit error (status code 413)
    if exc.status_code == 413:
        # Redirect to dashboard with a flash message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, exc.detail)
        return response
    
    # Handle 404 errors with our custom template
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    
    # For other HTTP exceptions, use the default handler
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY"),
    max_age=3600,  # Session lifetime in seconds
    same_site="Lax",  # Adjust depending on your needs
    # https_only=True  # Use only if you are using HTTPS
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logging.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logging.info(f"Outgoing response: {response.status_code}")
    return response

# Mount the static folder to serve images
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../static")), name="static")

# Include the API routes
app.include_router(converter.converter)
app.include_router(users.users)
app.include_router(qrcode.qrcode) # Include the QR code router
app.include_router(system.system, prefix="/api/system")
app.include_router(feedback.feedback) # Include the feedback router
app.include_router(secure_links.secure_links) # Include the secure links router

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Override default 404 handler
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

# Admin emails for access control
ADMIN_EMAILS = ["admin@slidepull.net", "colm@tud.ie"]

# Progress tracking is now handled client-side with a simple animation

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # If user is already logged in, redirect to dashboard
    if 'email' in request.session and 'user_id' in request.session:
        return RedirectResponse(url="/dashboard")
    
    # Otherwise show the login/home page
    return templates.TemplateResponse("/home.html", {"request": request})

@app.get("/how-it-works", response_class=HTMLResponse)
async def how_it_works(request: Request):
    # Show the "How it works?" page
    return templates.TemplateResponse("how_it_works.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request):
    # Show the Privacy Policy page
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/terms", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    # Show the Terms of Service page
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    # Show the About page
    return templates.TemplateResponse("about.html", {"request": request})

# Removed /development route

@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    User account page showing account information and usage statistics.
    """
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")

    # Get user session details
    email = request.session['email']
    user_id = request.session['user_id']
    account_activated = request.session['account_activated']
    premium_status = request.session['premium_status']
    
    member_since_str = request.session.get('member_since')
    formatted_member_since = 'N/A'
    if member_since_str:
        try:
            dt_member_since = datetime.strptime(member_since_str, '%Y-%m-%d %H:%M:%S')
            formatted_member_since = dt_member_since.strftime('%d/%m/%Y')
        except ValueError:
            logging.warning(f"Could not parse member_since string for /account: {member_since_str}")
            formatted_member_since = member_since_str

    # Get login method from database
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT login_method FROM user WHERE user_id = %s", (user_id,))
    user_data = cursor.fetchone()
    login_method = user_data['login_method'] if user_data else "slide_pull"

    cursor = db.cursor(dictionary=True)

    # Fetch presentations
    cursor.execute("""
        SELECT pdf_id FROM pdf WHERE user_id = %s
    """, (user_id,))
    presentations = cursor.fetchall()

    # Count sets
    cursor.execute("""
        SELECT COUNT(*) as count FROM `set` WHERE user_id = %s
    """, (user_id,))
    sets_result = cursor.fetchone()
    sets_count = sets_result['count'] if sets_result else 0

    # Calculate total downloads (PDF presentations + sets)
    cursor.execute("""
        SELECT COALESCE(SUM(download_count), 0) as pdf_downloads 
        FROM pdf 
        WHERE user_id = %s
    """, (user_id,))
    pdf_downloads_result = cursor.fetchone()
    pdf_downloads = pdf_downloads_result['pdf_downloads'] if pdf_downloads_result else 0

    cursor.execute("""
        SELECT COALESCE(SUM(download_count), 0) as set_downloads 
        FROM `set` 
        WHERE user_id = %s
    """, (user_id,))
    set_downloads_result = cursor.fetchone()
    set_downloads = set_downloads_result['set_downloads'] if set_downloads_result else 0

    total_downloads = pdf_downloads + set_downloads
    
    # Removed query for additional_presentations, additional_storage_days, additional_sets
    # as these columns no longer exist in the user table.
    # additional_info = None 
    
    # Calculate next billing date (1 month after member_since date)
    # This is a simplified example - in a real app, you'd track actual subscription dates
    next_billing_date = None
    if premium_status > 0:
        from datetime import timedelta # Import only timedelta, datetime is global
        try:
            if member_since_str: # Check if member_since_str (original string from session) exists
                # Use the globally imported datetime module
                member_since_date_obj = datetime.strptime(member_since_str, "%Y-%m-%d %H:%M:%S")
                next_billing_date = (member_since_date_obj + timedelta(days=30)).strftime("%Y-%m-%d")
            else:
                next_billing_date = "N/A" 
        except ValueError as e: # Catch specific parsing errors
            logging.error(f"Error calculating next_billing_date due to date parsing: {e}")
            next_billing_date = "Unknown"
        except Exception as e: # Catch other potential errors
            logging.error(f"Unexpected error calculating next_billing_date: {e}")
            next_billing_date = "Unknown"
    
    cursor.close()

    # Render the account template with all the user data
    return templates.TemplateResponse("users/account.html", {
        "request": request,
        "user_id": user_id,
        "email": email,
        "account_activated": account_activated,
        "premium_status": premium_status,
        "member_since": formatted_member_since, # Use formatted date
        "login_method": login_method,
        "presentations": presentations,
        "sets_count": sets_count,
        "total_downloads": total_downloads,
        "pdf_downloads": pdf_downloads,
        "set_downloads": set_downloads,
        "next_billing_date": next_billing_date
    })

@app.post("/activate-account")
async def activate_account(request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    Sends an activation email to the user's registered email address.
    """
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")
    
    email = request.session['email']
    user_id = request.session['user_id']
    
    # Import the send_activation_email function
    from helpers.email_utils import send_activation_email
    
    # Generate and send activation email
    try:
        send_activation_email(email, user_id, db)
        response = RedirectResponse(url="/account", status_code=303)
        set_flash_message(response, "Activation email sent successfully! Please check your inbox.")
        return response
    except Exception as e:
        response = RedirectResponse(url="/account", status_code=303)
        set_flash_message(response, f"Error sending activation email: {str(e)}")
        return response

@app.post("/change-password")
async def change_password(
    request: Request, 
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Changes the user's password if the current password is correct.
    """
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")
    
    email = request.session['email']
    user_id = request.session['user_id']
    
    # Import password utility functions
    from helpers.pass_utility import verify_password, hash_password
    
    cursor = db.cursor(dictionary=True)
    
    try:
        # Get the current hashed password from the database
        cursor.execute("SELECT password FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            response = RedirectResponse(url="/account", status_code=303)
            set_flash_message(response, "User not found.")
            return response
        
        stored_password = user_data['password']
        
        # Verify the current password
        if not verify_password(current_password, stored_password):
            response = RedirectResponse(url="/account", status_code=303)
            set_flash_message(response, "Current password is incorrect.")
            return response
        
        # Hash the new password
        hashed_new_password = hash_password(new_password)
        
        # Update the password in the database
        cursor.execute(
            "UPDATE user SET password = %s WHERE user_id = %s",
            (hashed_new_password, user_id)
        )
        db.commit()
        
        response = RedirectResponse(url="/account", status_code=303)
        set_flash_message(response, "Password changed successfully!")
        return response
        
    except Exception as e:
        response = RedirectResponse(url="/account", status_code=303)
        set_flash_message(response, f"Error changing password: {str(e)}")
        return response
    finally:
        cursor.close()

from helpers.subscription_utils import check_downgrade_eligibility

@app.get("/check-downgrade-eligibility/{target_tier}")
async def check_downgrade_eligibility_endpoint(
    target_tier: int,
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    API endpoint to check if a user is eligible to downgrade to a lower tier.
    """
    # Ensure the user is logged in
    if 'email' not in request.session:
        return {"eligible": False, "message": "You must be logged in to perform this action."}
    
    user_id = request.session['user_id']
    
    # Check eligibility
    eligible, message = check_downgrade_eligibility(user_id, target_tier, db)
    
    return {"eligible": eligible, "message": message}

@app.post("/cancel-subscription")
async def cancel_subscription(request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    Cancels the user's subscription.
    """
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")
    
    user_id = request.session['user_id']
    premium_status = request.session['premium_status']
    
    # Check if the user is eligible to downgrade to free tier
    from helpers.subscription_utils import check_downgrade_eligibility
    eligible, message = check_downgrade_eligibility(user_id, 0, db)
    if not eligible:
        response = RedirectResponse(url="/account", status_code=303)
        set_flash_message(response, f"Cannot cancel subscription: {message}")
        return response
    
    cursor = db.cursor()
    
    try:
        # In a real application, you would also need to cancel the subscription with your payment processor
        # Here we're just updating the database
        
        # Update the user's premium status to free (0)
        cursor.execute(
            "UPDATE user SET premium_status = 0 WHERE user_id = %s",
            (user_id,)
        )
        db.commit()
        
        # Update the session to reflect the change
        request.session['premium_status'] = 0
        
        response = RedirectResponse(url="/account", status_code=303)
        set_flash_message(response, "Your subscription has been cancelled. You will have access to premium features until the end of your current billing period.")
        return response
        
    except Exception as e:
        response = RedirectResponse(url="/account", status_code=303)
        set_flash_message(response, f"Error cancelling subscription: {str(e)}")
        return response
    finally:
        cursor.close()

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    Admin dashboard with system monitoring and management tools.
    Only accessible to users with admin@slidepull.net email.
    """
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")
    
    # Check if the user has admin access
    if request.session['email'] not in ADMIN_EMAILS:
        # Redirect non-admin users to the regular dashboard
        return RedirectResponse(url="/dashboard")
    
    # Fetch conversion statistics
    conversion_stats_data = []
    try:
        def sync_fetch_conversion_stats(conn: mysql.connector.connection.MySQLConnection):
            # This function runs in a separate thread
            _cursor = conn.cursor(dictionary=True)
            _cursor.execute("""
                SELECT 
                    cs.stat_id,
                    u.email as user_email,
                    p.original_filename,
                    cs.upload_size_kb,
                    cs.num_slides,
                    cs.conversion_duration_seconds,
                    cs.created_at
                FROM conversion_stats cs
                JOIN user u ON cs.user_id = u.user_id
                JOIN pdf p ON cs.pdf_id = p.pdf_id
                ORDER BY cs.created_at DESC
                LIMIT 50 
            """) # Limit to last 50 for display
            _data = _cursor.fetchall()
            _cursor.close()
            return _data

        conversion_stats_data = await run_in_threadpool(sync_fetch_conversion_stats, db)
    except Exception as e:
        logging.error(f"Error fetching conversion stats for admin page: {e}")
        # Continue without stats if there's an error

    # Render the admin template
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "email": request.session['email'],
        "conversion_stats": conversion_stats_data
    })

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """
    Admin logs page showing the last 250 log entries.
    Only accessible to users with admin@slidepull.net email.
    """
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")

    # Check if the user has admin access
    if request.session['email'] not in ADMIN_EMAILS:
        # Redirect non-admin users to the regular dashboard
        return RedirectResponse(url="/dashboard")

    log_entries = []
    try:
        with open("server.log", "r") as f:
            # Read all lines and get the last 250
            lines = f.readlines()
            last_250_lines = lines[-250:]

            for line in last_250_lines:
                # Assuming log format is 'YYYY-MM-DD HH:MM:SS,ms - name - level - message'
                parts = line.split(' - ', 3)
                if len(parts) == 4:
                    timestamp = parts[0]
                    message = parts[3].strip()
                    log_entries.append({"timestamp": timestamp, "message": message})
                else:
                    # Handle lines that don't match the expected format
                    log_entries.append({"timestamp": "N/A", "message": line.strip()})

    except FileNotFoundError:
        log_entries.append({"timestamp": "N/A", "message": "Log file not found."})
    except Exception as e:
        log_entries.append({"timestamp": "N/A", "message": f"Error reading log file: {str(e)}"})

    return templates.TemplateResponse("admin/logs.html", {"request": request, "log_entries": log_entries})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")

    # Get user session details
    email = request.session['email']
    user_id = request.session['user_id']
    account_activated = request.session['account_activated']
    premium_status = request.session['premium_status']
    
    member_since_str = request.session.get('member_since')
    formatted_member_since = 'N/A'
    if member_since_str:
        try:
            # Assuming member_since_str is in 'YYYY-MM-DD HH:MM:SS' format from session
            dt_member_since = datetime.strptime(member_since_str, '%Y-%m-%d %H:%M:%S')
            formatted_member_since = dt_member_since.strftime('%d/%m/%Y')
        except ValueError:
            # If parsing fails, use the original string or a default
            logging.warning(f"Could not parse member_since string: {member_since_str}")
            formatted_member_since = member_since_str # Fallback or keep 'N/A'

    # Check if there's a flash message to display
    flash_message = get_flash_message(request)

    cursor = db.cursor(dictionary=True)
    
    # Get the user's alias (needed for token refresh)
    cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
    user_data = cursor.fetchone()
    if not user_data or 'alias' not in user_data:
        logging.error(f"Couldn't find alias for user {user_id}")
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "user_id": user_id,
            "email": email,
            "flash_message": "Error loading user data. Please contact support.",
            "account_activated": account_activated,
            "premium_status": premium_status,
            "member_since": formatted_member_since, # Use formatted date
            "presentations": [],
            "is_admin": email in ADMIN_EMAILS
        })
    
    user_alias = user_data['alias']

    # Fetch presentations and associated sets using LEFT JOIN, including PDF QR code info
    cursor.execute("""
        SELECT pdf.pdf_id, pdf.original_filename, pdf.url, pdf.sas_token, pdf.sas_token_expiry AS uploaded_on,
               pdf.num_slides, pdf.file_size_kb, pdf.download_count,
               pdf.pdf_qrcode_url, pdf.pdf_qrcode_sas_token, pdf.pdf_qrcode_sas_token_expiry,
               `set`.set_id, `set`.name AS set_name, `set`.qrcode_url, `set`.qrcode_sas_token,
               `set`.download_count AS set_download_count, `set`.slide_count
        FROM pdf
        LEFT JOIN `set` ON pdf.pdf_id = `set`.pdf_id
        WHERE pdf.user_id = %s
        ORDER BY pdf.pdf_id
    """, (user_id,))

    rows = cursor.fetchall()

    # Organize data into presentations with their sets
    presentations = []
    presentation_dict = {}
    update_cursor = None
    
    try:
        update_cursor = db.cursor()
        
        for row in rows:
            pdf_id = row['pdf_id']
            if pdf_id not in presentation_dict:
                # New presentation
                # Check if the SAS token is expired and refresh if needed
                current_sas_token = row['sas_token']
                sas_token_expiry = row['uploaded_on']  # This is actually the sas_token_expiry
                original_filename = row['original_filename']
                
                # Extract the file path from the URL
                url_parts = row['url'].split('/')
                file_path = '/'.join(url_parts[4:])  # Skip the protocol and domain parts
                
                # Check if token is expired and refresh if needed
                # Ensure both datetimes are timezone-aware before comparison
                current_time = datetime.now(timezone.utc)
                
                # If sas_token_expiry is naive (has no timezone), assume it's in UTC
                if sas_token_expiry is not None and sas_token_expiry.tzinfo is None:
                    sas_token_expiry = sas_token_expiry.replace(tzinfo=timezone.utc)
                
                if sas_token_expiry is None or current_time >= sas_token_expiry:
                    logging.info(f"Refreshing expired SAS token for PDF {pdf_id}")
                    new_token, new_expiry = refresh_sas_token_if_needed(
                        alias=user_alias,
                        file_path=file_path,
                        current_sas_token=current_sas_token,
                        sas_token_expiry=sas_token_expiry
                    )
                    
                    # Update the database with the new token
                    update_cursor.execute(
                        "UPDATE pdf SET sas_token = %s, sas_token_expiry = %s WHERE pdf_id = %s",
                        (new_token, new_expiry, pdf_id)
                    )
                    db.commit()
                    
                    # Use the new token
                    pdf_url_with_sas = f"{row['url']}?{new_token}"
                    current_sas_token = new_token
                else:
                    # Token is still valid, use the existing one
                    pdf_url_with_sas = f"{row['url']}?{current_sas_token}"
                
                presentation = {
                    'pdf_id': pdf_id,
                    'original_filename': original_filename,
                    'url': row['url'],
                    'url_with_sas': pdf_url_with_sas,
                    'sas_token': current_sas_token,
                    'uploaded_on': sas_token_expiry,
                    'num_slides': row['num_slides'],
                    'file_size_kb': row['file_size_kb'],
                    'download_count': row['download_count'] or 0,
                    'sets': []
                }
                presentation_dict[pdf_id] = presentation
                presentations.append(presentation)
            else:
                presentation = presentation_dict[pdf_id]

            # Add set if it exists
            if row['set_id'] is not None:
                set_id = row['set_id']
                set_name = row['set_name']
                qrcode_url = row['qrcode_url']
                qrcode_sas_token = row['qrcode_sas_token']
                
                # Check if the QR code SAS token needs to be refreshed
                # We would need to query the set table to get the expiry date
                # For now, we'll assume it might be expired and refresh it
                
                # Extract the file path from the URL
                if qrcode_url:
                    url_parts = qrcode_url.split('/')
                    qr_file_path = '/'.join(url_parts[4:])  # Skip the protocol and domain parts
                    
                    # Refresh the QR code SAS token
                    new_qr_token, new_qr_expiry = refresh_sas_token_if_needed(
                        alias=user_alias,
                        file_path=qr_file_path,
                        current_sas_token=qrcode_sas_token
                    )
                    
                    # Update the database with the new token if it changed
                    if new_qr_token != qrcode_sas_token:
                        logging.info(f"Refreshing expired SAS token for QR code of set {set_id}")
                        update_cursor.execute(
                            "UPDATE `set` SET qrcode_sas_token = %s, qrcode_sas_token_expiry = %s WHERE set_id = %s",
                            (new_qr_token, new_qr_expiry, set_id)
                        )
                        db.commit()
                        qrcode_sas_token = new_qr_token
                    
                    # Construct the full QR code URL with SAS token
                    qrcode_url_with_sas = f"{qrcode_url}?{qrcode_sas_token}"
                    
                    presentation['sets'].append({
                        'set_id': set_id,
                        'name': set_name,
                        'qrcode_url_with_sas': qrcode_url_with_sas,
                        'download_count': row['set_download_count'] or 0,
                        'slide_count': row['slide_count'] or 0
                    })
    finally:
        if update_cursor:
            update_cursor.close()

    cursor.close()

    # Check if the user is an admin and add admin link if they are
    is_admin = email in ADMIN_EMAILS

    # Render the dashboard template with all the user and presentation data
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user_id": user_id,
        "email": email,
        "flash_message": flash_message,
        "account_activated": account_activated,
        "premium_status": premium_status,
        "member_since": formatted_member_since, # Use formatted date
        "presentations": presentations,  # Pass the list of presentations to the template
        "is_admin": is_admin  # Pass admin status to show/hide admin link
    })

@app.get("/download-pdf/{pdf_id}")
async def download_pdf(pdf_id: int, request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    Endpoint to download a PDF file with the proper filename.
    This adds the Content-Disposition header to force the browser to download the file
    with the original filename.
    
    This endpoint also checks if the SAS token is expired and refreshes it if needed.
    """
    # Ensure the user is logged in
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")
    
    user_id = request.session['user_id']
    
    try:
        # Get the PDF information from the database
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT original_filename, url, sas_token, sas_token_expiry
            FROM pdf
            WHERE pdf_id = %s AND user_id = %s
        """, (pdf_id, user_id))
        
        pdf_info = cursor.fetchone()
        
        if not pdf_info:
            cursor.close()
            return {"error": "PDF not found or you don't have permission to access it"}
        
        # Get the user's alias (needed for token refresh)
        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        
        if not user_data or 'alias' not in user_data:
            logging.error(f"Couldn't find alias for user {user_id}")
            return {"error": "User data not found. Please contact support."}
        
        user_alias = user_data['alias']
        
        # Check if the SAS token is expired and refresh if needed
        current_sas_token = pdf_info['sas_token']
        sas_token_expiry = pdf_info['sas_token_expiry']
        
        # Extract the file path from the URL
        url_parts = pdf_info['url'].split('/')
        file_path = '/'.join(url_parts[4:])  # Skip the protocol and domain parts
        
        # Check if token is expired and refresh if needed
        # Ensure both datetimes are timezone-aware before comparison
        current_time = datetime.now(timezone.utc)
        
        # If sas_token_expiry is naive (has no timezone), assume it's in UTC
        if sas_token_expiry is not None and sas_token_expiry.tzinfo is None:
            sas_token_expiry = sas_token_expiry.replace(tzinfo=timezone.utc)
        
        if sas_token_expiry is None or current_time >= sas_token_expiry:
            logging.info(f"Refreshing expired SAS token for PDF {pdf_id} during download")
            new_token, new_expiry = refresh_sas_token_if_needed(
                alias=user_alias,
                file_path=file_path,
                current_sas_token=current_sas_token,
                sas_token_expiry=sas_token_expiry
            )
            
            # Update the database with the new token
            update_cursor = db.cursor()
            update_cursor.execute(
                "UPDATE pdf SET sas_token = %s, sas_token_expiry = %s WHERE pdf_id = %s",
                (new_token, new_expiry, pdf_id)
            )
            db.commit()
            update_cursor.close()
            
            # Use the new token
            pdf_url_with_sas = f"{pdf_info['url']}?{new_token}"
        else:
            # Token is still valid, use the existing one
            pdf_url_with_sas = f"{pdf_info['url']}?{current_sas_token}"
        
        # Create a redirect response with the Content-Disposition header
        response = RedirectResponse(url=pdf_url_with_sas)
        
        # Set the Content-Disposition header to force download with the original filename
        filename = pdf_info['original_filename']
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        return {"error": f"Failed to download PDF: {str(e)}"}
