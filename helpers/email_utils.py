import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from dotenv import load_dotenv
import os
import socket

# Load environment variables from the .env file
load_dotenv()

GMAIL_USER = os.getenv('GMAIL_USER')
GMAIL_PASSWORD = os.getenv('GMAIL_PASSWORD')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')

def send_activation_email(email_to, token):
    try:
        # Ensure token is a string and properly encoded
        if not isinstance(token, str):
            token = str(token)
            
        # Check if credentials are configured
        if not GMAIL_USER or not GMAIL_PASSWORD:
            print("Error: Gmail credentials (GMAIL_USER or GMAIL_PASSWORD) not configured in .env.")
            return

        # Generate the activation link
        activation_link = f"{BASE_URL}/activate-account/{token}"
        subject = "SlidePull | Activate Your Account"
        
        # Create a multipart message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = Header(GMAIL_USER, 'utf-8')
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

        # First attempt: Try using port 587 with STARTTLS (works better in some network environments)
        try:
            print("Attempting to connect to Gmail SMTP server using port 587 with STARTTLS...")
            with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(GMAIL_USER, GMAIL_PASSWORD)
                server.sendmail(GMAIL_USER, email_to, msg.as_string())
                print(f"Activation email sent to {email_to} via Gmail (port 587).")
                return
        except Exception as e:
            print(f"Failed to send email using port 587: {e}")
            # If port 587 fails, try port 465 with SSL
            
        # Second attempt: Try using port 465 with SSL (traditional secure method)
        print("Attempting to connect to Gmail SMTP server using port 465 with SSL...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, email_to, msg.as_string())
            print(f"Activation email sent to {email_to} via Gmail (port 465).")

    except UnicodeError as e:
        print(f"Unicode encoding error: {e}")
        print("This might be caused by non-UTF-8 characters in the token or email addresses.")
        
    except Exception as e:
        print(f"Error sending activation email via Gmail: {e}")
        print("Please check your network/firewall settings and Gmail account configuration.")
