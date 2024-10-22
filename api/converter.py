from fastapi import APIRouter, UploadFile, File, Request, Depends, HTTPException
import os
import io
from fastapi.templating import Jinja2Templates

from helpers.blob_op import generate_sas_token_for_file  # Import the SAS token generator
from core.main_converter import convert_pptx_bytes_to_pdf, convert_pdf_to_images
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, BlobClient
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
    request: Request,
    pptx_file: UploadFile = File(...),
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    try:
        # Extract the user_id from the session
        user_id = request.session.get('user_id')

        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")

        # Get the user's alias from the database
        cursor = db.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        user_alias = user_data['alias']

        # Extract the original filename from the uploaded .pptx file
        original_filename = pptx_file.filename

        # Sanitize the filename
        sanitized_filename = original_filename.replace(" ", "_").replace(".pptx", ".pdf")

        # Read the PPTX file in-memory
        pptx_bytes = await pptx_file.read()

        # Convert the PPTX bytes to PDF bytes in-memory
        pdf_bytes = convert_pptx_bytes_to_pdf(pptx_bytes, request)

        # Define the blob name for the PDF
        pdf_blob_name = f"{user_alias}/pdf/{sanitized_filename}"

        # Generate the SAS token for this specific PDF file
        sas_token_pdf, sas_token_expiry = generate_sas_token_for_file(
            alias=user_alias,
            file_path=f"pdf/{sanitized_filename}"
        )

        # Construct the blob URL with SAS token
        pdf_blob_url_with_sas = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}?{sas_token_pdf}"

        # Create a BlobClient using the SAS URL
        blob_client = BlobClient.from_blob_url(pdf_blob_url_with_sas)

        # Upload the PDF file content directly to Azure Blob Storage
        blob_client.upload_blob(pdf_bytes, overwrite=True)

        # Construct the base blob URL without the SAS token
        pdf_blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}"

        # Store the base URL in the database
        cursor.execute(
            "INSERT INTO pdf (user_id, original_filename, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s, %s)",
            (user_id, original_filename, pdf_blob_url, sas_token_pdf, sas_token_expiry)
        )

        db.commit()

        # Fetch the pdf_id of the inserted PDF entry
        pdf_id = cursor.lastrowid

        # Close the cursor before calling the next function
        cursor.close()

        # In upload_pptx function
        convert_pdf_to_images(pdf_blob_name, user_alias, pdf_id, sas_token_pdf, db)

        # Return the SAS URL for the PDF
        return {
            "message": "File uploaded and converted to PDF successfully!",
            "sas_url": pdf_blob_url_with_sas
        }

    except Exception as e:
        db.rollback()
        return {"error": f"Failed to upload and process file: {str(e)}"}
    finally:
        try:
            cursor.close()
        except:
            pass



