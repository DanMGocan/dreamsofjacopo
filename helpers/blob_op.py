# How does a blob work? 

# blob_link/user_alias/presentations/presentation_id/presentation_id.pptx
# blob_link/user_alias/pdf/presentation_id/pdf_id.pdf
# blob_link/user_alias/images/presentation_id/image_id.jpg
# blob_link/user_alias/thumbnails/presentation_id/thumbnail_id.jpg

import os
from azure.storage.blob import generate_blob_sas, BlobSasPermissions, ContentSettings, BlobClient
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import Request

# Load environment variables from .env file
load_dotenv()

# Get Azure Storage account details from environment variables
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_BLOB_CONTAINER_NAME = os.getenv("AZURE_BLOB_CONTAINER_NAME")

def generate_sas_token_for_file(alias, file_path, current_sas_token=None, sas_token_expiry=None):
    # Check if the current SAS token is still valid
    if current_sas_token and sas_token_expiry and datetime.utcnow().replace(tzinfo=timezone.utc) < sas_token_expiry:
        print(f"Using existing SAS token for file '{file_path}'")
        return current_sas_token, sas_token_expiry  # Return the existing valid SAS token and its expiry time

    # Ensure blob_name includes alias only once
    if file_path.startswith(f"{alias}/"):
        blob_name = file_path  # file_path already includes alias
    else:
        blob_name = f"{alias}/{file_path}"  # Prepend alias to file_path

    expiry_time = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(days=7)

    # Generate the SAS token for the specific file (blob)
    sas_token = generate_blob_sas(
        account_name=AZURE_STORAGE_ACCOUNT_NAME,
        container_name=AZURE_BLOB_CONTAINER_NAME,
        blob_name=blob_name,  # Blob name with alias included correctly
        account_key=AZURE_STORAGE_ACCOUNT_KEY,  # Storage account key for authentication
        permission=BlobSasPermissions(read=True, write=True, delete=True),  # Permissions
        expiry=expiry_time  # Set expiry time
    )

    print(f"Generated new SAS Token for file '{blob_name}': {sas_token}")
    return sas_token, expiry_time

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

def upload_to_blob(blob_name, file_content, content_type, user_alias):
    try:
        # Generate SAS token for the specific image blob
        sas_token_image, sas_token_expiry = generate_sas_token_for_file(
            alias=user_alias,
            file_path=blob_name
        )

        # Construct the base blob URL without the SAS token
        blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{blob_name}"

        # Append the SAS token when accessing the blob
        blob_url_with_sas = f"{blob_url}?{sas_token_image}"

        # Create a BlobClient using the SAS URL
        blob_client = BlobClient.from_blob_url(blob_url_with_sas)

        # Upload the file content to Azure Blob Storage
        blob_client.upload_blob(
            file_content,
            blob_type="BlockBlob",
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )

        # Construct and return the Blob URL without the SAS token
        blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{blob_name}"
        print(f"Blob Name: {blob_name}")
        print(f"SAS Token: {sas_token_image}")
        print(f"Blob URL with SAS: {blob_url_with_sas}")
        
        
        return blob_url, sas_token_image, sas_token_expiry
    except Exception as e:
        raise Exception(f"Failed to upload blob: {e}")



