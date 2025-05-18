from fastapi import APIRouter, UploadFile, File, Request, Depends, HTTPException, Form, WebSocket
import os
import io
import re
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse

from helpers.flash_utils import set_flash_message
from helpers.blob_op import generate_sas_token_for_file, upload_to_blob
from helpers.user_utils import get_user_data_from_session

from core.main_converter import convert_pptx_bytes_to_pdf, convert_pdf_to_slides_and_thumbnails
from core.qr_generator import generate_qr
from core.shared_state import conversion_progress

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
import uuid
import time

# Configure logging
# logging.basicConfig(level=logging.INFO) # Removed:basicConfig is configured in app/main.py
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
    Handles PowerPoint file uploads, converts them to PDF, and processes them.
    1. Converts PPTX to PDF.
    2. Uploads PDF to Azure.
    3. Converts PDF pages to individual 1-page PDFs and thumbnails.
    """
    upload_id = str(int(datetime.now().timestamp()))
    conversion_progress[upload_id] = {
        "total": 0,
        "current": 0,
        "status": "initializing"
    }
    
    cursor = None
    pdf_id = None # Initialize pdf_id
    start_time_conversion = time.time() # Start timing for conversion stats
    try:
        if not verify_db_connection(db):
            logger.error("Database connection is invalid at the start of upload_pptx")
            try: db = get_connection()
            except Exception as e: logger.error(f"Failed to get a new database connection: {e}")
            if upload_id in conversion_progress:
                conversion_progress[upload_id]["status"] = "error"
                raise HTTPException(status_code=500, detail="Database connection error.")

        user_data = await get_user_data_from_session(request, db)
        user_id = user_data['user_id']
        user_alias = user_data['alias']
        premium_status = user_data['premium_status']

        try:
            cursor = db.cursor(dictionary=True, buffered=True)
            cursor.execute("SELECT COUNT(*) as count FROM pdf WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            existing_count = result['count'] if result else 0
            
            limit = 1 if premium_status == 0 else (3 if premium_status == 1 else 8) # Example limits
            if existing_count >= limit:
                tier_name = "Free" if premium_status == 0 else ("Premium" if premium_status == 1 else "Corporate")
                conversion_progress[upload_id]["status"] = "error"
                raise HTTPException(status_code=403, detail=f"{tier_name} users can only have {limit} presentation(s).")
        except mysql.connector.Error as db_err:
            logger.error(f"Database error checking existing PDFs: {db_err}")
            conversion_progress[upload_id]["status"] = "error"
            raise HTTPException(status_code=500, detail="Database error.")
        finally:
            if cursor: cursor.close(); cursor = None

        original_filename = pptx_file.filename
        sanitized_filename = original_filename.replace(" ", "_").replace(".pptx", ".pdf")
        file_size_kb = round(pptx_file.size / 1024)
        file_size_mb = round(file_size_kb / 1024, 2)
        
        max_size_mb = 20 if premium_status == 0 else (30 if premium_status == 1 else 50)
        if file_size_mb > max_size_mb:
            conversion_progress[upload_id]["status"] = "error"
            raise HTTPException(status_code=413, detail=f"File size ({file_size_mb}MB) exceeds limit ({max_size_mb}MB).")

        pptx_bytes = await pptx_file.read()
        conversion_progress[upload_id]["status"] = "converting_to_pdf"
        pdf_bytes = await convert_pptx_bytes_to_pdf(pptx_bytes, request)

        pdf_blob_name = f"{user_alias}/pdf/{sanitized_filename}"
        sas_token_pdf, sas_token_expiry = generate_sas_token_for_file(alias=user_alias, file_path=f"pdf/{sanitized_filename}")
        conversion_progress[upload_id]["status"] = "uploading_pdf"
        pdf_blob_url_with_sas = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}?{sas_token_pdf}"
        blob_client = BlobClient.from_blob_url(pdf_blob_url_with_sas)
        blob_client.upload_blob(pdf_bytes, overwrite=True)
        pdf_blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}"
        
        if not verify_db_connection(db):
            logger.error("DB connection lost before saving PDF info")
            try: db = get_connection()
            except Exception as e: logger.error(f"Failed to get new DB connection: {e}"); raise HTTPException(status_code=500, detail="DB error.")
        
        try:
            cursor = db.cursor(dictionary=True, buffered=True)
            pdf_unique_code = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO pdf (user_id, original_filename, url, sas_token, sas_token_expiry, file_size_kb, unique_code) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, original_filename, pdf_blob_url, sas_token_pdf, sas_token_expiry, file_size_kb, pdf_unique_code)
            )
            db.commit()
            pdf_id = cursor.lastrowid
        except mysql.connector.Error as db_err:
            logger.error(f"DB error saving PDF info: {db_err}")
            conversion_progress[upload_id]["status"] = "error"
            raise HTTPException(status_code=500, detail="DB error saving PDF.")
        finally:
            if cursor: cursor.close(); cursor = None
        
        logger.info(f"Updating progress tracking: upload_id={upload_id} -> pdf_id={pdf_id}")
        if upload_id in conversion_progress:
            conversion_progress[str(pdf_id)] = conversion_progress.pop(upload_id)
        else: # Should not happen if initialized correctly
            conversion_progress[str(pdf_id)] = {"total": 0, "current": 0, "status": "initializing_late"}

        logger.info(f"Progress data now tracked under pdf_id={pdf_id}: {conversion_progress[str(pdf_id)]}")

        num_slides = await convert_pdf_to_slides_and_thumbnails(pdf_blob_name, user_alias, pdf_id, sas_token_pdf, db)

        try:
            cursor = db.cursor()
            cursor.execute("UPDATE pdf SET num_slides = %s WHERE pdf_id = %s", (num_slides, pdf_id))
            db.commit()
        except mysql.connector.Error as db_err:
            logger.error(f"DB error updating num_slides: {db_err}")
        finally:
            if cursor: cursor.close(); cursor = None

        conversion_progress[str(pdf_id)]["status"] = "generating_pdf_qr"
        try:
            pdf_qr_code_url, pdf_qr_code_sas_token, pdf_qr_code_sas_token_expiry = generate_qr(
                user_alias=user_alias, pdf_id=pdf_id, set_name="full_pdf", pdf_unique_code=pdf_unique_code
            )
            if not verify_db_connection(db):
                logger.error("DB connection lost before saving PDF QR info")
                try: db = get_connection()
                except Exception as e: logger.error(f"Failed to get new DB connection: {e}"); raise HTTPException(status_code=500, detail="DB error.")
            cursor = db.cursor()
            cursor.execute(
                "UPDATE pdf SET pdf_qrcode_url = %s, pdf_qrcode_sas_token = %s, pdf_qrcode_sas_token_expiry = %s WHERE pdf_id = %s",
                (pdf_qr_code_url, pdf_qr_code_sas_token, pdf_qr_code_sas_token_expiry, pdf_id)
            )
            db.commit()
            cursor.close(); cursor = None
            logging.info(f"PDF QR code generated for PDF ID: {pdf_id}")
        except Exception as qr_err:
            logger.error(f"Error generating PDF QR code for PDF ID {pdf_id}: {qr_err}")
            if str(pdf_id) in conversion_progress: conversion_progress[str(pdf_id)]["status"] = "complete_with_qr_error"

        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Your presentation was uploaded successfully!")
        if str(pdf_id) in conversion_progress and conversion_progress[str(pdf_id)]["status"] != "complete_with_qr_error":
             conversion_progress[str(pdf_id)]["status"] = "complete"

        # Record conversion stats
        conversion_duration_seconds = time.time() - start_time_conversion
        
        # Prioritize email, fallback to alias for the stats record
        identifier_for_stats = user_data.get('email')
        if not identifier_for_stats:
            identifier_for_stats = user_data.get('alias', 'unknown_user') # Fallback to alias, then to a placeholder
        
        logger.info(f"Attempting to save conversion_stats for identifier: {identifier_for_stats}, filename: {original_filename}, size: {file_size_kb}, slides: {num_slides}, duration: {conversion_duration_seconds}")
        stat_cursor = None 
        try:
            if not verify_db_connection(db):
                logger.error("DB connection lost before saving conversion_stats")
                db = get_connection() 
            
            stat_cursor = db.cursor() 
            
            if original_filename is None: # Email/Alias has a fallback, so only check filename
                logger.error(f"Cannot save conversion_stats: original_filename ({original_filename}) is None.")
            else:
                stat_cursor.execute(
                    """
                    INSERT INTO conversion_stats (user_email, original_filename, upload_size_kb, num_slides, conversion_duration_seconds)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (identifier_for_stats, original_filename, file_size_kb, num_slides, conversion_duration_seconds)
                )
                db.commit()
                logger.info(f"Conversion stats saved for {original_filename} by {identifier_for_stats}. Duration: {conversion_duration_seconds:.2f}s")
        except Exception as stat_err:
            logger.error(f"Error saving conversion_stats for {original_filename} by {identifier_for_stats}: {stat_err}")
            # Do not fail the whole request if stats saving fails, just log it.
        finally:
            if stat_cursor: # Check if stat_cursor was initialized
                try:
                    stat_cursor.close()
                except Exception as e_stat_close: # More specific exception variable
                    logger.error(f"Error closing stat_cursor for conversion_stats: {e_stat_close}")
                
        return response
    except Exception as e:
        logger.error(f"Error in upload_pptx: {str(e)}", exc_info=True)
        try:
            if db and verify_db_connection(db): db.rollback()
            else: logger.error("Could not rollback, DB connection invalid.")
        except Exception as rollback_err: logger.error(f"Error during rollback: {rollback_err}")
        
        current_progress_key = str(pdf_id) if pdf_id else upload_id
        if current_progress_key in conversion_progress:
            conversion_progress[current_progress_key]["status"] = "error"
        
        if isinstance(e, HTTPException): raise e
        else: raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        if cursor: # This cursor is the main one for the function, not stat_cursor
            try: cursor.close()
            except Exception as cursor_err: logger.error(f"Error closing main cursor: {cursor_err}")

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
    cursor = None
    try:
        if not verify_db_connection(db):
            db = get_connection() # Try to re-establish
        cursor = db.cursor(dictionary=True, buffered=True)
        cursor.execute("""
            SELECT pdf.url, pdf.sas_token, pdf.user_id, user.alias 
            FROM pdf 
            JOIN user ON pdf.user_id = user.user_id 
            WHERE pdf.pdf_id = %s
        """, (pdf_id,))
        presentation = cursor.fetchone()

        if not presentation: raise HTTPException(status_code=404, detail="Presentation not found")
        if presentation['user_id'] != user_id: raise HTTPException(status_code=403, detail="Permission denied")
        
        user_alias = presentation['alias']

        # Delete main PDF
        if presentation['url'] and presentation['sas_token']:
            try:
                BlobClient.from_blob_url(f"{presentation['url']}?{presentation['sas_token']}").delete_blob()
            except ResourceNotFoundError: logger.info(f"Main PDF already deleted: {presentation['url']}")

        # Delete slide_files (both 'pdf' and 'image' types)
        cursor.execute("SELECT url, sas_token FROM slide_file WHERE pdf_id = %s", (pdf_id,))
        slide_files = cursor.fetchall()
        for sf in slide_files:
            try:
                BlobClient.from_blob_url(f"{sf['url']}?{sf['sas_token']}").delete_blob()
            except ResourceNotFoundError: logger.info(f"Slide file already deleted: {sf['url']}")
        
        # Delete thumbnails
        cursor.execute("SELECT url, sas_token FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
        thumbnails = cursor.fetchall()
        for thumb in thumbnails:
            try:
                BlobClient.from_blob_url(f"{thumb['url']}?{thumb['sas_token']}").delete_blob()
            except ResourceNotFoundError: logger.info(f"Thumbnail already deleted: {thumb['url']}")

        # Delete database records
        cursor.execute("DELETE FROM set_image WHERE set_id IN (SELECT set_id FROM `set` WHERE pdf_id = %s)", (pdf_id,))
        cursor.execute("DELETE FROM thumbnail WHERE pdf_id = %s", (pdf_id,))
        cursor.execute("DELETE FROM slide_file WHERE pdf_id = %s", (pdf_id,)) 
        cursor.execute("DELETE FROM `set` WHERE pdf_id = %s", (pdf_id,))
        cursor.execute("DELETE FROM pdf WHERE pdf_id = %s AND user_id = %s", (pdf_id, user_id))
        db.commit()

        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, "Presentation and all associated files deleted successfully.")
        return response
    except Exception as e:
        logger.error(f"Error in delete_presentation: {str(e)}", exc_info=True)
        if db and verify_db_connection(db): db.rollback()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Error deleting presentation: {str(e)}")
    finally:
        if cursor: cursor.close()

@converter.get("/select-slides/{pdf_id}", response_class=HTMLResponse)
async def select_thumbnails(
    pdf_id: int,
    request: Request,
    db: connection.MySQLConnection = Depends(get_db)
):
    if 'user_id' not in request.session:
        return RedirectResponse(url="/login")
    cursor = None
    try:
        if not verify_db_connection(db): db = get_connection()
        cursor = db.cursor(dictionary=True)
        # Fetch thumbnails, ensuring they are ordered by the slide_number of the parent slide_file
        cursor.execute("""
            SELECT t.thumbnail_id, t.url, t.sas_token, sf.slide_number
            FROM thumbnail t
            JOIN slide_file sf ON t.image_id = sf.image_id AND sf.file_type = 'pdf'
            WHERE t.pdf_id = %s
            ORDER BY sf.slide_number
        """, (pdf_id,))
        thumbnails = cursor.fetchall()
        return templates.TemplateResponse("conversion/select-slides.html", {
            "request": request, "pdf_id": pdf_id, "thumbnails": thumbnails
        })
    except Exception as e:
        logger.error(f"Error in select_thumbnails: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading thumbnails: {str(e)}")
    finally:
        if cursor: cursor.close()

@converter.post("/generate-set/{pdf_id}", response_class=HTMLResponse)
async def generate_set(
    pdf_id: int,
    request: Request,
    selected_thumbnails: Optional[List[str]] = Form(None), # These are thumbnail_ids
    set_name: str = Form(...),
    db: mysql.connector.connection.MySQLConnection = Depends(get_db),
):
    logging.info(f"Starting to generate new set '{set_name}' for PDF ID: {pdf_id}")
    cursor = None
    str_pdf_id = str(pdf_id) # For progress tracking key
    start_time_set_creation = time.time() # Start timing for set creation stats

    if 'user_id' not in request.session:
        logging.warning("User not logged in for generate_set, redirecting.")
        return RedirectResponse(url="/login", status_code=303)

    user_id = request.session['user_id']
    premium_status = request.session.get('premium_status', 0)

    from core.main_converter import conversion_progress 
    conversion_progress[str_pdf_id] = {"total": 0, "current": 0, "status": "initializing_set"}

    try:
        if not verify_db_connection(db): db = get_connection()
        
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM `set` WHERE pdf_id = %s AND user_id = %s", (pdf_id, user_id))
        set_count_result = cursor.fetchone()
        set_count = set_count_result['count'] if set_count_result else 0
        
        max_sets = 3 if premium_status == 0 else (5 if premium_status == 1 else 8)
        if set_count >= max_sets:
            tier_name = "Free" if premium_status == 0 else ("Premium" if premium_status == 1 else "Corporate")
            response = RedirectResponse(url=f"/select-slides/{pdf_id}", status_code=303)
            set_flash_message(response, f"Set limit ({max_sets}) for {tier_name} tier reached.")
            return response

        if not selected_thumbnails:
            raise HTTPException(status_code=400, detail="No slides selected for the set.")
        
        selected_thumbnail_ids = parse_obj_as(List[int], selected_thumbnails)
        logging.info(f"User {user_id} creating set '{set_name}' with {len(selected_thumbnail_ids)} selected thumbnails for PDF {pdf_id}.")

        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        if not user_data or 'alias' not in user_data:
            raise HTTPException(status_code=404, detail="User alias not found.")
        user_alias = user_data['alias']

        # Step 1: Get the 1-page slide PDFs for all selected slides
        format_strings_thumb_ids = ','.join(['%s'] * len(selected_thumbnail_ids))
        query_slide_file_info = f"""
            SELECT t.thumbnail_id, sf.image_id as slide_file_id, sf.url, sf.sas_token, sf.slide_number
            FROM thumbnail t
            JOIN slide_file sf ON t.image_id = sf.image_id
            WHERE t.thumbnail_id IN ({format_strings_thumb_ids}) AND sf.file_type = 'pdf' AND sf.pdf_id = %s
        """
        cursor.execute(query_slide_file_info, tuple(selected_thumbnail_ids) + (pdf_id,))
        fetched_slide_infos = cursor.fetchall()

        if not fetched_slide_infos or len(fetched_slide_infos) != len(selected_thumbnail_ids):
            raise HTTPException(status_code=404, detail="Could not retrieve all selected slide PDF details.")

        thumbnail_to_slide_pdf_map = {info['thumbnail_id']: info for info in fetched_slide_infos}
        slide_pdfs_to_merge = []
        for thumb_id in selected_thumbnail_ids:
            if thumb_id in thumbnail_to_slide_pdf_map:
                slide_pdfs_to_merge.append(thumbnail_to_slide_pdf_map[thumb_id])
            else:
                logging.warning(f"Thumbnail ID {thumb_id} selected but not found in fetched slide infos.")
        
        if not slide_pdfs_to_merge:
             raise HTTPException(status_code=404, detail="No valid slide PDFs found for merging after ordering.")

        logging.info(f"Found {len(slide_pdfs_to_merge)} slide PDFs to merge for set '{set_name}'.")
        conversion_progress[str_pdf_id]["total"] = len(slide_pdfs_to_merge)
        conversion_progress[str_pdf_id]["current"] = 0
        conversion_progress[str_pdf_id]["status"] = "merging_pdfs"

        # Step 2: Merge selected 1-page slide PDFs
        merged_pdf_document = fitz.open()
        import aiohttp
        for idx, slide_pdf_info in enumerate(slide_pdfs_to_merge):
            try:
                slide_pdf_url_with_sas = f"{slide_pdf_info['url']}?{slide_pdf_info['sas_token']}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(slide_pdf_url_with_sas) as response:
                        response.raise_for_status()
                        slide_pdf_bytes = await response.read()
                
                temp_slide_doc = fitz.open(stream=slide_pdf_bytes, filetype="pdf")
                merged_pdf_document.insert_pdf(temp_slide_doc)
                temp_slide_doc.close()
                conversion_progress[str_pdf_id]["current"] = idx + 1
            except Exception as e:
                logging.error(f"Problem merging slide PDF (URL: {slide_pdf_info['url']}): {e}", exc_info=True)
                merged_pdf_document.close()
                raise Exception(f"Could not process slide PDF: {slide_pdf_info.get('slide_number', 'unknown')}")

        pdf_buffer = io.BytesIO()
        merged_pdf_document.save(pdf_buffer, garbage=4, deflate=True, clean=True) # Use maximum garbage collection
        merged_pdf_document.close()
        pdf_content = pdf_buffer.getvalue()

        # Step 3: Upload merged set PDF
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        set_pdf_filename = f"{set_name}_{timestamp}.pdf"
        set_pdf_blob_path = f"{user_alias}/sets/{pdf_id}/{set_pdf_filename}"
        conversion_progress[str_pdf_id]["status"] = "uploading_set_pdf"
        
        set_url, set_sas_token, set_sas_token_expiry = upload_to_blob(
            blob_name=set_pdf_blob_path, file_content=pdf_content, content_type="application/pdf", user_alias=user_alias
        )
        logging.info(f"Set PDF for '{set_name}' uploaded to {set_url}")

        # Step 4: Store set information in database
        set_unique_code = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO `set` (name, pdf_id, user_id, url, sas_token, sas_token_expiry, slide_count, unique_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (set_name, pdf_id, user_id, set_url, set_sas_token, set_sas_token_expiry, len(slide_pdfs_to_merge), set_unique_code)
        )
        db.commit()
        set_id = cursor.lastrowid

        # Step 5: Populate set_image table
        for display_idx, slide_info in enumerate(slide_pdfs_to_merge):
            slide_file_id = slide_info['slide_file_id'] 
            cursor.execute(
                "INSERT INTO set_image (set_id, image_id, display_order) VALUES (%s, %s, %s)",
                (set_id, slide_file_id, display_idx)
            )
        db.commit()
        logging.info(f"Populated set_image for set_id {set_id} with {len(slide_pdfs_to_merge)} entries.")

        # Step 6: Generate QR code for the set
        conversion_progress[str_pdf_id]["status"] = "generating_set_qr"
        qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = generate_qr(
            user_alias=user_alias, pdf_id=pdf_id, set_id=set_id, set_name=set_name, set_unique_code=set_unique_code
        )
        logging.info(f"Set QR code for '{set_name}' generated at {qr_code_url}")

        if not verify_db_connection(db): db = get_connection()
        cursor.execute(
            "UPDATE `set` SET qrcode_url = %s, qrcode_sas_token = %s, qrcode_sas_token_expiry = %s WHERE set_id = %s",
            (qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry, set_id)
        )
        db.commit()
        
        conversion_progress[str_pdf_id]["status"] = "complete"

        # Record set creation stats
        creation_duration_seconds = time.time() - start_time_set_creation
        set_size_kb = round(len(pdf_content) / 1024)
        stat_cursor = None # Use a new cursor variable for stats
        try:
            if not verify_db_connection(db):
                logger.error("DB connection lost before saving set_stats")
                db = get_connection()
            
            stat_cursor = db.cursor() # Initialize stat_cursor
            stat_cursor.execute(
                """
                INSERT INTO set_stats (set_id, num_slides_in_set, creation_duration_seconds, set_size_kb)
                VALUES (%s, %s, %s, %s)
                """,
                (set_id, len(slide_pdfs_to_merge), creation_duration_seconds, set_size_kb)
            )
            db.commit()
            logger.info(f"Set stats saved for set_id {set_id}. Duration: {creation_duration_seconds:.2f}s, Size: {set_size_kb}KB")
        except Exception as stat_err:
            logger.error(f"Error saving set_stats for set_id {set_id}: {stat_err}")
        finally:
            if stat_cursor: # Check if stat_cursor was initialized
                try:
                    stat_cursor.close()
                except Exception as e_stat_close: # More specific exception variable
                    logger.error(f"Error closing stat_cursor for set_stats: {e_stat_close}")

        response = RedirectResponse(url="/dashboard", status_code=303)
        set_flash_message(response, f"Your set '{set_name}' created successfully with {len(slide_pdfs_to_merge)} slides!")
        return response

    except Exception as e:
        logger.error(f"Error generating set '{set_name}' for PDF {pdf_id}: {e}", exc_info=True)
        if db and verify_db_connection(db): db.rollback()
        if str_pdf_id in conversion_progress: conversion_progress[str_pdf_id]["status"] = "error"
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Error creating set: {str(e)}")
    finally:
        if cursor: # This is the main cursor for the generate_set function
            try:
                cursor.close()
            except Exception as e_main_cursor_close:
                logger.error(f"Error closing main cursor in generate_set: {e_main_cursor_close}")

def update_slide_count(db, set_id):
    cursor = db.cursor()
    try:
        cursor.execute(
            "UPDATE `set` SET slide_count = (SELECT COUNT(*) FROM set_image WHERE set_id = %s) WHERE set_id = %s",
            (set_id, set_id)
        )
        db.commit()
    except Exception as e:
        logger.error(f"Error updating slide count for set {set_id}: {e}")
    finally:
        cursor.close()

@converter.post("/add-image-to-set/{set_id}")
async def add_image_to_set(
    set_id: int,
    image_id: int, # This is now slide_file_id of a 'pdf' type slide_file
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    cursor = None
    try:
        if not verify_db_connection(db): db = get_connection()
        cursor = db.cursor()
        # Get current max display_order for the set
        cursor.execute("SELECT MAX(display_order) as max_order FROM set_image WHERE set_id = %s", (set_id,))
        result = cursor.fetchone()
        max_order = result[0] if result[0] is not None else -1
        
        cursor.execute(
            "INSERT INTO set_image (set_id, image_id, display_order) VALUES (%s, %s, %s)",
            (set_id, image_id, max_order + 1)
        )
        db.commit()
        update_slide_count(db, set_id) # Update count after successful insert
        return {"message": "Slide added to set successfully."}
    except Exception as e:
        logger.error(f"Error adding image {image_id} to set {set_id}: {e}", exc_info=True)
        if db and verify_db_connection(db): db.rollback()
        raise HTTPException(status_code=500, detail="Error adding slide to set.")
    finally:
        if cursor: cursor.close()

@converter.post("/remove-image-from-set/{set_id}")
async def remove_image_from_set(
    set_id: int,
    image_id: int, # This is slide_file_id
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    cursor = None
    try:
        if not verify_db_connection(db): db = get_connection()
        cursor = db.cursor()
        cursor.execute(
            "DELETE FROM set_image WHERE set_id = %s AND image_id = %s",
            (set_id, image_id)
        )
        db.commit()
        # Optionally, re-order remaining slides if display_order needs to be contiguous
        update_slide_count(db, set_id) # Update count after successful delete
        return {"message": "Slide removed from set successfully."}
    except Exception as e:
        logger.error(f"Error removing image {image_id} from set {set_id}: {e}", exc_info=True)
        if db and verify_db_connection(db): db.rollback()
        raise HTTPException(status_code=500, detail="Error removing slide from set.")
    finally:
        if cursor: cursor.close()
