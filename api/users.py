from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from database_op.database import get_db  # Import the get_db function
import mysql.connector

users = APIRouter()

templates = Jinja2Templates(directory="templates")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Route to display the registration page
@users.get("/registration", response_class=HTMLResponse)
async def show_registration_page(request: Request):
    return templates.TemplateResponse("registration.html", {"request": request})

# Route to handle form submission
@users.post("/create-account")
async def create_account(request: Request):
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
            INSERT INTO user (email, password)
            VALUES (%s, %s)
        """
        cursor.execute(insert_query, (email, hashed_password))
        db.commit()
        cursor.close()
        db.close()
        return RedirectResponse(url="/login", status_code=303)
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
        query = "SELECT password FROM user WHERE email = %s"
        cursor.execute(query, (email,))
        result = cursor.fetchone()
        cursor.close()
        db.close()
        
        if result and pwd_context.verify(password, result['password']):
            # Authentication successful
            # Set up session or token here
            return RedirectResponse(url="/", status_code=303)
        else:
            # Authentication failed
            raise HTTPException(status_code=401, detail="Invalid email or password")
    except mysql.connector.Error as e:
        raise HTTPException(status_code=500, detail="Database error")

