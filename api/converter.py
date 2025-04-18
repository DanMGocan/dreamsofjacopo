from fastapi import APIRouter, UploadFile, File, Request, Depends, HTTPException, Form, WebSocket
import os
import io
import re
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse

from helpers.flash_utils import set_flash_message
from helpers.blob_op import generate_sas_token_for_file, upload_to_blob
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
from typing import List, Optional, Dict
from pydantic import parse_obj_as
from datetime import datetime, timedelta
import asyncio

# Load our configuration from environment variables
load_dotenv()

# Create a temporary directory for any files we need to process
TEMP_DIR = "static/temp/"
os.makedirs(TEMP_DIR, exist_ok=True)

# Set up Azure Blob Storage connection
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_BLOB_CONTAINER_NAME = os.getenv("AZURE_BLOB_CONTAINER_NAME")

# Initialize the Azure Blob Storage client
blob_service_client = BlobServiceClient(
    account_url=f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
    credential=AZURE_STORAGE_ACCOUNT_KEY
)

# Create our API router
converter = APIRouter()

# Set up templates for rendering HTML
templates = Jinja2Templates(directory="templates")

# Store active conversion progress
conversion_progress: Dict[str, Dict] = {}

@converter.post("/upload-pptx")
async def upload_pptx(
    request: Request,
    pptx_file: UploadFile = File(...),
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Handles PowerPoint file uploads, converts them to PDF, and processes them into images.
    
    This is the main entry point for our conversion process. When a user uploads a .pptx file,
    we take it through the full pipeline:
    1. Check if the user is allowed to upload (free users get 1 presentation)
    2. Convert the PowerPoint to PDF
    3. Upload the PDF to Azure
    4. Convert the PDF to individual slide images
    5. Create thumbnails for the slide selection UI
    
    Note: Only .pptx format is fully supported.
    
    Progress is tracked and can be accessed via WebSocket.
    """
    # Generate a unique ID for this upload process
    upload_id = str(int(datetime.now().timestamp()))
    
    # Initialize progress tracking
    from core.main_converter import conversion_progress
    conversion_progress[upload_id] = {
        "total": 0,
        "current": 0,
        "status": "initializing"
    }
    
    try:
        # Get the current user's information
        user_data = await get_user_data_from_session(request, db)
        user_id = user_data['user_id']
        user_alias = user_data['alias']
        premium_status = user_data['premium_status']

        # Free users can only have one presentation at a time
        if premium_status == 0:
            cursor = db.cursor(dictionary=True, buffered=True)
            cursor.execute("SELECT pdf_id FROM pdf WHERE user_id = %s", (user_id,))
            existing_pdf = cursor.fetchone()
            if existing_pdf:
                cursor.close()
                conversion_progress[upload_id]["status"] = "error"
                raise HTTPException(
                    status_code=403, 
                    detail="Free users can only have one presentation. Please delete your existing presentation before uploading a new one."
                )
            cursor.close()

        # Get the original filename and clean it up for storage
        original_filename = pptx_file.filename
        sanitized_filename = original_filename.replace(" ", "_").replace(".pptx", ".pdf")

        # Read the uploaded PowerPoint file
        pptx_bytes = await pptx_file.read()
        
        # Update progress
        conversion_progress[upload_id]["status"] = "converting_to_pdf"

        # Step 1: Convert PowerPoint to PDF
        pdf_bytes = convert_pptx_bytes_to_pdf(pptx_bytes, request)

        # Set up the path where we'll store the PDF in Azure
        pdf_blob_name = f"{user_alias}/pdf/{sanitized_filename}"

        # Generate a secure access token for this PDF
        sas_token_pdf, sas_token_expiry = generate_sas_token_for_file(
            alias=user_alias,
            file_path=f"pdf/{sanitized_filename}"
        )

        # Update progress
        conversion_progress[upload_id]["status"] = "uploading_pdf"

        # Create the full URL with security token
        pdf_blob_url_with_sas = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}?{sas_token_pdf}"

        # Upload the PDF to Azure
        blob_client = BlobClient.from_blob_url(pdf_blob_url_with_sas)
        blob_client.upload_blob(pdf_bytes, overwrite=True)

        # Store the base URL (without token) in our database
        pdf_blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}"
        
        # Save the PDF information to our database
        cursor = db.cursor(dictionary=True, buffered=True)
        cursor.execute(
            "INSERT INTO pdf (user_id, original_filename, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s, %s)",
            (user_id, original_filename, pdf_blob_url, sas_token_pdf, sas_token_expiry)
        )
        db.commit()
        
        # Get the ID of the newly created PDF record
        pdf_id = cursor.lastrowid
        cursor.close()
        
        # Update the upload_id in the conversion_progress dictionary to match the pdf_id
        # This allows the WebSocket to track progress using the pdf_id
        conversion_progress[str(pdf_id)] = conversion_progress[upload_id]
        del conversion_progress[upload_id]

        # Step 2: Convert the PDF to images and thumbnails
        # This function will update the progress in the conversion_progress dictionary
        convert_pdf_to_images(pdf_blob_name, user_alias, pdf_id, sas_token_pdf, db)

        # Redirect back to the dashboard with a success message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Your presentation was uploaded successfully!")
        return response

    except Exception as e:
        # If anything goes wrong, undo any partial database changes
        db.rollback()
        
        # Update progress with error
        conversion_progress[upload_id]["status"] = "error"
        
        return {"error": f"Failed to upload and process file: {str(e)}"}
    finally:
        # Make sure we always close the database cursor
        try:
            if 'cursor' in locals() and cursor:
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
    """
    Deletes a presentation and all its associated files and database records.
    
    This is a cleanup operation that:
    1. Checks if the user is authorized to delete this presentation
    2. Deletes the PDF, images, thumbnails, and QR codes from Azure
    3. Removes all database records related to this presentation
    
    We're careful to handle cases where files might already be deleted.
    """
    # Make sure the user is logged in
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")

    user_id = request.session['user_id']

    try:
        # Get the presentation details from the database
        cursor = db.cursor(dictionary=True, buffered=True)
        cursor.execute("""
            SELECT url, sas_token, user_id 
            FROM pdf 
            WHERE pdf_id = %s
        """, (pdf_id,))
        presentation = cursor.fetchone()

        # Make sure the presentation exists
        if not presentation:
            raise HTTPException(status_code=404, detail="Presentation not found")

        # Make sure this user owns the presentation
        if presentation['user_id'] != user_id:
            raise HTTPException(status_code=403, detail="You don't have permission to delete this presentation")

        # Step 1: Delete the PDF file from Azure
        pdf_blob_url_with_sas = f"{presentation['url']}?{presentation['sas_token']}"
        try:
            blob_client = BlobClient.from_blob_url(pdf_blob_url_with_sas)
            blob_client.delete_blob()
        except ResourceNotFoundError:
            # It's okay if the file is already gone
            print(f"PDF already deleted: {pdf_blob_url_with_sas}")

        # Step 2: Delete all the full-size slide images
        cursor.execute("SELECT url, sas_token FROM image WHERE pdf_id = %s", (pdf_id,))
        images = cursor.fetchall()
        for image in images:
            try:
                image_blob_url_with_sas = f"{image['url']}?{image['sas_token']}"
                image_blob_client = BlobClient.from_blob_url(image_blob_url_with_sas)
                image_blob_client.delete_blob()
            except ResourceNotFoundError:
                print(f"Image already deleted: {image_blob_url_with_sas}")

        # Step 3: Delete all the thumbnails
        cursor.execute("SELECT url, sas_token FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
        thumbnails = cursor.fetchall()
        for thumbnail in thumbnails:
            try:
                thumbnail_blob_url_with_sas = f"{thumbnail['url']}?{thumbnail['sas_token']}"
                thumbnail_blob_client = BlobClient.from_blob_url(thumbnail_blob_url_with_sas)
                thumbnail_blob_client.delete_blob()
            except ResourceNotFoundError:
                print(f"Thumbnail already deleted: {thumbnail_blob_url_with_sas}")

        # Step 4: Delete any QR code folders
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
            print(f"QR code folder already deleted or doesn't exist: {qr_code_folder_path}")

        # Step 5: Delete any set folders
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
            print(f"Set folder already deleted or doesn't exist: {set_folder_path}")

        # Step 6: Delete all database records
        cursor.execute("DELETE FROM image WHERE pdf_id = %s", (pdf_id,))
        cursor.execute("DELETE FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
        cursor.execute("DELETE FROM `set` WHERE pdf_id = %s", (pdf_id,))
        cursor.execute("DELETE FROM pdf WHERE pdf_id = %s", (pdf_id,))
        db.commit()

        # Redirect back to dashboard with success message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Presentation and all associated files deleted successfully.")
        return response

    except Exception as e:
        # If anything goes wrong, undo any partial database changes
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting presentation: {e}")

    finally:
        # Always close the database cursor
        cursor.close()



@converter.get("/select-slides/{pdf_id}", response_class=HTMLResponse)
async def select_thumbnails(
    pdf_id: int,
    request: Request,
    db: connection.MySQLConnection = Depends(get_db)
):
    """
    Displays the slide selection page for creating a set.
    
    This page shows thumbnails of all slides in the presentation and lets
    the user select which ones to include in their set.
    """
    # Make sure the user is logged in
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")

    # Get all the thumbnails for this presentation
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT thumbnail_id, url, sas_token FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
    thumbnails = cursor.fetchall()
    cursor.close()

    # Show the slide selection page
    return templates.TemplateResponse("conversion/select-slides.html", {
        "request": request,
        "pdf_id": pdf_id,
        "thumbnails": thumbnails
    })

import logging

# WebSocket endpoint for progress updates
@converter.websocket("/ws/progress/{pdf_id}")
async def websocket_progress(websocket: WebSocket, pdf_id: str):
    await websocket.accept()
    
    # Initialize progress for this PDF if not exists
    if pdf_id not in conversion_progress:
        conversion_progress[pdf_id] = {
            "total": 0,
            "current": 0,
            "status": "waiting"
        }
    
    try:
        # Keep connection open and send updates
        while True:
            if pdf_id in conversion_progress:
                progress = conversion_progress[pdf_id]
                await websocket.send_json(progress)
                
                # If process is complete, close the connection
                if progress["status"] == "complete":
                    await websocket.close()
                    break
            
            # Check for updates every second
            await asyncio.sleep(1)
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        # Clean up progress data after some time
        if pdf_id in conversion_progress and conversion_progress[pdf_id]["status"] == "complete":
            # In a real app, you might want to schedule this for deletion after a timeout
            pass

@converter.post("/generate-set/{pdf_id}", response_class=HTMLResponse)
def generate_set(
    pdf_id: int,
    request: Request,
    selected_thumbnails: Optional[List[str]] = Form(None),
    set_name: str = Form(...),
    db: mysql.connector.connection.MySQLConnection = Depends(get_db),
):
    """
    Creates a set of slides based on user selection and generates a QR code for it.
    
    This is the final step in our user flow:
    1. We package up just the slides the user selected
    2. Create a ZIP file containing those slides
    3. Generate a QR code that links to the ZIP file
    4. Save everything to the database so it appears on the dashboard
    
    When someone scans the QR code, they'll get immediate access to just
    the slides the presenter wanted to share.
    """
    logging.info("Starting to generate a new slide set")

    # Make sure the user is logged in
    if 'user_id' not in request.session:
        logging.warning("User not logged in, redirecting to login page")
        return RedirectResponse(url="/login", status_code=303)

    # Make sure they actually selected some slides
    if not selected_thumbnails:
        logging.error("User didn't select any slides")
        raise HTTPException(status_code=400, detail="Please select at least one slide to include in your set.")
    
    # Validate set name - no spaces allowed
    if not re.match(r'^[A-Za-z0-9_-]+$', set_name):
        sanitized_name = re.sub(r'[^A-Za-z0-9_-]', '', set_name.replace(' ', '_'))
        logging.warning(f"Invalid set name '{set_name}', sanitized to '{sanitized_name}'")
        set_name = sanitized_name
    
    # Initialize progress tracking
    str_pdf_id = str(pdf_id)
    conversion_progress[str_pdf_id] = {
        "total": 0,
        "current": 0,
        "status": "initializing"
    }

    try:
        # Get the user's information
        user_id = request.session['user_id']
        selected_thumbnail_ids = parse_obj_as(List[int], selected_thumbnails)
        
        logging.info(f"Processing set creation for user {user_id} with {len(selected_thumbnail_ids)} selected slides")

        # Get the user's alias (needed for file organization in Azure)
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()

        if not user_data or 'alias' not in user_data:
            logging.error(f"Couldn't find alias for user {user_id}")
            raise HTTPException(status_code=404, detail="User profile incomplete. Please contact support.")
        
        user_alias = user_data['alias']

        # Step 1: Get the full-size images for all selected slides
        cursor = db.cursor(dictionary=True)
        format_strings = ','.join(['%s'] * len(selected_thumbnail_ids))
        query = f"""
            SELECT image.url, image.sas_token
            FROM image
            INNER JOIN thumbnail ON image.image_id = thumbnail.image_id
            WHERE thumbnail.thumbnail_id IN ({format_strings})
            ORDER BY image.image_id  -- Keep slides in order
        """
        cursor.execute(query, tuple(selected_thumbnail_ids))
        images = cursor.fetchall()
        cursor.close()

        logging.info(f"Found {len(images)} images for the selected slides")

        if not images:
            conversion_progress[str_pdf_id]["status"] = "error"
            raise HTTPException(
                status_code=404, 
                detail="Could not find the selected slides. Please try again or contact support."
            )
        
        # Update progress information
        conversion_progress[str_pdf_id]["total"] = len(images)
        conversion_progress[str_pdf_id]["current"] = 0
        conversion_progress[str_pdf_id]["status"] = "processing"

        # Step 2: Create a ZIP file with all the selected slides
        logging.info("Packaging slides into a ZIP file")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            for idx, image in enumerate(images):
                try:
                    # Get the full URL with security token
                    image_url = f"{image['url']}?{image['sas_token']}"
                    
                    # Download the image from Azure
                    blob_client = BlobClient.from_blob_url(image_url)
                    downloader = blob_client.download_blob(timeout=30)
                    blob_data = downloader.readall()

                    # Add it to our ZIP file with a nice filename
                    # We use the original filename but add a slide number prefix
                    filename = f"slide_{idx+1}_{os.path.basename(image['url'])}"
                    zip_file.writestr(filename, blob_data)
                    
                    # Update progress
                    conversion_progress[str_pdf_id]["current"] = idx + 1
                    
                except Exception as e:
                    logging.error(f"Problem with slide {idx+1}: {e}")
                    conversion_progress[str_pdf_id]["status"] = "error"
                    raise Exception(f"Could not process one of your selected slides. Please try again.")

        # Reset the buffer position so we can read from the beginning
        zip_buffer.seek(0)

        # Step 3: Upload the ZIP file to Azure
        # We include a timestamp to make the filename unique
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        zip_filename = f"{set_name}_{timestamp}.zip"
        zip_blob_path = f"{user_alias}/sets/{pdf_id}/{zip_filename}"

        # Update progress
        conversion_progress[str_pdf_id]["status"] = "uploading"
        
        zip_content = zip_buffer.getvalue()
        zip_url, zip_sas_token, zip_sas_token_expiry = upload_to_blob(
            blob_name=zip_blob_path,
            file_content=zip_content,
            content_type="application/zip",
            user_alias=user_alias
        )
        
        logging.info(f"ZIP file uploaded to {zip_url}")

        # Step 4: Generate a QR code that links to the ZIP file
        conversion_progress[str_pdf_id]["status"] = "generating_qr"
        
        link_with_sas = f"{zip_url}?{zip_sas_token}"
        qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = generate_qr(
            link_with_sas=link_with_sas,
            user_alias=user_alias,
            pdf_id=pdf_id,
            set_name=set_name
        )
        
        logging.info(f"QR code generated at {qr_code_url}")

        # Step 5: Save everything to the database
        conversion_progress[str_pdf_id]["status"] = "saving"
        
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO `set`
            (name, pdf_id, qrcode_url, qrcode_sas_token, qrcode_sas_token_expiry, 
             sas_token, sas_token_expiry, user_id)
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
        
        # Mark process as complete
        conversion_progress[str_pdf_id]["status"] = "complete"

        # All done! Send the user back to the dashboard
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, f"Your set '{set_name}' was created successfully with {len(images)} slides!")
        return response

    except Exception as e:
        # If anything goes wrong, undo any partial database changes
        logging.exception(f"Error generating set: {e}")
        db.rollback()
        
        # Update progress with error
        if str_pdf_id in conversion_progress:
            conversion_progress[str_pdf_id]["status"] = "error"
            
        raise HTTPException(
            status_code=500, 
            detail="Something went wrong while creating your set. Please try again or contact support."
        )
