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
from database_op.database import get_db, get_connection
import mysql.connector
from mysql.connector import connection

import logging
import fitz  # PyMuPDF
from typing import List, Optional, Dict
from pydantic import parse_obj_as
from datetime import datetime, timedelta
import asyncio
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def verify_db_connection(db):
    """Verify that the database connection is still valid"""
    try:
        cursor = db.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return True
    except mysql.connector.Error:
        logger.error("Database connection is no longer valid")
        return False

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
    
    cursor = None
    try:
        # Verify database connection is valid
        if not verify_db_connection(db):
            logger.error("Database connection is invalid at the start of upload_pptx")
            # Try to get a new connection
            try:
                db = get_connection()
            except Exception as e:
                logger.error(f"Failed to get a new database connection: {e}")
                conversion_progress[upload_id]["status"] = "error"
                raise HTTPException(
                    status_code=500,
                    detail="Database connection error. Please try again later."
                )

        # Get the current user's information
        user_data = await get_user_data_from_session(request, db)
        user_id = user_data['user_id']
        user_alias = user_data['alias']
        premium_status = user_data['premium_status']

        # Check presentation limits based on user status
        try:
            cursor = db.cursor(dictionary=True, buffered=True)
            cursor.execute("SELECT COUNT(*) as count FROM pdf WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            existing_count = result['count'] if result else 0
            
            # Free users can only have one presentation at a time
            if premium_status == 0 and existing_count >= 1:
                conversion_progress[upload_id]["status"] = "error"
                raise HTTPException(
                    status_code=403, 
                    detail="Free users can only have one presentation. Please delete your existing presentation before uploading a new one."
                )
            # Premium users can have up to 3 presentations
            elif premium_status == 1 and existing_count >= 3:
                conversion_progress[upload_id]["status"] = "error"
                raise HTTPException(
                    status_code=403, 
                    detail="Premium users can have up to 3 presentations. Please delete an existing presentation before uploading a new one."
                )
        except mysql.connector.Error as db_err:
            logger.error(f"Database error when checking existing PDFs: {db_err}")
            conversion_progress[upload_id]["status"] = "error"
            raise HTTPException(
                status_code=500,
                detail="Database connection error. Please try again later."
            )
        finally:
            if cursor:
                cursor.close()
                cursor = None

        # Get the original filename and clean it up for storage
        original_filename = pptx_file.filename
        sanitized_filename = original_filename.replace(" ", "_").replace(".pptx", ".pdf")

        # Get the file size in kilobytes and megabytes
        file_size_kb = round(pptx_file.size / 1024)
        file_size_mb = round(file_size_kb / 1024, 2)
        
        # Check file size against the user's plan limit
        max_size_mb = 20  # Default for free tier
        if premium_status == 1:
            max_size_mb = 30  # Premium tier
        elif premium_status == 2:
            max_size_mb = 50  # Corporate tier
            
        if file_size_mb > max_size_mb:
            conversion_progress[upload_id]["status"] = "error"
            raise HTTPException(
                status_code=413,
                detail=f"File size ({file_size_mb} MB) exceeds the maximum allowed for your plan ({max_size_mb} MB). Please upgrade your plan or upload a smaller file."
            )

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
        
        # Verify database connection is still valid before saving PDF information
        if not verify_db_connection(db):
            logger.error("Database connection lost before saving PDF information")
            # Try to get a new connection
            try:
                db = get_connection()
            except Exception as e:
                logger.error(f"Failed to get a new database connection: {e}")
                conversion_progress[upload_id]["status"] = "error"
                raise HTTPException(
                    status_code=500,
                    detail="Database connection error. Please try again later."
                )
        
        # Save the PDF information to our database
        try:
            cursor = db.cursor(dictionary=True, buffered=True)
            cursor.execute(
                "INSERT INTO pdf (user_id, original_filename, url, sas_token, sas_token_expiry, file_size_kb) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, original_filename, pdf_blob_url, sas_token_pdf, sas_token_expiry, file_size_kb)
            )
            db.commit()
            
            # Get the ID of the newly created PDF record
            pdf_id = cursor.lastrowid
        except mysql.connector.Error as db_err:
            logger.error(f"Database error when saving PDF information: {db_err}")
            conversion_progress[upload_id]["status"] = "error"
            raise HTTPException(
                status_code=500,
                detail="Database error when saving PDF information. Please try again later."
            )
        finally:
            if cursor:
                cursor.close()
                cursor = None
        
        # Update the upload_id in the conversion_progress dictionary to match the pdf_id
        # This allows the WebSocket to track progress using the pdf_id
        logger.info(f"Updating progress tracking: upload_id={upload_id} -> pdf_id={pdf_id}")
        logger.info(f"Current progress data: {conversion_progress[upload_id]}")
        conversion_progress[str(pdf_id)] = conversion_progress[upload_id]
        del conversion_progress[upload_id]
        logger.info(f"Progress data now tracked under pdf_id={pdf_id}: {conversion_progress[str(pdf_id)]}")

        # Step 2: Convert the PDF to images and thumbnails
        # This function will update the progress in the conversion_progress dictionary
        # It now also returns the number of slides
        num_slides = convert_pdf_to_images(pdf_blob_name, user_alias, pdf_id, sas_token_pdf, db)

        # Update the number of slides in the database record
        try:
            cursor = db.cursor()
            cursor.execute(
                "UPDATE pdf SET num_slides = %s WHERE pdf_id = %s",
                (num_slides, pdf_id)
            )
            db.commit()
        except mysql.connector.Error as db_err:
            logger.error(f"Database error when updating number of slides: {db_err}")
            # This is not a critical error, so we log it but don't raise an HTTPException
            # The presentation is still uploaded and processed, just slide count might be missing
        finally:
            if cursor:
                cursor.close()

        # Redirect back to the dashboard with a success message
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Your presentation was uploaded successfully!")
        return response

    except Exception as e:
        # If anything goes wrong, undo any partial database changes
        logger.error(f"Error in upload_pptx: {str(e)}")
        logger.error(traceback.format_exc())  # Log the full stack trace
        
        try:
            if verify_db_connection(db):
                db.rollback()
            else:
                logger.error("Could not rollback because database connection is invalid")
        except Exception as rollback_err:
            logger.error(f"Error during rollback: {str(rollback_err)}")
        
        # Update progress with error
        conversion_progress[upload_id]["status"] = "error"
        
        # Return a more specific error message
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(

                status_code=500,
                detail=f"Failed to upload and process file: {str(e)}"
            )
    finally:
        # Make sure we always close the database cursor
        if cursor:
            try:
                cursor.close()
            except Exception as cursor_err:
                logger.error(f"Error closing cursor: {str(cursor_err)}")

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
    cursor = None

    try:
        # Verify database connection is valid
        if not verify_db_connection(db):
            logger.error("Database connection is invalid at the start of delete_presentation")
            # Try to get a new connection
            try:
                db = get_connection()
            except Exception as e:
                logger.error(f"Failed to get a new database connection: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Database connection error. Please try again later."
                )

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
            logger.info(f"PDF already deleted: {pdf_blob_url_with_sas}")

        # Step 2: Delete all the full-size slide images
        cursor.execute("SELECT url, sas_token FROM image WHERE pdf_id = %s", (pdf_id,))
        images = cursor.fetchall()
        for image in images:
            try:
                image_blob_url_with_sas = f"{image['url']}?{image['sas_token']}"
                image_blob_client = BlobClient.from_blob_url(image_blob_url_with_sas)
                image_blob_client.delete_blob()
            except ResourceNotFoundError:
                logger.info(f"Image already deleted: {image_blob_url_with_sas}")

        # Step 3: Delete all the thumbnails
        cursor.execute("SELECT url, sas_token FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
        thumbnails = cursor.fetchall()
        for thumbnail in thumbnails:
            try:
                thumbnail_blob_url_with_sas = f"{thumbnail['url']}?{thumbnail['sas_token']}"
                thumbnail_blob_client = BlobClient.from_blob_url(thumbnail_blob_url_with_sas)
                thumbnail_blob_client.delete_blob()
            except ResourceNotFoundError:
                logger.info(f"Thumbnail already deleted: {thumbnail_blob_url_with_sas}")

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
            logger.info(f"QR code folder already deleted or doesn't exist: {qr_code_folder_path}")

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
            logger.info(f"Set folder already deleted or doesn't exist: {set_folder_path}")

        # Verify database connection is still valid before deleting records
        if not verify_db_connection(db):
            logger.error("Database connection lost before deleting records")
            # Try to get a new connection
            try:
                db = get_connection()
                # Need to recreate the cursor with the new connection
                cursor.close()
                cursor = db.cursor(dictionary=True, buffered=True)
            except Exception as e:
                logger.error(f"Failed to get a new database connection: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Database connection error. Please try again later."
                )

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
        logger.error(f"Error in delete_presentation: {str(e)}")
        logger.error(traceback.format_exc())  # Log the full stack trace
        
        try:
            if verify_db_connection(db):
                db.rollback()
            else:
                logger.error("Could not rollback because database connection is invalid")
        except Exception as rollback_err:
            logger.error(f"Error during rollback: {str(rollback_err)}")
            
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=500, detail=f"Error deleting presentation: {e}")

    finally:
        # Always close the database cursor
        if cursor:
            try:
                cursor.close()
            except Exception as cursor_err:
                logger.error(f"Error closing cursor: {str(cursor_err)}")

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

    cursor = None
    try:
        # Verify database connection is valid
        if not verify_db_connection(db):
            logger.error("Database connection is invalid at the start of select_thumbnails")
            # Try to get a new connection
            try:
                db = get_connection()
            except Exception as e:
                logger.error(f"Failed to get a new database connection: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Database connection error. Please try again later."
                )

        # Get all the thumbnails for this presentation
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT thumbnail_id, url, sas_token FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
        thumbnails = cursor.fetchall()

        # Show the slide selection page
        return templates.TemplateResponse("conversion/select-slides.html", {
            "request": request,
            "pdf_id": pdf_id,
            "thumbnails": thumbnails
        })
    except Exception as e:
        logger.error(f"Error in select_thumbnails: {str(e)}")
        logger.error(traceback.format_exc())  # Log the full stack trace
        raise HTTPException(status_code=500, detail=f"Error loading thumbnails: {str(e)}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as cursor_err:
                logger.error(f"Error closing cursor: {str(cursor_err)}")

import logging

# Progress tracking is now handled client-side with a simple animation

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
    2. Create a PDF file containing those slides
    3. Generate a QR code that links to the PDF file
    4. Save everything to the database so it appears on the dashboard
    
    When someone scans the QR code, they'll get immediate access to just
    the slides the presenter wanted to share as a PDF file.
    
    Set limits based on premium status:
    - Free tier: 3 sets per presentation
    - Premium tier: 5 sets per presentation
    - Corporate tier: 8 sets per presentation
    """
    logging.info("Starting to generate a new slide set")
    cursor = None

    # Make sure the user is logged in
    if 'user_id' not in request.session:
        logging.warning("User not logged in, redirecting to login page")
        return RedirectResponse(url="/login", status_code=303)
    
    # Get user's premium status
    user_id = request.session['user_id']
    premium_status = request.session.get('premium_status', 0)
    
    # Check if the user has reached their set limit
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as count FROM `set` WHERE pdf_id = %s", (pdf_id,))
    set_count = cursor.fetchone()['count']
    cursor.close()
    
    # Determine max sets based on premium status
    max_sets = 3  # Free tier
    if premium_status == 1:
        max_sets = 5  # Premium tier
    elif premium_status == 2:
        max_sets = 8  # Corporate tier
    
    if set_count >= max_sets:
        # User has reached their set limit
        tier_name = "Free"
        if premium_status == 1:
            tier_name = "Premium"
        elif premium_status == 2:
            tier_name = "Corporate"
            
        response = RedirectResponse(url=f"/select-slides/{pdf_id}", status_code=303)
        set_flash_message(response, f"You have reached the maximum number of sets ({max_sets}) allowed for your {tier_name} tier. Please delete some sets or upgrade your account.")
        return response

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
        # Verify database connection is valid
        if not verify_db_connection(db):
            logger.error("Database connection is invalid at the start of generate_set")
            # Try to get a new connection
            try:
                db = get_connection()
            except Exception as e:
                logger.error(f"Failed to get a new database connection: {e}")
                conversion_progress[str_pdf_id]["status"] = "error"
                raise HTTPException(
                    status_code=500,
                    detail="Database connection error. Please try again later."
                )

        # Get the user's information
        user_id = request.session['user_id']
        selected_thumbnail_ids = parse_obj_as(List[int], selected_thumbnails)
        
        logging.info(f"Processing set creation for user {user_id} with {len(selected_thumbnail_ids)} selected slides")

        # Get the user's alias (needed for file organization in Azure)
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        cursor = None

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
        cursor = None

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

        # Step 2: Create a PDF file with all the selected slides
        logging.info("Packaging slides into a PDF file")
        pdf_buffer = io.BytesIO()
        pdf_document = fitz.open()  # Create a new empty PDF

        for idx, image in enumerate(images):
            try:
                # Get the full URL with security token
                image_url = f"{image['url']}?{image['sas_token']}"
                
                # Download the image from Azure
                blob_client = BlobClient.from_blob_url(image_url)
                downloader = blob_client.download_blob(timeout=30)
                blob_data = downloader.readall()

                # Create a temporary image file in memory
                img_stream = io.BytesIO(blob_data)
                
                # Add the image as a new page to the PDF
                # Create a new page with appropriate dimensions
                img = fitz.open(stream=img_stream, filetype="png")
                rect = img[0].rect  # Get the rectangle representing the image size
                page = pdf_document.new_page(width=rect.width, height=rect.height)
                
                # Insert the image onto the page
                page.insert_image(rect, stream=blob_data)
                img.close()
                
                # Update progress (using 1-based indexing for better user display)
                conversion_progress[str_pdf_id]["current"] = idx + 1
                
            except Exception as e:
                logging.error(f"Problem with slide {idx+1}: {e}")
                conversion_progress[str_pdf_id]["status"] = "error"
                raise Exception(f"Could not process one of your selected slides. Please try again.")

        # Save the PDF to the buffer
        pdf_document.save(pdf_buffer)
        pdf_document.close()
        pdf_buffer.seek(0)

        # Step 3: Upload the PDF file to Azure
        # We include a timestamp to make the filename unique
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        pdf_filename = f"{set_name}_{timestamp}.pdf"
        pdf_blob_path = f"{user_alias}/sets/{pdf_id}/{pdf_filename}"

        # Update progress
        conversion_progress[str_pdf_id]["status"] = "uploading"
        
        pdf_content = pdf_buffer.getvalue()
        pdf_url, pdf_sas_token, pdf_sas_token_expiry = upload_to_blob(
            blob_name=pdf_blob_path,
            file_content=pdf_content,
            content_type="application/pdf",
            user_alias=user_alias
        )
        
        logging.info(f"PDF file uploaded to {pdf_url}")

        # Step 4: Generate a QR code that links directly to the PDF
        conversion_progress[str_pdf_id]["status"] = "generating_qr"
        
        # Get the set ID (we'll need to insert the record first)
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO `set`
            (name, pdf_id, user_id, sas_token, sas_token_expiry, slide_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                set_name,
                pdf_id,
                user_id,
                pdf_sas_token,
                pdf_sas_token_expiry,
                len(images)  # Store the number of slides in the set
            )
        )
        db.commit()
        set_id = cursor.lastrowid
        
        # Generate the QR code with the direct URL to the PDF
        link_with_sas = f"{pdf_url}?{pdf_sas_token}"
        qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = generate_qr(
            link_with_sas=link_with_sas,
            user_alias=user_alias,
            pdf_id=pdf_id,
            set_name=set_name
        )
        
        logging.info(f"QR code generated at {qr_code_url}")

        # Verify database connection is still valid before saving to database
        if not verify_db_connection(db):
            logger.error("Database connection lost before saving to database")
            # Try to get a new connection
            try:
                db = get_connection()
            except Exception as e:
                logger.error(f"Failed to get a new database connection: {e}")
                conversion_progress[str_pdf_id]["status"] = "error"
                raise HTTPException(
                    status_code=500,
                    detail="Database connection error. Please try again later."
                )

        # Step 5: Update the set record with QR code information
        conversion_progress[str_pdf_id]["status"] = "saving"
        
        cursor.execute(
            """
            UPDATE `set`
            SET qrcode_url = %s, qrcode_sas_token = %s, qrcode_sas_token_expiry = %s
            WHERE set_id = %s
            """,
            (
                qr_code_url,
                qr_code_sas_token,
                qr_code_sas_token_expiry,
                set_id
            )
        )
        db.commit()
        cursor.close()
        cursor = None
        
        # Mark process as complete
        conversion_progress[str_pdf_id]["status"] = "complete"

        # All done! Send the user back to the dashboard
        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, f"Your set '{set_name}' was created successfully with {len(images)} slides!")
        return response

    except Exception as e:
        # If anything goes wrong, undo any partial database changes
        logging.exception(f"Error generating set: {e}")
        
        try:
            if verify_db_connection(db):
                db.rollback()
            else:
                logger.error("Could not rollback because database connection is invalid")
        except Exception as rollback_err:
            logger.error(f"Error during rollback: {str(rollback_err)}")
        
        # Update progress with error
        if str_pdf_id in conversion_progress:
            conversion_progress[str_pdf_id]["status"] = "error"
            
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(
                status_code=500, 
                detail="Something went wrong while creating your set. Please try again or contact support."
            )
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception as cursor_err:
                logger.error(f"Error closing cursor: {str(cursor_err)}")
