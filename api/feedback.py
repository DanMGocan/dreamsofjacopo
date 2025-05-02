from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from database_op.database import get_db
import mysql.connector
from helpers.flash_utils import set_flash_message
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create router
feedback = APIRouter()

@feedback.post("/submit-bug-report")
async def submit_bug_report(
    request: Request,
    bug_description: str = Form(...),
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Endpoint to submit a bug report.
    
    Args:
        request: The request object
        bug_description: The description of the bug
        db: Database connection
        
    Returns:
        Redirect to dashboard with success message
    """
    # Ensure the user is logged in
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    
    user_id = request.session['user_id']
    
    try:
        # Insert the bug report into the database
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO bug_reports (user_id, bug_description, status) VALUES (%s, %s, %s)",
            (user_id, bug_description, 1)  # Status 1 = investigating
        )
        db.commit()
        cursor.close()
        
        # Redirect to dashboard with success message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Bug report submitted successfully. Thank you for your feedback!")
        return response
        
    except Exception as e:
        # If anything goes wrong, redirect with an error message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, f"Error submitting bug report: {str(e)}")
        return response

@feedback.post("/send-contact-email")
async def send_contact_email(
    request: Request,
    subject: str = Form(...),
    message: str = Form(...)
):
    """
    Endpoint to send a contact email.
    
    Args:
        request: The request object
        subject: The email subject
        message: The email message
        
    Returns:
        Redirect to dashboard with success message
    """
    # Ensure the user is logged in
    if 'user_id' not in request.session or 'email' not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    
    user_id = request.session['user_id']
    user_email = request.session['email']
    
    try:
        # Get email configuration from environment variables
        smtp_server = os.getenv("SMTP_SERVER", "smtp.example.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_username = os.getenv("SMTP_USERNAME", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        contact_email = os.getenv("CONTACT_EMAIL", "contact@slidepull.net")
        
        # Create the email
        msg = MIMEMultipart()
        msg['From'] = user_email
        msg['To'] = contact_email
        msg['Subject'] = f"[SlidePull Contact] {subject}"
        
        # Add user information to the message
        body = f"""
        Message from: {user_email} (User ID: {user_id})
        
        {message}
        """
        msg.attach(MIMEText(body, 'plain'))
        
        # Send the email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(msg)
        
        # Redirect to dashboard with success message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Your message has been sent. We'll get back to you soon!")
        return response
        
    except Exception as e:
        # If anything goes wrong, redirect with an error message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, f"Error sending message: {str(e)}")
        return response
