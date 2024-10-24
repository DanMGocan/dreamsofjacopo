from fastapi import APIRouter, UploadFile, File, Request, Depends, HTTPException
import os
import io
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse 

from helpers.flash_utils import set_flash_message
from helpers.blob_op import generate_sas_token_for_file  # Import the SAS token generator
from helpers.user_utils import get_user_data_from_session
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

@converter.post("/upload-pptx")
async def upload_pptx(
    request: Request,
    pptx_file: UploadFile = File(...),
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    try:
        # Use the helper function to get user data from session and database
        user_data = await get_user_data_from_session(request, db)
        user_id = user_data['user_id']
        user_alias = user_data['alias']
        premium_status = user_data['premium_status']

        # Check if the user has already uploaded a file if not a premium user
        if premium_status == 0:
            cursor = db.cursor(dictionary=True, buffered=True)
            cursor.execute("SELECT pdf_id FROM pdf WHERE user_id = %s", (user_id,))
            existing_pdf = cursor.fetchone()
            if existing_pdf:
                raise HTTPException(
                    status_code=403, 
                    detail="You have already uploaded a file. Delete the existing file before uploading a new one."
                )
            cursor.close()

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
        cursor = db.cursor(dictionary=True, buffered=True)
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

from starlette.responses import RedirectResponse
from fastapi import Request

@converter.post("/delete-presentation/{pdf_id}")
async def delete_presentation(
    pdf_id: int,
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    # Ensure the user is logged in
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")

    user_id = request.session['user_id']

    # Fetch the presentation, including the SAS token and blob URL
    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute("""
        SELECT url, sas_token, user_id 
        FROM pdf 
        WHERE pdf_id = %s
    """, (pdf_id,))
    presentation = cursor.fetchone()

    if not presentation:
        raise HTTPException(status_code=404, detail="Presentation not found")

    # Ensure the presentation belongs to the current user
    if presentation['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this presentation")

    # Use the URL with the SAS token to delete the PDF file from Azure Blob Storage
    pdf_blob_url_with_sas = f"{presentation['url']}?{presentation['sas_token']}"
    blob_client = BlobClient.from_blob_url(pdf_blob_url_with_sas)
    blob_client.delete_blob()

    # Delete all associated images from Azure Blob Storage
    cursor.execute("SELECT url, sas_token FROM image WHERE pdf_id = %s", (pdf_id,))
    images = cursor.fetchall()

    for image in images:
        image_blob_url_with_sas = f"{image['url']}?{image['sas_token']}"
        image_blob_client = BlobClient.from_blob_url(image_blob_url_with_sas)
        image_blob_client.delete_blob()

    # Delete all associated thumbnails from Azure Blob Storage
    cursor.execute("SELECT url, sas_token FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
    thumbnails = cursor.fetchall()

    for thumbnail in thumbnails:
        thumbnail_blob_url_with_sas = f"{thumbnail['url']}?{thumbnail['sas_token']}"
        thumbnail_blob_client = BlobClient.from_blob_url(thumbnail_blob_url_with_sas)
        thumbnail_blob_client.delete_blob()

    # Delete the PDF, images, and thumbnails from the database
    cursor.execute("DELETE FROM image WHERE pdf_id = %s", (pdf_id,))
    cursor.execute("DELETE FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
    cursor.execute("DELETE FROM pdf WHERE pdf_id = %s", (pdf_id,))

    db.commit()

    # Close the cursor after the operation
    cursor.close()

    # Create a RedirectResponse first
    response = RedirectResponse(url="/dashboard", status_code=303)

    # Set a flash message indicating the presentation and associated files were deleted
    set_flash_message(response, "Presentation and all associated files deleted successfully")

    # Return the response with the flash message
    return response
