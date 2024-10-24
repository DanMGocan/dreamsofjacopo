from mailersend import emails
from dotenv import load_dotenv
import os

# Load environment variables from the .env file
load_dotenv()

MAILERSEND_API_KEY = os.getenv('MAILERSEND_API_KEY')
FROM_EMAIL = os.getenv('FROM_EMAIL')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')

def send_activation_email(email_to, token):
    # Generate the activation link
    activation_link = f"{BASE_URL}/activate-account/{token}"
    subject = "SlidePull | Activate Your Account"
    text_content = "Thank you for registering. Please click the link below to activate your account."
    html_content = f"""
    <h1>Activate Your Account</h1>
    <p>Thank you for registering. Please click the link below to activate your account:</p>
    <p><a href="{activation_link}">Activate Account</a></p>
    <p>If you did not register on our site, please ignore this email.</p>
    """

    # Initialize the MailerSend client
    mailer = emails.NewEmail(MAILERSEND_API_KEY)

    # Create an empty mail body dictionary
    mail_body = {}

    # Set the sender details
    mail_from = {
        "name": "SlidePull",
        "email": FROM_EMAIL,
    }

    # Set the recipient details
    recipients = [
        {
            "name": "Recipient",
            "email": email_to,
        }
    ]

    # Set the reply-to address (optional)
    reply_to = {
        "name": "Support",
        "email": "support@yourdomain.com",
    }

    # Populate the mail body with the necessary fields
    mailer.set_mail_from(mail_from, mail_body)
    mailer.set_mail_to(recipients, mail_body)
    mailer.set_subject(subject, mail_body)
    mailer.set_html_content(html_content, mail_body)
    mailer.set_plaintext_content(text_content, mail_body)
    mailer.set_reply_to(reply_to, mail_body)

    try:
        # Send the email
        response = mailer.send(mail_body)

        # Check for success
        if response['status_code'] == 202:
            print(f"Activation email sent to {email_to}")
        else:
            print(f"Failed to send email. Status Code: {response['status_code']}")
            print(f"Error: {response}")
    except Exception as e:
        print(f"Error sending activation email: {e}")
