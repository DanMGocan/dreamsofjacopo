from fastapi import APIRouter, UploadFile, File, Request, Depends, HTTPException
import os
import io
from fastapi.templating import Jinja2Templates

from helpers.blob_op import generate_sas_token_for_file  # Import the SAS token generator
from core.main_converter import convert_pptx_bytes_to_pdf
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from database_op.database import get_db
from datetime import datetime, timedelta
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

# Load environment variables
load_dotenv()

TEMP_DIR = "static/temp/"
os.makedirs(TEMP_DIR, exist_ok=True)  # Ensure temp directory exists

from azure.storage.blob import BlobServiceClient, generate_account_sas, ResourceTypes, AccountSasPermissions

# Load environment variables
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_BLOB_CONTAINER_NAME = os.getenv("AZURE_BLOB_CONTAINER_NAME")

# Initialize the BlobServiceClient without a connection string
blob_service_client = BlobServiceClient(
    account_url=f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
    credential=AZURE_STORAGE_ACCOUNT_KEY
)

converter = APIRouter()

# Initialize templates
templates = Jinja2Templates(directory="templates")

@converter.get("/upload")
async def create_user(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@converter.post("/upload-pptx")
async def upload_pptx(
    request: Request,  # Add Request to access session data
    pptx_file: UploadFile = File(...), 
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    try:
        # Extract the user_id from the session
        user_id = request.session.get('user_id')

        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")

        # Get the user's alias from the database
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        user_alias = user_data['alias']

        # Extract the original filename from the uploaded .pptx file
        original_filename = pptx_file.filename

        # Optional: sanitize the filename (e.g., replace spaces with underscores, remove unsafe characters)
        sanitized_filename = original_filename.replace(" ", "_").replace(".pptx", ".pdf")

        # Read the PPTX file in-memory
        pptx_bytes = await pptx_file.read()

        # Convert the PPTX bytes to PDF bytes in-memory
        pdf_bytes = convert_pptx_bytes_to_pdf(pptx_bytes, request)

        # Define the blob name for the PDF (use the sanitized filename)
        pdf_blob_name = f"{user_alias}/pdf/{sanitized_filename}"

        # Get the blob client for the specific blob (PDF filename as blob name)
        blob_client = blob_service_client.get_blob_client(container=AZURE_BLOB_CONTAINER_NAME, blob=pdf_blob_name)

        # Upload the PDF file content directly to Azure Blob Storage (upload happens regardless of SAS token status)
        blob_client.upload_blob(io.BytesIO(pdf_bytes), overwrite=True)

        # Generate a new SAS token for the specific file (using the new function)
        sas_token = generate_sas_token_for_file(user_alias, f"pdf/{sanitized_filename}")
        sas_token_expiry = datetime.utcnow() + timedelta(days=7)

        # Insert a new record in the PDF table (save both the URL, the original filename, and the file-specific SAS token)
        cursor.execute(
            "INSERT INTO pdf (user_id, original_filename, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s, %s)",
            (user_id, original_filename, f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}", sas_token, sas_token_expiry)
        )
        db.commit()

        # Return the SAS URL (file-level) to be used for future download and processing
        sas_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}?{sas_token}"

        return {
            "message": "File uploaded and converted to PDF successfully!",
            "sas_url": sas_url  # Return the file-level SAS URL for future access
        }

    except Exception as e:
        db.rollback()
        return {"error": f"Failed to upload and process file: {str(e)}"}
    finally:
        cursor.close()



