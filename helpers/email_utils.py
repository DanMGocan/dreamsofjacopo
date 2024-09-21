# app/email_utils.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
EMAIL_FROM = os.getenv('EMAIL_FROM', SMTP_USERNAME)
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')  # Update with your domain

def send_activation_email(email_to, token):
    activation_link = f"{BASE_URL}/activate-account/{token}"
    subject = "Activate Your Account"
    body = f"""
    <h1>Activate Your Account</h1>
    <p>Thank you for registering. Please click the link below to activate your account:</p>
    <a href="{activation_link}">Activate Account</a>
    <p>If you did not register on our site, please ignore this email.</p>
    """

    # Create message container
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = email_to

    # Record the MIME types of both parts - text/plain and text/html.
    part = MIMEText(body, 'html')

    # Attach parts into message container.
    msg.attach(part)

    try:
        # Establish connection to the SMTP server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)

        # Send the email
        server.sendmail(EMAIL_FROM, email_to, msg.as_string())
        server.quit()
        print(f"Activation email sent to {email_to}")
    except Exception as e:
        print(f"Error sending activation email: {e}")
