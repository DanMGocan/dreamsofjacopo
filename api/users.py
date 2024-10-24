from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from database_op.database import get_db  # Import the get_db function
import mysql.connector
from itsdangerous.exc import BadSignature, SignatureExpired
from itsdangerous import URLSafeSerializer

from helpers.email_utils import send_activation_email
from helpers.flash_utils import set_flash_message
from helpers.pass_utility import generate_password
from helpers.user_utils import authenticate_user

from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
import uuid

import os

from datetime import datetime

SECRET_KEY = os.getenv('SECRET_KEY')  # Ensure to set this in your .env file
serializer = URLSafeSerializer(SECRET_KEY)

users = APIRouter()

templates = Jinja2Templates(directory="templates")

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
        'scope': 'openid email',
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

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

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
        from itsdangerous import URLSafeTimedSerializer
        serializer = URLSafeTimedSerializer(os.getenv('SECRET_KEY'))
        token = serializer.dumps(user_id, salt='activate-account')

        # Send activation email in the background
        background_tasks.add_task(send_activation_email, email, token)

        # Generate activation token
        token = serializer.dumps(user_id, salt='activate-account')

        # Send activation email in the background
        # background_tasks.add_task(send_activation_email, email, token)

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
    redirect_uri = config("GOOGLE_REDIRECT_URI")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@users.get("/auth/google/callback")
async def google_auth_callback(
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    # Fetch the token from the authorization callback
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get('userinfo')

    # Extract the user's email from the userinfo
    email = userinfo.get('email')

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
                INSERT INTO user (email, password, account_activated, login_method, alias)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (email, pwd_context.hash(generate_password()), True, 'google', alias))  # Set login_method to 'google'
            db.commit()

            user_id = cursor.lastrowid  # Get the inserted user ID
            account_activated = True
            premium_status = 0  # Default to free user
            member_since = None  # Set as None, will update later if needed
            alias = alias  # Generated alias
        else:
            # User already exists, get their data
            user_id = user['user_id']
            account_activated = user['account_activated']
            premium_status = user['premium_status']
            member_since = user['member_since']
            alias = user['alias']

            # Check if the user registered with a different method
            if user['login_method'] != 'google':
                raise HTTPException(status_code=403, detail="You registered with a different login method. Please use that method to log in.")

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

# Activation endpoint
@users.get("/activate-account/{token}")
async def activate_account(request: Request, token: str):
    try:
        # Verify the token (valid for 1 hour)
        user_id = serializer.loads(token, salt='activate-account', max_age=3600)
    except SignatureExpired:
        return templates.TemplateResponse("activation_failed.html", {"request": request, "message": "Activation link expired."})
    except BadSignature:
        return templates.TemplateResponse("activation_failed.html", {"request": request, "message": "Invalid activation link."})

    # Activate the user in the database
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection error")
    
    try:
        cursor = db.cursor()
        update_query = "UPDATE user SET account_activated = %s WHERE user_id = %s"
        cursor.execute(update_query, (True, user_id))
        db.commit()
        cursor.close()
        db.close()

        # Update the session to reflect that the account is activated
        request.session['account_activated'] = True

        # Redirect to dashboard and set the flash message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Activation successful")
        return response

    except mysql.connector.Error as e:
        cursor.close()
        db.close()
        raise HTTPException(status_code=500, detail="Database error")


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