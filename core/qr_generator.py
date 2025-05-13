import qrcode
import io
from helpers.blob_op import upload_to_blob
import os
import logging
from dotenv import load_dotenv
import uuid

# Load environment variables
load_dotenv()

# Get the base URL from environment variables or default to localhost
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

def generate_qr(user_alias, pdf_id=None, set_id=None, set_name=None, pdf_unique_code=None, set_unique_code=None):
    """
    Creates a QR code that links to the user's slides through a secure redirection endpoint.
    
    Instead of directly embedding Azure URLs and SAS tokens in QR codes, this function now
    generates QR codes that point to our secure endpoint, which handles the redirections
    and SAS token management internally.
    
    Uses unique codes for security instead of sequential IDs.
    """
    try:
        logging.info(f"Generating QR code for user {user_alias}, PDF ID {pdf_id}, set ID {set_id}, set name {set_name}")
        
        # Determine the type of QR code and construct the secure link using unique codes
        if pdf_unique_code:
            # For full PDFs, link to our secure PDF endpoint using the unique code
            secure_link = f"{BASE_URL}/s/pdf/{pdf_unique_code}"
            logging.info(f"Generated secure PDF link: {secure_link}")
        elif set_unique_code:
            # For sets of slides, link to our secure set endpoint using the unique code
            secure_link = f"{BASE_URL}/s/set/{set_unique_code}"
            logging.info(f"Generated secure set link: {secure_link}")
        else:
            # If we don't have proper identification, raise an error
            raise ValueError("Missing required parameters: either pdf_unique_code or set_unique_code must be provided")
        
        # Set up our QR code with good defaults
        qr = qrcode.QRCode(
            version=1,                                  # QR code version (size)
            error_correction=qrcode.constants.ERROR_CORRECT_L,  # Low error correction
            box_size=10,                                # Size of each box in pixels
            border=4,                                   # White border around the QR code
        )
        
        # Add the secure link to the QR code (no SAS token exposed)
        qr.add_data(secure_link)
        qr.make(fit=True)  # Optimize the QR code size

        # Create the QR code image in memory (no need to save to disk)
        qr_buffer = io.BytesIO()
        qr_image = qr.make_image(fill_color="black", back_color="white")
        qr_image.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)  # Reset buffer position to the beginning

        # Set up the path where we'll store this in Azure
        # We organize by user and presentation ID to keep things tidy
        # Use a different path for full PDF QR codes vs set QR codes
        # We'll still use the IDs for the blob name for organization
        if pdf_id and set_name == "full_pdf":
            qr_blob_name = f"{user_alias}/qrcodes/{pdf_id}_full_pdf_qr.png"
        elif set_id and set_name:
             qr_blob_name = f"{user_alias}/qrcodes/{set_id}_{set_name}_qr.png"
        else:
             # Fallback or error if IDs are missing for blob naming
             # This might need adjustment based on how QR codes are generated initially
             logging.warning("PDF ID or Set ID missing for QR code blob naming.")
             qr_blob_name = f"{user_alias}/qrcodes/unknown_qr_{uuid.uuid4()}.png"

        logging.info(f"QR code blob path: {qr_blob_name}")

        # When users download the QR code, we want it to have a nice filename
        # that includes the set name they chose
        # Use set_name if available, otherwise a default
        download_filename = f"{set_name or 'qrcode'}_qr.png"
        content_disposition = f'attachment; filename="{download_filename}"'

        # Upload the QR code to Azure and get back the URL and security token
        # The content_disposition ensures the file downloads with the right name
        qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = upload_to_blob(
            blob_name=qr_blob_name,
            file_content=qr_buffer.getvalue(),
            content_type="image/png",
            user_alias=user_alias,
            content_disposition=content_disposition
        )

        logging.info(f"QR code generated at {qr_code_url}")

        # Return everything the app needs to display and link to the QR code
        return qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry

    except Exception as e:
        # Log the error with detailed information
        logging.error(f"Error generating QR code for user {user_alias}, PDF ID {pdf_id}, set ID {set_id}, set name {set_name}: {e}")
        # If anything goes wrong, provide a helpful error message
        raise Exception(f"Couldn't create your QR code: {e}")
