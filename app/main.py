from fastapi import FastAPI, UploadFile, File, Form, Request, Depends, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from helpers.flash_utils import get_flash_message, set_flash_message
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import mysql.connector
from database_op.database import get_db
import asyncio
import json

load_dotenv()

import os
from api import converter, users, qrcode, system, feedback
from core.main_converter import conversion_progress as pdf_conversion_progress

# Create an instance of FastAPI
app = FastAPI()

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

# Mount the static folder to serve images
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../static")), name="static")

# Include the API routes
app.include_router(converter.converter)
app.include_router(users.users)
app.include_router(qrcode.qrcode) # Include the QR code router
app.include_router(system.system, prefix="/api/system")
app.include_router(feedback.feedback) # Include the feedback router

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Admin email for access control
ADMIN_EMAIL = "admin@slidepull.net"

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
    member_since = request.session['member_since']
    
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
    
    # Get additional subscription information
    cursor.execute("""
        SELECT additional_presentations, additional_storage_days, additional_sets
        FROM user
        WHERE user_id = %s
    """, (user_id,))
    additional_info = cursor.fetchone()
    
    # Calculate next billing date (1 month after member_since date)
    # This is a simplified example - in a real app, you'd track actual subscription dates
    next_billing_date = None
    if premium_status > 0:
        from datetime import datetime, timedelta
        try:
            member_since_date = datetime.strptime(member_since, "%Y-%m-%d %H:%M:%S")
            next_billing_date = (member_since_date + timedelta(days=30)).strftime("%Y-%m-%d")
        except:
            next_billing_date = "Unknown"
    
    cursor.close()

    # Render the account template with all the user data
    return templates.TemplateResponse("users/account.html", {
        "request": request,
        "user_id": user_id,
        "email": email,
        "account_activated": account_activated,
        "premium_status": premium_status,
        "member_since": member_since,
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
async def admin_dashboard(request: Request):
    """
    Admin dashboard with system monitoring and management tools.
    Only accessible to users with admin@slidepull.net email.
    """
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")
    
    # Check if the user has admin access
    if request.session['email'] != ADMIN_EMAIL:
        # Redirect non-admin users to the regular dashboard
        return RedirectResponse(url="/dashboard")
    
    # Render the admin template
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "email": request.session['email']
    })

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
    member_since = request.session['member_since']

    # Check if there's a flash message to display
    flash_message = get_flash_message(request)

    cursor = db.cursor(dictionary=True)

    # Fetch presentations and associated sets using LEFT JOIN
    cursor.execute("""
        SELECT pdf.pdf_id, pdf.original_filename, pdf.url, pdf.sas_token, pdf.sas_token_expiry AS uploaded_on,
               pdf.num_slides, pdf.file_size_kb, pdf.download_count,
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
    for row in rows:
        pdf_id = row['pdf_id']
        if pdf_id not in presentation_dict:
            # New presentation
            # Construct the full PDF URL with SAS token for direct viewing
            pdf_url_with_sas = f"{row['url']}?{row['sas_token']}"
            
            presentation = {
                'pdf_id': pdf_id,
                'original_filename': row['original_filename'],
                'url': row['url'],
                'url_with_sas': pdf_url_with_sas,
                'sas_token': row['sas_token'],
                'uploaded_on': row['uploaded_on'],
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
            # Construct the full QR code URL with SAS token
            qrcode_url_with_sas = f"{row['qrcode_url']}?{row['qrcode_sas_token']}"
            presentation['sets'].append({
                'set_id': row['set_id'],
                'name': row['set_name'],
                'qrcode_url_with_sas': qrcode_url_with_sas,
                'download_count': row['set_download_count'] or 0,
                'slide_count': row['slide_count'] or 0
            })

    cursor.close()

    # Check if the user is an admin and add admin link if they are
    is_admin = email == ADMIN_EMAIL

    # Render the dashboard template with all the user and presentation data
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user_id": user_id,
        "email": email,
        "flash_message": flash_message,
        "account_activated": account_activated,
        "premium_status": premium_status,
        "member_since": member_since,
        "presentations": presentations,  # Pass the list of presentations to the template
        "is_admin": is_admin  # Pass admin status to show/hide admin link
    })

@app.get("/download-pdf/{pdf_id}")
async def download_pdf(pdf_id: int, request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    Endpoint to download a PDF file with the proper filename.
    This adds the Content-Disposition header to force the browser to download the file
    with the original filename.
    """
    # Ensure the user is logged in
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")
    
    user_id = request.session['user_id']
    
    try:
        # Get the PDF information from the database
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT original_filename, url, sas_token
            FROM pdf
            WHERE pdf_id = %s AND user_id = %s
        """, (pdf_id, user_id))
        
        pdf_info = cursor.fetchone()
        cursor.close()
        
        if not pdf_info:
            return {"error": "PDF not found or you don't have permission to access it"}
        
        # Construct the full URL with SAS token
        pdf_url_with_sas = f"{pdf_info['url']}?{pdf_info['sas_token']}"
        
        # Create a redirect response with the Content-Disposition header
        response = RedirectResponse(url=pdf_url_with_sas)
        
        # Set the Content-Disposition header to force download with the original filename
        filename = pdf_info['original_filename']
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        return {"error": f"Failed to download PDF: {str(e)}"}
