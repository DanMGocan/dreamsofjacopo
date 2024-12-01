from fastapi import APIRouter, UploadFile, File, Request, Depends, HTTPException, Form
import os
import io
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse

from helpers.flash_utils import set_flash_message
from helpers.blob_op import generate_sas_token_for_file, upload_to_blob  # Import the SAS token generator
from helpers.user_utils import get_user_data_from_session

from core.main_converter import convert_pptx_bytes_to_pdf, convert_pdf_to_images
from core.qr_generator import generate_qr

from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, BlobClient
from database_op.database import get_db
import mysql.connector
from mysql.connector import connection

import logging
import zipfile
from typing import List, Optional
from pydantic import parse_obj_as
from datetime import datetime, timedelta

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

from azure.core.exceptions import ResourceNotFoundError

@converter.post("/delete-presentation/{pdf_id}")
async def delete_presentation(
    pdf_id: int,
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")

    user_id = request.session['user_id']

    try:
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

        if presentation['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="You are not authorized to delete this presentation")

        # Delete the PDF file from Azure Blob Storage
        pdf_blob_url_with_sas = f"{presentation['url']}?{presentation['sas_token']}"
        try:
            blob_client = BlobClient.from_blob_url(pdf_blob_url_with_sas)
            blob_client.delete_blob()
        except ResourceNotFoundError:
            print(f"Blob already deleted: {pdf_blob_url_with_sas}")

        # Delete all associated images from Azure Blob Storage
        cursor.execute("SELECT url, sas_token FROM image WHERE pdf_id = %s", (pdf_id,))
        images = cursor.fetchall()
        for image in images:
            try:
                image_blob_url_with_sas = f"{image['url']}?{image['sas_token']}"
                image_blob_client = BlobClient.from_blob_url(image_blob_url_with_sas)
                image_blob_client.delete_blob()
            except ResourceNotFoundError:
                print(f"Image blob already deleted: {image_blob_url_with_sas}")

        # Delete all associated thumbnails from Azure Blob Storage
        cursor.execute("SELECT url, sas_token FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
        thumbnails = cursor.fetchall()
        for thumbnail in thumbnails:
            try:
                thumbnail_blob_url_with_sas = f"{thumbnail['url']}?{thumbnail['sas_token']}"
                thumbnail_blob_client = BlobClient.from_blob_url(thumbnail_blob_url_with_sas)
                thumbnail_blob_client.delete_blob()
            except ResourceNotFoundError:
                print(f"Thumbnail blob already deleted: {thumbnail_blob_url_with_sas}")

        # Delete associated folders (qr_codes and sets)
        try:
            qr_code_folder_path = f"{user_id}/qr_codes/{pdf_id}"
            qr_code_container_client = BlobClient(
                account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net",
                container_name=os.getenv("AZURE_BLOB_CONTAINER_NAME"),
                blob_name=qr_code_folder_path,
                credential=os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
            )
            qr_code_container_client.delete_blob()
        except ResourceNotFoundError:
            print(f"QR code folder already deleted: {qr_code_folder_path}")

        try:
            set_folder_path = f"{user_id}/sets/{pdf_id}"
            set_container_client = BlobClient(
                account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net",
                container_name=os.getenv("AZURE_BLOB_CONTAINER_NAME"),
                blob_name=set_folder_path,
                credential=os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
            )
            set_container_client.delete_blob()
        except ResourceNotFoundError:
            print(f"Set folder already deleted: {set_folder_path}")

        # Delete database records
        cursor.execute("DELETE FROM image WHERE pdf_id = %s", (pdf_id,))
        cursor.execute("DELETE FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
        cursor.execute("DELETE FROM `set` WHERE user_id = %s AND `name` LIKE %s", (user_id, f"%{pdf_id}%"))
        cursor.execute("DELETE FROM pdf WHERE pdf_id = %s", (pdf_id,))
        db.commit()

        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Presentation, associated files, and folders deleted successfully.")
        return response

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")

    finally:
        cursor.close()



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

import logging

@converter.post("/generate-set/{pdf_id}", response_class=HTMLResponse)
def generate_set(
    pdf_id: int,
    request: Request,
    selected_thumbnails: Optional[List[str]] = Form(None),
    set_name: str = Form(...),
    db: mysql.connector.MySQLConnection = Depends(get_db),
):
    logging.info("Entered generate_set endpoint")

    # Check if the user is logged in
    if 'user_id' not in request.session:
        logging.warning("User not logged in, redirecting to login page")
        return RedirectResponse(url="/login", status_code=303)

    if not selected_thumbnails:
        logging.error("No thumbnails were selected")
        raise HTTPException(status_code=400, detail="No thumbnails selected.")

    try:
        # Parse inputs
        selected_thumbnail_ids = parse_obj_as(List[int], selected_thumbnails)
        user_id = request.session['user_id']
        logging.info(f"User ID: {user_id}")
        logging.info(f"Selected thumbnails: {selected_thumbnail_ids}")

        # Fetch the user's alias
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()

        if not user_data or 'alias' not in user_data:
            logging.error("User alias not found")
            raise HTTPException(status_code=404, detail="User alias not found.")
        user_alias = user_data['alias']
        logging.info(f"User alias: {user_alias}")

        # Fetch the full-size images corresponding to the selected thumbnails
        logging.info("Fetching full-size images for selected thumbnails...")
        cursor = db.cursor(dictionary=True)
        format_strings = ','.join(['%s'] * len(selected_thumbnail_ids))
        query = f"""
            SELECT image.url, image.sas_token
            FROM image
            INNER JOIN thumbnail ON image.image_id = thumbnail.image_id
            WHERE thumbnail.thumbnail_id IN ({format_strings})
        """
        cursor.execute(query, tuple(selected_thumbnail_ids))
        images = cursor.fetchall()
        cursor.close()

        logging.info(f"Number of images fetched: {len(images)}")

        if not images:
            logging.error("No valid images found for selected thumbnails")
            raise HTTPException(status_code=404, detail="No valid images found for selected thumbnails.")

        # Create a zip file in memory
        logging.info("Creating ZIP file for the selected images...")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            for idx, image in enumerate(images):
                try:
                    image_url = f"{image['url']}?{image['sas_token']}"
                    logging.info(f"Downloading image {idx + 1}/{len(images)}: {image_url}")
                    # Download the image data
                    blob_client = BlobClient.from_blob_url(image_url)
                    downloader = blob_client.download_blob(timeout=30)
                    blob_data = downloader.readall()

                    # Add the image to the zip file
                    filename = os.path.basename(image['url'])
                    zip_file.writestr(filename, blob_data)
                    logging.info(f"Added image to ZIP: {filename}")
                except Exception as e:
                    logging.error(f"Error downloading image {image_url}: {e}")
                    raise Exception(f"Failed to process image: {image_url}")

        zip_buffer.seek(0)
        logging.info("ZIP file created successfully")

        # Define the blob name for the ZIP file
        zip_filename = f"{set_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip"
        zip_blob_path = f"{user_alias}/sets/{pdf_id}/{zip_filename}"

        # Upload the ZIP file to blob storage
        logging.info(f"Uploading ZIP file to blob storage: {zip_blob_path}")
        zip_content = zip_buffer.getvalue()
        zip_url, zip_sas_token, zip_sas_token_expiry = upload_to_blob(
            blob_name=zip_blob_path,
            file_content=zip_content,
            content_type="application/zip",
            user_alias=user_alias
        )
        logging.info(f"ZIP file uploaded successfully: {zip_url}")

        # Generate QR code for the ZIP file
        # Generate QR code for the ZIP file
        logging.info("Generating QR code for the ZIP file")
        link_with_sas = f"{zip_url}?{zip_sas_token}"
        qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = generate_qr(
            link_with_sas=link_with_sas,
            user_alias=user_alias,
            pdf_id=pdf_id,
            set_name=set_name  # Pass the set name
        )

        logging.info(f"QR code generated successfully: {qr_code_url}")

        # Insert the new set into the database, including pdf_id
        logging.info("Inserting new set into the database")
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO `set`
            (name, pdf_id, qrcode_url, qrcode_sas_token, qrcode_sas_token_expiry, sas_token, sas_token_expiry, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                set_name,
                pdf_id,
                qr_code_url,
                qr_code_sas_token,
                qr_code_sas_token_expiry,
                zip_sas_token,
                zip_sas_token_expiry,
                user_id
            )
        )
        db.commit()
        cursor.close()
        logging.info("Set inserted into the database successfully")

        # Create a RedirectResponse with a flash message
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie("flash_message", "Set created successfully.")
        logging.info("Redirecting to dashboard with success message")
        return response

    except Exception as e:
        logging.exception("Error generating set")
        db.rollback()
        raise HTTPException(status_code=500, detail="An internal server error occurred")






