import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from dotenv import load_dotenv
import os
import socket

# Load environment variables from the .env file
load_dotenv()

# Load environment variables from the .env file
load_dotenv()

# Use generic SMTP credentials
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')

# Configure SMTP settings based on environment variables or default to ZohoMail
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'zoho').lower()

SMTP_SETTINGS = {
    'zoho': {
        'server': 'smtppro.zoho.eu',
        'port': 587,
        'use_tls': True,
        'use_ssl': False
    },
    # Add other providers here if needed in the future
    # 'gmail': {
    #     'server': 'smtp.gmail.com',
    #     'port': 587,
    #     'use_tls': True,
    #     'use_ssl': False
    # }
}

def send_activation_email(email_to, token):
    try:
        # Ensure token is a string and properly encoded
        if not isinstance(token, str):
            token = str(token)
            
        # Check if credentials are configured
        if not SMTP_USER or not SMTP_PASSWORD:
            print("Error: SMTP credentials (SMTP_USER or SMTP_PASSWORD) not configured in .env.")
            return

        # Get SMTP settings for the selected provider
        settings = SMTP_SETTINGS.get(EMAIL_PROVIDER)
        if not settings:
            print(f"Error: Email provider '{EMAIL_PROVIDER}' not supported.")
            return

        smtp_server = settings['server']
        smtp_port = settings['port']
        use_tls = settings['use_tls']
        use_ssl = settings['use_ssl']

        # Generate the activation link
        activation_link = f"{BASE_URL}/activate-account/{token}"
        subject = "SlidePull | Activate Your Account"
        
        # Create a multipart message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = Header(SMTP_USER, 'utf-8')
        msg['To'] = Header(email_to, 'utf-8')
        
        # Create HTML content - using simple HTML to avoid encoding issues
        html_content = f"""
        <html>
        <body>
            <h1>Activate Your Account</h1>
            <p>Thank you for registering with SlidePull. Please click the link below to activate your account:</p>
            <p><a href="{activation_link}">Activate Account</a></p>
            <p>If the link doesn't work, you can also copy and paste this URL into your browser:</p>
            <p>{activation_link}</p>
            <p>If you did not register on our site, please ignore this email.</p>
            <p>This is an automated message, please do not reply to this email.</p>
        </body>
        </html>
        """
        
        # Create plain text version for email clients that don't support HTML
        text_content = f"""
        Activate Your Account

        Thank you for registering with SlidePull. Please click the link below to activate your account:

        {activation_link}

        If you did not register on our site, please ignore this email.
        """
        
        # Attach parts with explicit encoding
        part1 = MIMEText(text_content.encode('utf-8'), 'plain', 'utf-8')
        part2 = MIMEText(html_content.encode('utf-8'), 'html', 'utf-8')
        msg.attach(part1)
        msg.attach(part2)

        # Set a longer timeout for the connection
        socket.setdefaulttimeout(30)  # 30 seconds timeout

        # Connect to the SMTP server
        if use_ssl:
            print(f"Attempting to connect to {smtp_server} using port {smtp_port} with SSL...")
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, email_to, msg.as_string())
                print(f"Activation email sent to {email_to} via {EMAIL_PROVIDER} (port {smtp_port}, SSL).")
        elif use_tls:
            print(f"Attempting to connect to {smtp_server} using port {smtp_port} with STARTTLS...")
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, email_to, msg.as_string())
                print(f"Activation email sent to {email_to} via {EMAIL_PROVIDER} (port {smtp_port}, STARTTLS).")
        else:
            print(f"Attempting to connect to {smtp_server} using port {smtp_port} (no encryption)...")
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_USER, email_to, msg.as_string())
                print(f"Activation email sent to {email_to} via {EMAIL_PROVIDER} (port {smtp_port}, no encryption).")

    except UnicodeError as e:
        print(f"Unicode encoding error: {e}")
        print("This might be caused by non-UTF-8 characters in the token or email addresses.")
        
    except Exception as e:
        print(f"Error sending activation email via {EMAIL_PROVIDER}: {e}")
        print("Please check your network/firewall settings and email account configuration.")

# Note: You will need to update your .env file with your ZohoMail credentials:
# SMTP_USER=your_zoho_email@yourdomain.com
# SMTP_PASSWORD=your_zoho_app_password_or_password
# EMAIL_PROVIDER=zoho
