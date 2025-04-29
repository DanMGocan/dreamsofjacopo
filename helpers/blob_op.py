# Azure Blob Storage Organization
# 
# We organize our files in Azure Blob Storage using this structure:
# - user_alias/pdf/filename.pdf - The converted PDF files
# - user_alias/images/pdf_id/slide_1.png - Full-size slide images
# - user_alias/thumbnails/pdf_id/slide_1.png - Thumbnail images for selection UI
# - user_alias/qrcodes/pdf_id_qr.png - Generated QR codes
#
# This organization keeps everything neat and makes it easy to find and
# manage files for each user.

import os
from azure.storage.blob import generate_blob_sas, BlobSasPermissions, ContentSettings, BlobClient
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import Request

# Load our environment variables from .env file
load_dotenv()

# Get Azure Storage account details from environment variables
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_BLOB_CONTAINER_NAME = os.getenv("AZURE_BLOB_CONTAINER_NAME")

def generate_sas_token_for_file(alias, file_path, current_sas_token=None, sas_token_expiry=None, content_disposition=None):
    """
    Creates or reuses a Shared Access Signature (SAS) token for accessing a file in Azure Blob Storage.
    
    SAS tokens are like temporary passwords that grant limited access to a specific file.
    They're perfect for giving users secure access to their files without exposing our storage account keys.
    
    We set these to expire after 7 days for security reasons.
    """
    # If we already have a valid token, just reuse it
    if current_sas_token and sas_token_expiry and datetime.utcnow().replace(tzinfo=timezone.utc) < sas_token_expiry:
        print(f"Reusing existing SAS token for '{file_path}' - still valid")
        return current_sas_token, sas_token_expiry

    # Make sure the blob name includes the user's alias for organization
    if file_path.startswith(f"{alias}/"):
        blob_name = file_path  # Path already includes alias
    else:
        blob_name = f"{alias}/{file_path}"  # Add alias to path

    # Set token to expire in 7 days
    expiry_time = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(days=7)

    # Generate the SAS token with the permissions we need
    sas_token = generate_blob_sas(
        account_name=AZURE_STORAGE_ACCOUNT_NAME,
        container_name=AZURE_BLOB_CONTAINER_NAME,
        blob_name=blob_name,
        account_key=AZURE_STORAGE_ACCOUNT_KEY,
        # Allow reading, writing, and deleting this specific blob
        permission=BlobSasPermissions(read=True, write=True, delete=True),
        expiry=expiry_time,
        content_disposition=content_disposition  # Controls how browsers handle the file when downloaded
    )

    print(f"Created new SAS token for '{blob_name}' (expires in 7 days)")
    return sas_token, expiry_time


# These are placeholder functions for future implementation
# We'll build these out as needed for specific file types
def upload_presentation():
    pass 

def upload_pdf():
    pass 

def upload_images():
    pass 

def upload_thumbnails():
    pass 

def upload_zip():
    pass 

def upload_to_blob(blob_name, file_content, content_type, user_alias, content_disposition=None):
    """
    Uploads any file to Azure Blob Storage and returns access information.
    
    This is our main upload function that handles all file types. It:
    1. Generates a secure access token for the file
    2. Uploads the file to Azure with the right content type
    3. Returns the URL and token needed to access the file
    
    We use this for everything - PDFs, images, thumbnails, QR codes, etc.
    """
    try:
        # First, get a SAS token that will allow access to this file
        sas_token, sas_token_expiry = generate_sas_token_for_file(
            alias=user_alias,
            file_path=blob_name,
            content_disposition=content_disposition
        )

        # Build the base URL for this file (without the SAS token)
        # This is what we'll store in the database
        blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{blob_name}"

        # Add the SAS token to create a full access URL
        blob_url_with_sas = f"{blob_url}?{sas_token}"

        # Create a client for uploading to this specific blob
        blob_client = BlobClient.from_blob_url(blob_url_with_sas)

        # Upload the file with the right content type
        # We use BlockBlob for all our files since they're relatively small
        blob_client.upload_blob(
            file_content,
            blob_type="BlockBlob",
            overwrite=True,  # Replace if a file with this name already exists
            content_settings=ContentSettings(content_type=content_type)
        )

        # Return everything the app needs to access this file later
        return blob_url, sas_token, sas_token_expiry
    except Exception as e:
        # If anything goes wrong, provide a helpful error message
        raise Exception(f"Couldn't upload file to Azure: {e}")
