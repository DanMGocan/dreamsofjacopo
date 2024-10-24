# app/email_utils.py
from fastapi import Request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
from mailjet_rest import Client

# Load environment variables from the .env file
load_dotenv()

MAILJET_API_KEY = os.getenv('MAILJET_API_KEY')
MAILJET_SECRET_KEY = os.getenv('MAILJET_SECRET_KEY')
FROM_EMAIL = os.getenv('FROM_EMAIL')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')

def send_activation_email(email_to, token):
    activation_link = f"{BASE_URL}/activate-account/{token}"
    subject = "SlidePull | Activate Your Account"
    html_content = f"""
    <h1>Activate Your Account</h1>
    <p>Thank you for registering. Please click the link below to activate your account:</p>
    <p><a href="{activation_link}">Activate Account</a></p>
    <p>If you did not register on our site, please ignore this email.</p>
    """

    # Initialize the Mailjet client
    mailjet = Client(auth=(MAILJET_API_KEY, MAILJET_SECRET_KEY), version='v3.1')

    # Prepare the email data
    data = {
        'Messages': [
            {
                "From": {
                    "Email": FROM_EMAIL,
                    "Name": "SlidePull"
                },
                "To": [
                    {
                        "Email": email_to,
                        "Name": ""
                    }
                ],
                "Subject": subject,
                "HTMLPart": html_content,
            }
        ]
    }

    try:
        result = mailjet.send.create(data=data)
        if result.status_code == 200:
            print(f"Activation email sent to {email_to}")
        else:
            print(f"Failed to send email. Status Code: {result.status_code}")
            print(f"Error: {result.json()}")
    except Exception as e:
        print(f"Error sending activation email: {e}")

