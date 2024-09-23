from fastapi import FastAPI, UploadFile, File, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from helpers.flash_utils import get_flash_message
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

import logging

# Example logging for debugging
logging.basicConfig(level=logging.DEBUG)
load_dotenv()

import os
from api import converter, users, qrcode

# Create an instance of FastAPI
app = FastAPI()

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
app.include_router(qrcode.qrcode)

# Initialize templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("/home.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):

    if 'email' not in request.session:
        # If no session exists, redirect to the login page
        return RedirectResponse(url="/login")

    # Get the user's email from the session
    email = request.session['email']
    user_id = request.session['user_id']
    account_activated = request.session['account_activated']

    # Check if there's a flash message to display
    flash_message = get_flash_message(request)

    return templates.TemplateResponse("dashboard.html", {"request": request, "user_id": user_id, "email": email, "flash_message": flash_message, "account_activated": account_activated})



