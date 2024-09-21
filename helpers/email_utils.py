# app/email_utils.py
from fastapi import Request

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv


import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Load environment variables from the .env file
load_dotenv()

# Google OAuth variables from .env file
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_PROJECT_ID = os.getenv('GOOGLE_PROJECT_ID')
GOOGLE_AUTH_URI = os.getenv('GOOGLE_AUTH_URI')
GOOGLE_TOKEN_URI = os.getenv('GOOGLE_TOKEN_URI')
GOOGLE_AUTH_PROVIDER_CERT_URL = os.getenv('GOOGLE_AUTH_PROVIDER_CERT_URL')
GOOGLE_REDIRECT_URIS = os.getenv('GOOGLE_REDIRECT_URIS').split(',')

# Create a dictionary to mimic the structure of the previous gsecret.json
GOOGLE_CREDENTIALS = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "project_id": GOOGLE_PROJECT_ID,
        "auth_uri": GOOGLE_AUTH_URI,
        "token_uri": GOOGLE_TOKEN_URI,
        "auth_provider_x509_cert_url": GOOGLE_AUTH_PROVIDER_CERT_URL,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uris": GOOGLE_REDIRECT_URIS,
    }
}

# Scopes required to send emails
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Example of how to use these credentials when initializing the InstalledAppFlow
from google_auth_oauthlib.flow import InstalledAppFlow

def get_gmail_service():
    creds = None
    token_file = 'token.json'

    # Load existing credentials from token file
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # If no valid credentials are available, initiate the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Use the credentials dictionary instead of a JSON file
            flow = InstalledAppFlow.from_client_config(GOOGLE_CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=8080)

        # Save the credentials for future use
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    return service

def send_activation_email(email_to, token):
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
    activation_link = f"{BASE_URL}/activate-account/{token}"
    subject = "Activate Your Account"
    body = f"""
    <h1>Activate Your Account</h1>
    <p>Thank you for registering. Please click the link below to activate your account:</p>
    <a href="{activation_link}">Activate Account</a>
    <p>If you did not register on our site, please ignore this email.</p>
    """

    # Create the email message
    message = MIMEText(body, 'html')
    message['to'] = email_to
    message['subject'] = subject

    # Encode the message
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        service = get_gmail_service()
        send_message = {'raw': raw_message}
        service.users().messages().send(userId='me', body=send_message).execute()
        print(f"Activation email sent to {email_to}")
    except Exception as e:
        print(f"Error sending activation email: {e}")

