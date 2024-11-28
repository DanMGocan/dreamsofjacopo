from fastapi import APIRouter, UploadFile, File, Request, Depends, HTTPException, Form
import os
import io
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse

from helpers.flash_utils import set_flash_message
from helpers.blob_op import generate_sas_token_for_file  # Import the SAS token generator
from helpers.user_utils import get_user_data_from_session
from core.main_converter import convert_pptx_bytes_to_pdf, convert_pdf_to_images
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, BlobClient
from database_op.database import get_db
import mysql.connector
from mysql.connector import connection
from mysql.connector.pooling import MySQLConnectionPool

import zipfile
from typing import List
from pydantic import parse_obj_as
import datetime


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
        # Create a RedirectResponse first
        response = RedirectResponse(url="/dashboard", status_code=303)

        # Set a flash message indicating the presentation and associated files were deleted
        set_flash_message(response, "All good homie!")

        # Return the response with the flash message
        return response

    except Exception as e:
        db.rollback()
        return {"error": f"Failed to upload and process file: {str(e)}"}
    finally:
        try:
            cursor.close()
        except:
            pass

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

@converter.get("/select-slides/{pdf_id}", response_class=HTMLResponse)
async def select_thumbnails(
    pdf_id: int,
    request: Request,
    db: connection.MySQLConnection = Depends(get_db)
):
    # Ensure user is logged in
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")

    # Fetch thumbnails for the selected pdf_id, including the SAS token
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT thumbnail_id, url, sas_token FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
    thumbnails = cursor.fetchall()
    cursor.close()

    # Render the template to display thumbnails
    return templates.TemplateResponse("conversion/select-slides.html", {
        "request": request,
        "pdf_id": pdf_id,
        "thumbnails": thumbnails
    })

@converter.post("/generate-set/{pdf_id}", response_class=HTMLResponse)
async def generate_set(
    pdf_id: int,
    request: Request,
    selected_thumbnails: List[str] = Form(...),
    set_name: str = Form(...),
    db: mysql.connector.MySQLConnection = Depends(get_db),
):
    print("[DEBUG] Entering generate_set endpoint")
    print(f"[DEBUG] PDF ID: {pdf_id}")

    # Check session validity before any operations
    if 'user_id' not in request.session:
        print("[DEBUG] User is not logged in")
        return RedirectResponse(url="/login")

    print("[DEBUG] User is logged in")
    """
    Handles the selection of thumbnails, zipping them, uploading to Azure Blob Storage,
    and storing metadata in the database.

    Args:
        pdf_id (int): The ID of the PDF for which thumbnails are selected.
        request (Request): FastAPI request object.
        selected_thumbnails (List[str]): IDs of selected thumbnails from the form.
        set_name (str): User-provided name for the set.
        db (mysql.connector.MySQLConnection): MySQL database connection.

    Returns:
        RedirectResponse: Redirect to the created set's page.
    """
    try:
        print(f"[INFO] Processing PDF ID: {pdf_id}")
        print(f"[INFO] Selected thumbnails: {selected_thumbnails}")
        print(f"[INFO] Set name: {set_name}")

        # Convert selected thumbnails from List[str] to List[int]
        selected_thumbnails = parse_obj_as(List[int], selected_thumbnails)

        # Ensure the user is logged in
        if 'user_id' not in request.session:
            print("[ERROR] User not logged in")
            return RedirectResponse(url="/login")

        # Get the logged-in user's ID from the session
        user_id = request.session['user_id']
        print(f"[INFO] User ID: {user_id}")

        # Fetch selected thumbnails from the database
        cursor = db.cursor(dictionary=True)
        query = "SELECT url, sas_token FROM thumbnail WHERE thumbnail_id IN (%s)" % ",".join(map(str, selected_thumbnails))
        print(f"[INFO] Executing query: {query}")
        cursor.execute(query)
        thumbnails = cursor.fetchall()
        cursor.close()

        if not thumbnails:
            print("[WARNING] No valid thumbnails found for the given IDs.")
            raise HTTPException(status_code=404, detail="No valid thumbnails selected.")

        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            for thumbnail in thumbnails:
                print(f"[INFO] Downloading thumbnail: {thumbnail['url']}")
                # Fetch the image from Azure Blob Storage
                blob_client = BlobClient.from_blob_url(f"{thumbnail['url']}?{thumbnail['sas_token']}")
                blob_data = blob_client.download_blob().readall()

                # Add the image to the zip file
                filename = os.path.basename(thumbnail['url'])
                zip_file.writestr(filename, blob_data)

        zip_buffer.seek(0)
        print("[INFO] Successfully created ZIP archive in memory")

        # Upload the zip file to Azure Blob Storage
        zip_filename = f"{set_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip"
        print(f"[INFO] Uploading ZIP file: {zip_filename}")
        blob_client = BlobClient(
            account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net",
            container_name=os.getenv("AZURE_BLOB_CONTAINER_NAME"),
            blob_name=zip_filename,
            credential=os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
        )
        blob_client.upload_blob(zip_buffer.getvalue(), overwrite=True)
        zip_url = blob_client.url  # Get the URL of the uploaded zip file
        print(f"[INFO] Uploaded ZIP file URL: {zip_url}")

        # Insert the new set into the database
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO `set` (name, qrcode_url, user_id) VALUES (%s, %s, %s)",
            (set_name, zip_url, user_id)
        )
        set_id = cursor.lastrowid  # Get the ID of the newly created set
        print(f"[INFO] Inserted new set with ID: {set_id}")

        # Link thumbnails to the new set
        for thumbnail_id in selected_thumbnails:
            print(f"[INFO] Linking thumbnail {thumbnail_id} to set {set_id}")
            cursor.execute(
                "INSERT INTO set_images (set_id, image_id) VALUES (%s, %s)",
                (set_id, thumbnail_id)
            )
        db.commit()
        cursor.close()

        # Create a RedirectResponse with a flash message
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie("flash_message", "Set created successfully.")
        print("[INFO] Redirecting to /dashboard with success message")
        return response

    except Exception as e:
        print(e)
        print(f"[ERROR] An error occurred: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred")