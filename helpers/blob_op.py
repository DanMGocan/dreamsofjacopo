# How does a blob work? 

# blob_link/user_alias/presentations/presentation_id/presentation_id.pptx
# blob_link/user_alias/pdf/presentation_id/pdf_id.pdf
# blob_link/user_alias/images/presentation_id/image_id.jpg
# blob_link/user_alias/thumbnails/presentation_id/thumbnail_id.jpg

import os
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Azure Storage account details from environment variables
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_BLOB_CONTAINER_NAME = os.getenv("AZURE_BLOB_CONTAINER_NAME")

# Generate a SAS token for a specific file (blob)
def generate_sas_token_for_file(alias, file_path):
    # Generate a SAS token for the specific file under the user's alias folder
    blob_name = f"{alias}/{file_path}"  # Full path to the file
    
    # Generate the SAS token for the specific file (blob)
    sas_token = generate_blob_sas(
        account_name=AZURE_STORAGE_ACCOUNT_NAME,
        container_name=AZURE_BLOB_CONTAINER_NAME,
        blob_name=blob_name,  # Specific file path (blob)
        account_key=AZURE_STORAGE_ACCOUNT_KEY,  # Storage account key for authentication
        permission=BlobSasPermissions(read=True, write=True, delete=True, list=True),  # Permissions
        expiry=datetime.now(timezone.utc) + timedelta(days=7)  # Set expiry time
    )
    
    print(f"Generated SAS Token for file '{blob_name}': {sas_token}")
    return sas_token

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


