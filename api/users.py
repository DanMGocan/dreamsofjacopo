from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from database_op.database import get_db  # Import the get_db function
import mysql.connector
from itsdangerous.exc import BadSignature, SignatureExpired
from itsdangerous import URLSafeTimedSerializer

from helpers.email_utils import send_activation_email
from helpers.flash_utils import set_flash_message
from helpers.pass_utility import generate_password
from helpers.user_utils import authenticate_user

from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
import uuid
import requests # Import the requests library

import os

from datetime import datetime

SECRET_KEY = os.getenv('SECRET_KEY')  # Ensure to set this in your .env file
serializer = URLSafeTimedSerializer(SECRET_KEY)

users = APIRouter()

templates = Jinja2Templates(directory="templates")

# Get reCAPTCHA keys from environment variables
RECAPTCHA_SITE_KEY = os.getenv('RECAPTCHA_SITE_KEY')
RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY')

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Load environment variables
config = Config(".env")

# Set up OAuth
oauth = OAuth(config)

# Google OAuth configuration
oauth.register(
    name='google',
    client_id=config('GOOGLE_CLIENT_ID'),
    client_secret=config('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account',
        'access_type': 'offline'
    }
)

# Route to display the registration page
@users.get("/registration", response_class=HTMLResponse)
async def show_registration_page(request: Request):
    return templates.TemplateResponse("users/registration.html", {"request": request})

@users.post("/create-account")
async def create_account(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    form = await request.form()
    email = form.get("email")
    password = form.get("password")
    recaptcha_response = form.get("g-recaptcha-response") # Get the reCAPTCHA response

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    # Verify reCAPTCHA v3
    if not RECAPTCHA_SECRET_KEY:
        print("RECAPTCHA_SECRET_KEY not set in environment variables.")
        raise HTTPException(status_code=500, detail="Server configuration error: reCAPTCHA secret key not set.")

    if not recaptcha_response:
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")

    captcha_verify_url = "https://www.google.com/recaptcha/api/siteverify"
    captcha_data = {
        "secret": RECAPTCHA_SECRET_KEY,
        "response": recaptcha_response
    }

    try:
        response = requests.post(captcha_verify_url, data=captcha_data)
        response.raise_for_status() # Raise an exception for bad status codes
        result = response.json()

        if not result.get("success"):
            print(f"reCAPTCHA verification failed: {result.get('error-codes')}")
            raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")
        
        # For v3, also check the score (0.0 to 1.0, where 1.0 is very likely a good interaction)
        score = result.get("score", 0)
        if score < 0.5:  # You can adjust this threshold based on your needs
            print(f"reCAPTCHA score too low: {score}")
            raise HTTPException(status_code=400, detail="reCAPTCHA verification failed. Please try again.")

    except requests.exceptions.RequestException as e:
        print(f"Error verifying reCAPTCHA: {e}")
        raise HTTPException(status_code=500, detail="Error verifying reCAPTCHA. Please try again later.")


    # Hash the password
    hashed_password = pwd_context.hash(password)

    try:
        cursor = db.cursor()

        # Generate a unique alias for the user
        alias = str(uuid.uuid4())

        # Insert user with login_method as 'slide_pull' for traditional email/password signup
        insert_query = """
            INSERT INTO user (email, password, account_activated, login_method, alias, premium_status, member_since)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (email, hashed_password, False, 'slide_pull', alias, 0, datetime.now()))
        db.commit()
        user_id = cursor.lastrowid  # Get the inserted user ID

        # Generate activation token
        token = serializer.dumps(user_id, salt='activate-account')

        # Send activation email in the background
        background_tasks.add_task(send_activation_email, email, token)

        # Store user info in session and redirect to the dashboard
        request.session['user_id'] = user_id
        request.session['email'] = email
        request.session['account_activated'] = False  # Initially set to False
        request.session['login_method'] = 'slide_pull'  # Store login method in session
        request.session['premium_status'] = 0  # Default to free user
        request.session['member_since'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Convert to string for session


        # You might want to redirect the user to a 'Check your email' page
        # return RedirectResponse(url="/check-your-email", status_code=303)
        return RedirectResponse(url="/dashboard", status_code=303)

    except mysql.connector.IntegrityError as e:
        # Handle duplicate email error
        if e.errno == mysql.connector.errorcode.ER_DUP_ENTRY:
            raise HTTPException(status_code=400, detail="Email already registered")
        else:
            raise HTTPException(status_code=500, detail="Database error")
    finally:
        cursor.close()  # Ensure the cursor is closed

@users.post("/login")
async def login(
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    # Extract form data
    form = await request.form()
    email = form.get("email")
    password = form.get("password")

    # Check if both email and password are provided
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    # Authenticate the user and get the full user data
    user_data = await authenticate_user(email=email, password=password, db=db)

    # Store the entire user info (excluding password) in the session
    request.session['user_id'] = user_data['user_id']
    request.session['email'] = user_data['email']
    request.session['premium_status'] = user_data['premium_status']
    request.session['member_since'] = str(user_data['member_since'])  # Serialize datetime
    request.session['account_activated'] = user_data['account_activated']
    request.session['login_method'] = user_data['login_method']
    request.session['alias'] = user_data['alias']

    # Redirect to the dashboard after successful login
    return RedirectResponse(url="/dashboard", status_code=303)

# Google Login Endpoint
@users.get("/login/google")
async def login_via_google(request: Request):
    try:
        redirect_uri = config("GOOGLE_REDIRECT_URI")
        print(f"Google login redirect URI: {redirect_uri}")  # Debug print
        return await oauth.google.authorize_redirect(request, redirect_uri)
    except Exception as e:
        print(f"Error in Google login: {str(e)}")  # Debug print
        raise HTTPException(status_code=500, detail=f"Google OAuth error: {str(e)}")

@users.get("/auth/google/callback")
async def google_auth_callback(
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    try:
        # Fetch the token from the authorization callback
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get('userinfo')
        
        if not userinfo:
            print("No userinfo in token response")
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")

        # Extract the user's email from the userinfo
        email = userinfo.get('email')
        if not email:
            print("No email in userinfo")
            raise HTTPException(status_code=400, detail="Email not provided by Google")
            
        print(f"Successfully authenticated with Google: {email}")
    except Exception as e:
        print(f"Error in Google callback: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Google OAuth callback error: {str(e)}")

    # Open a database connection
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection error")

    try:
        cursor = db.cursor(dictionary=True)
        # Generate a unique alias for the user (if new)
        alias = str(uuid.uuid4())

        # Check if the user already exists in the database
        query = "SELECT user_id, email, account_activated, login_method, premium_status, member_since, alias FROM user WHERE email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()

        # If the user does not exist, add them to the database
        if not user:
            insert_query = """
                INSERT INTO user (email, password, account_activated, login_method, alias, premium_status, member_since)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (email, pwd_context.hash(generate_password()), True, 'google', alias, 0, datetime.now()))  # Set login_method to 'google'
            db.commit()

            user_id = cursor.lastrowid  # Get the inserted user ID
            account_activated = True
            premium_status = 0  # Default to free user
            member_since = datetime.now()  # Set current time
            alias = alias  # Generated alias
        else:
            # User already exists, get their data
            user_id = user['user_id']
            premium_status = user['premium_status']
            member_since = user['member_since']
            alias = user['alias']

            # Check if the user registered with a different method
            if user['login_method'] != 'google':
                raise HTTPException(status_code=403, detail="You registered with a different login method. Please use that method to log in.")
            
            # Ensure account is activated for Google login users
            if not user['account_activated']:
                # Update account_activated to True for Google login users
                update_query = "UPDATE user SET account_activated = %s WHERE user_id = %s"
                cursor.execute(update_query, (True, user_id))
                db.commit()
            
            # Always set account_activated to True for Google login
            account_activated = True

        cursor.close()

        # Store user info in the session
        request.session['user_id'] = user_id
        request.session['email'] = email
        request.session['account_activated'] = account_activated
        request.session['login_method'] = 'google'
        request.session['premium_status'] = premium_status
        request.session['member_since'] = str(member_since) if member_since else None
        request.session['alias'] = alias

        # Redirect to the dashboard
        return RedirectResponse(url="/dashboard", status_code=303)

    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail="Database error")


# Route to handle logout
@users.get("/logout")
async def logout(request: Request, response: Response):
    # Clear the session by popping all session keys
    request.session.clear()

    # Redirect to the login page after logout
    return RedirectResponse(url="/")

# Route to display the upgrade page
@users.get("/upgrade", response_class=HTMLResponse)
async def show_upgrade_page(
    request: Request,
    downgrade: str = None,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    # Ensure the user is logged in
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")
    
    # Get user's current premium status
    premium_status = request.session.get('premium_status', 0)
    user_id = request.session.get('user_id')
    
    # Check if this is a downgrade request
    if downgrade is not None:
        try:
            # Convert downgrade parameter to int
            target_tier = int(downgrade)
            
            # Import the check_downgrade_eligibility function
            from helpers.subscription_utils import check_downgrade_eligibility
            
            # Check if the user is eligible to downgrade
            eligible, message = check_downgrade_eligibility(user_id, target_tier, db)
            
            if eligible:
                # Update the user's premium status in the database
                cursor = db.cursor()
                update_query = "UPDATE user SET premium_status = %s WHERE user_id = %s"
                cursor.execute(update_query, (target_tier, user_id))
                db.commit()
                cursor.close()
                
                # Update the session
                request.session['premium_status'] = target_tier
                
                # Redirect to the dashboard with a success message
                response = RedirectResponse(url="/dashboard", status_code=303)
                set_flash_message(response, "Your account has been downgraded successfully.")
                return response
            else:
                # Redirect to the account page with an error message
                response = RedirectResponse(url="/account", status_code=303)
                set_flash_message(response, f"Cannot downgrade: {message}")
                return response
        except Exception as e:
            # If anything goes wrong, redirect with an error message
            response = RedirectResponse(url="/account", status_code=303)
            set_flash_message(response, f"Error processing downgrade: {str(e)}")
            return response
    
    # Get next billing date if the user has a premium subscription
    next_billing_date = None
    if premium_status > 0:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT member_since FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        
        if user_data and 'member_since' in user_data:
            from datetime import datetime, timedelta
            try:
                member_since = user_data['member_since']
                member_since_date = datetime.strptime(str(member_since), "%Y-%m-%d %H:%M:%S")
                next_billing_date = (member_since_date + timedelta(days=30)).strftime("%Y-%m-%d")
            except:
                next_billing_date = "Unknown"
    
    # If not a downgrade request, show the upgrade page
    return templates.TemplateResponse("users/upgrade.html", {
        "request": request, 
        "premium_status": premium_status,
        "next_billing_date": next_billing_date
    })

# Activation endpoint (handles both GET and POST)
@users.api_route("/activate-account/{token}", methods=["GET", "POST"])
async def activate_account(
    request: Request, 
    token: str,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    try:
        # Verify the token (valid for 1 hour)
        user_id = serializer.loads(token, salt='activate-account', max_age=3600)
    except SignatureExpired:
        return templates.TemplateResponse("users/activation_failed.html", {"request": request, "message": "Activation link expired."})
    except BadSignature:
        return templates.TemplateResponse("users/activation_failed.html", {"request": request, "message": "Invalid activation link."})

    # Activate the user in the database
    try:
        cursor = db.cursor()
        update_query = "UPDATE user SET account_activated = %s WHERE user_id = %s"
        cursor.execute(update_query, (True, user_id))
        db.commit()
        cursor.close()

        # Update the session to reflect that the account is activated
        request.session['account_activated'] = True

        # Redirect to dashboard and set the flash message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Activation successful")
        return response

    except mysql.connector.Error as e:
        if 'cursor' in locals() and cursor:
            cursor.close()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@users.post("/resend-activation")
async def resend_activation(request: Request, background_tasks: BackgroundTasks):
    user_email = request.session['email']
    if not user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Fetch user data from the session
    user_id = request.session['user_id']
    email = request.session['email']

    # Generate a new activation token
    token = serializer.dumps(user_id, salt='activate-account')

    # Send the activation email in the background
    background_tasks.add_task(send_activation_email, email, token)

    # Redirect to the dashboard with a flash message
    response = RedirectResponse(url="/dashboard", status_code=303)
    set_flash_message(response, "Activation email resent successfully")
    return response

@users.post("/process-upgrade")
async def process_upgrade(
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Process the upgrade form submission.
    In a real implementation, this would integrate with a payment processor.
    For now, we'll just update the user's premium status in the database.
    """
    # Ensure the user is logged in
    if 'user_id' not in request.session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = request.session['user_id']
    
    try:
        # Get form data
        form = await request.form()
        
        # Check if a plan was selected (this would come from radio buttons in a real form)
        selected_plan = form.get("selected_plan", "0")  # Default to free plan
        
        # Get à la carte options
        additional_presentations = int(form.get("additional_presentations", "0"))
        additional_storage_days = int(form.get("additional_storage_days", "0"))
        additional_sets = int(form.get("additional_sets", "0"))
        
        # Convert selected_plan to an integer
        premium_status = int(selected_plan)
        
        # Update the user's premium status in the database
        cursor = db.cursor()
        update_query = """
            UPDATE user 
            SET premium_status = %s,
                additional_presentations = %s,
                additional_storage_days = %s,
                additional_sets = %s
            WHERE user_id = %s
        """
        
        # In a real implementation, we would check if these columns exist first
        # For now, we'll assume they do or handle the error
        try:
            cursor.execute(update_query, (
                premium_status,
                additional_presentations,
                additional_storage_days,
                additional_sets,
                user_id
            ))
            db.commit()
        except mysql.connector.Error as e:
            # If the columns don't exist, we'll need to alter the table
            if "Unknown column" in str(e):
                # Add the columns if they don't exist
                alter_query = """
                    ALTER TABLE user
                    ADD COLUMN additional_presentations INT DEFAULT 0,
                    ADD COLUMN additional_storage_days INT DEFAULT 0,
                    ADD COLUMN additional_sets INT DEFAULT 0
                """
                cursor.execute(alter_query)
                db.commit()
                
                # Try the update again
                cursor.execute(update_query, (
                    premium_status,
                    additional_presentations,
                    additional_storage_days,
                    additional_sets,
                    user_id
                ))
                db.commit()
            else:
                # If it's a different error, re-raise it
                raise
        
        # Update the session
        request.session['premium_status'] = premium_status
        
        # Redirect to the dashboard with a success message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Your account has been upgraded successfully!")
        return response
        
    except Exception as e:
        # If anything goes wrong, redirect with an error message
        response = RedirectResponse(url="/upgrade", status_code=303)
        set_flash_message(response, f"Error processing upgrade: {str(e)}")
        return response
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
