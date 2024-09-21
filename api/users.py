from fastapi import APIRouter, Request, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from database_op.database import get_db  # Import the get_db function
from core.session import create_session, get_session, clear_session, get_current_user
from helpers.activation import generate_activation_token, verify_activation_token
import mysql.connector
from itsdangerous.exc import BadSignature, SignatureExpired
from itsdangerous import URLSafeTimedSerializer, URLSafeSerializer

import os

SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')  # Ensure to set this in your .env file
serializer = URLSafeSerializer(SECRET_KEY)


users = APIRouter()

templates = Jinja2Templates(directory="templates")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Route to display the registration page
@users.get("/registration", response_class=HTMLResponse)
async def show_registration_page(request: Request):
    return templates.TemplateResponse("registration.html", {"request": request})

# Route to handle registration
@users.post("/create-account")
async def create_account(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    email = form.get("email")
    password = form.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    # Hash the password
    hashed_password = pwd_context.hash(password)

    # Insert the user into the database
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection error")

    try:
        cursor = db.cursor()
        insert_query = """
            INSERT INTO user (email, password, account_activated)
            VALUES (%s, %s, %s)
        """
        cursor.execute(insert_query, (email, hashed_password, False))  # Set account_activated to False
        db.commit()
        user_id = cursor.lastrowid  # Get the inserted user ID
        cursor.close()
        db.close()

        # Generate activation token
        token = serializer.dumps(user_id, salt='activate-account')

        # Send activation email in the background
        background_tasks.add_task(send_activation_email, email, token)

        return templates.TemplateResponse("activation_sent.html", {"request": request, "email": email})
    except mysql.connector.IntegrityError as e:
        # Handle duplicate email error
        if e.errno == mysql.connector.errorcode.ER_DUP_ENTRY:
            cursor.close()
            db.close()
            raise HTTPException(status_code=400, detail="Email already registered")
        else:
            cursor.close()
            db.close()
            raise HTTPException(status_code=500, detail="Database error")

        
@users.get("/login", response_class=HTMLResponse)
async def show_login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@users.post("/login")
async def login(request: Request):
    form = await request.form()
    email = form.get("email")
    password = form.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection error")

    try:
        cursor = db.cursor(dictionary=True)
        query = "SELECT user_id, password, account_activated FROM user WHERE email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and pwd_context.verify(password, user['password']):
            if not user['account_activated']:
                raise HTTPException(status_code=403, detail="Account not activated")

            response = RedirectResponse(url="/dashboard", status_code=303)
            # Create session
            create_session(response, {"user_id": user['user_id'], "email": email})
            return response
        else:
            raise HTTPException(status_code=401, detail="Invalid email or password")
    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail="Database error")

# Route to handle logout
@users.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    clear_session(response)
    return response

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

        return templates.TemplateResponse("activation_success.html", {"request": request})
    except mysql.connector.Error as e:
        cursor.close()
        db.close()
        raise HTTPException(status_code=500, detail="Database error")
