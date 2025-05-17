import os
import io
import fitz  # PyMuPDF
import subprocess
import requests
import logging
import time
import asyncio
import uuid
from azure.storage.blob import BlobServiceClient
from core.shared_state import conversion_progress

from fastapi import HTTPException, Request, Depends
import tempfile
from database_op.database import get_db
import mysql.connector
from datetime import datetime, timedelta
from helpers.blob_op import generate_sas_token_for_file
from helpers.blob_op import upload_to_blob
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Azure Blob settings from environment variables
# We're using these to store all our files in the cloud
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_BLOB_CONTAINER_NAME = "slide-pull-main"

# Create a thread pool for running LibreOffice conversions
# This limits the number of concurrent LibreOffice processes
# to prevent resource exhaustion
libreoffice_pool = ThreadPoolExecutor(max_workers=2)

# Create a thread pool for image processing and uploads
# This allows multiple images to be processed concurrently
image_pool = ThreadPoolExecutor(max_workers=4)

async def convert_pptx_bytes_to_pdf(pptx_bytes, request: Request):
    """
    Takes a PowerPoint file in memory and converts it to PDF using LibreOffice.
    
    This is the first step in our conversion pipeline. We take the uploaded .pptx,
    save it temporarily to disk (since LibreOffice needs a file path), convert it,
    and then read the PDF back into memory.
    
    This function is now truly asynchronous and won't block other requests.
    
    Note: Only .pptx format is fully supported. Other formats like .odt are not
    currently supported.
    """
    try:
        # Create a buffer for our PowerPoint file
        pptx_in_memory = io.BytesIO(pptx_bytes)

        # Create a unique ID for this conversion to avoid conflicts
        conversion_id = str(uuid.uuid4())
        
        # We need to use a temp directory since LibreOffice works with files on disk
        # Each conversion gets its own unique temp directory
        temp_dir = tempfile.mkdtemp(prefix=f"conversion_{conversion_id}_")
        
        try:
            # Set up our temporary file paths with unique names
            temp_pptx_path = os.path.join(temp_dir, f"{conversion_id}.pptx")
            temp_pdf_path = os.path.join(temp_dir, f"{conversion_id}.pdf")

            # Save the PowerPoint to disk temporarily
            with open(temp_pptx_path, "wb") as f:
                f.write(pptx_in_memory.getbuffer())

            # Find LibreOffice on this system
            soffice_path = os.getenv("SOFFICE_PATH", r'C:\Program Files\LibreOffice\program\soffice.exe')

            # Get the size of the PowerPoint file to estimate conversion time
            pptx_size_mb = os.path.getsize(temp_pptx_path) / (1024 * 1024)
            
            # Estimate timeout based on file size and available resources
            # For low-resource environments, we need to allow more time
            # Base timeout of 120 seconds + 30 seconds per MB
            estimated_timeout = 120 + (pptx_size_mb * 30)
            
            # Cap the timeout at a reasonable maximum (10 minutes)
            timeout = min(estimated_timeout, 600)
            
            logger.info(f"Converting PPTX to PDF (ID: {conversion_id}, size: {pptx_size_mb:.2f} MB, timeout: {timeout:.0f} seconds)")

            # Run LibreOffice in headless mode to do the conversion
            # This is way faster than using COM automation or other methods
            try:
                # Use a unique user profile for each conversion to avoid conflicts
                user_profile_dir = os.path.join(temp_dir, "userprofile")
                os.makedirs(user_profile_dir, exist_ok=True)
                
                # Normalize paths to avoid issues with backslashes in Windows
                temp_dir_normalized = temp_dir.replace('\\', '/')
                temp_pptx_path_normalized = temp_pptx_path.replace('\\', '/')
                user_profile_dir_normalized = user_profile_dir.replace('\\', '/')
                
                # Prepare the command
                cmd = [
                    soffice_path, 
                    '--headless', 
                    '--convert-to', 'pdf', 
                    temp_pptx_path_normalized, 
                    '--outdir', temp_dir_normalized
                ]
                
                # Only add user profile on Windows to avoid issues
                if os.name == 'nt':  # Windows
                    cmd.append('-env:UserInstallation=file:///' + user_profile_dir_normalized)
                else:  # Linux/Mac
                    cmd.append('-env:UserInstallation=file://' + user_profile_dir_normalized)
                
                # Run the conversion asynchronously using the thread pool
                # This prevents blocking the event loop while LibreOffice runs
                def run_libreoffice():
                    logger.info(f"Running LibreOffice command: {' '.join(cmd)}")
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    try:
                        stdout, stderr = process.communicate(timeout=timeout)
                        stdout_text = stdout.decode('utf-8', errors='ignore')
                        stderr_text = stderr.decode('utf-8', errors='ignore')
                        
                        logger.info(f"LibreOffice stdout: {stdout_text}")
                        
                        if process.returncode != 0:
                            logger.error(f"LibreOffice conversion failed with code {process.returncode}: {stderr_text}")
                            raise Exception(f"LibreOffice conversion failed with code {process.returncode}")
                        
                        logger.info(f"LibreOffice conversion completed successfully")
                        return True
                    except subprocess.TimeoutExpired:
                        process.kill()
                        logger.error(f"LibreOffice conversion timed out after {timeout} seconds")
                        raise Exception(f"The presentation took too long to convert. This may be due to its size or complexity.")
                
                # Try the conversion with the primary method
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        libreoffice_pool, 
                        run_libreoffice
                    )
                except Exception as primary_error:
                    logger.warning(f"Primary conversion method failed: {primary_error}. Trying fallback method...")
                    
                    # Fallback method with simpler command
                    fallback_cmd = [
                        soffice_path,
                        '--headless',
                        '--convert-to',
                        'pdf',
                        '--outdir',
                        temp_dir_normalized,
                        temp_pptx_path_normalized
                    ]
                    
                    def run_fallback():
                        logger.info(f"Running fallback LibreOffice command: {' '.join(fallback_cmd)}")
                        process = subprocess.Popen(
                            fallback_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )
                        try:
                            stdout, stderr = process.communicate(timeout=timeout)
                            stdout_text = stdout.decode('utf-8', errors='ignore')
                            stderr_text = stderr.decode('utf-8', errors='ignore')
                            
                            logger.info(f"Fallback LibreOffice stdout: {stdout_text}")
                            
                            if process.returncode != 0:
                                logger.error(f"Fallback LibreOffice conversion failed with code {process.returncode}: {stderr_text}")
                                raise Exception(f"Both conversion methods failed. Original error: {primary_error}. Fallback error: LibreOffice conversion failed with code {process.returncode}")
                            
                            logger.info(f"Fallback LibreOffice conversion completed successfully")
                            return True
                        except subprocess.TimeoutExpired:
                            process.kill()
                            logger.error(f"Fallback LibreOffice conversion timed out after {timeout} seconds")
                            raise Exception(f"Both conversion methods failed. Original error: {primary_error}. Fallback error: The presentation took too long to convert.")
                    
                    try:
                        # Run the fallback conversion
                        await asyncio.get_event_loop().run_in_executor(
                            libreoffice_pool, 
                            run_fallback
                        )
                    except Exception as fallback_error:
                        logger.warning(f"Fallback conversion method failed: {fallback_error}. Trying last resort method...")
                        
                        # Last resort method - direct conversion without user profile
                        last_resort_cmd = [
                            soffice_path,
                            '--headless',
                            '--norestore',
                            '--nologo',
                            '--nolockcheck',
                            '--convert-to',
                            'pdf',
                            temp_pptx_path_normalized
                        ]
                        
                        def run_last_resort():
                            logger.info(f"Running last resort LibreOffice command: {' '.join(last_resort_cmd)}")
                            # Create a new temporary directory for the output
                            output_dir = os.path.dirname(temp_pptx_path)
                            
                            process = subprocess.Popen(
                                last_resort_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                cwd=output_dir  # Set the working directory to control output location
                            )
                            try:
                                stdout, stderr = process.communicate(timeout=timeout)
                                stdout_text = stdout.decode('utf-8', errors='ignore')
                                stderr_text = stderr.decode('utf-8', errors='ignore')
                                
                                logger.info(f"Last resort LibreOffice stdout: {stdout_text}")
                                
                                if process.returncode != 0:
                                    logger.error(f"Last resort LibreOffice conversion failed with code {process.returncode}: {stderr_text}")
                                    raise Exception(f"All conversion methods failed. Original error: {primary_error}. Fallback error: {fallback_error}. Last resort error: LibreOffice conversion failed with code {process.returncode}")
                                
                                logger.info(f"Last resort LibreOffice conversion completed successfully")
                                return True
                            except subprocess.TimeoutExpired:
                                process.kill()
                                logger.error(f"Last resort LibreOffice conversion timed out after {timeout} seconds")
                                raise Exception(f"All conversion methods failed. Original error: {primary_error}. Fallback error: {fallback_error}. Last resort error: The presentation took too long to convert.")
                        
                        # Run the last resort conversion
                        await asyncio.get_event_loop().run_in_executor(
                            libreoffice_pool, 
                            run_last_resort
                        )
                
            except Exception as e:
                logger.error(f"Error during LibreOffice conversion: {str(e)}")
                raise e

            # Check if the PDF was actually created
            # The output filename might be different from what we expect
            pdf_files = [f for f in os.listdir(temp_dir) if f.endswith('.pdf')]
            if not pdf_files:
                logger.error("PDF file was not created by LibreOffice")
                raise Exception("Failed to convert PPTX to PDF: Output file was not created")
            
            # Use the first PDF file found
            temp_pdf_path = os.path.join(temp_dir, pdf_files[0])

            # Read the converted PDF back into memory
            with open(temp_pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()

            return pdf_data

        finally:
            # Clean up the temporary directory and all its contents
            # This is important to prevent disk space issues
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up temporary directory: {cleanup_error}")

    except subprocess.CalledProcessError as e:
        # This happens if LibreOffice fails to convert the file
        logger.error(f"LibreOffice conversion failed: {e}")
        raise Exception(f"Failed to convert PPTX to PDF: {e}")
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"Unexpected error during conversion: {e}")
        raise Exception(f"Unexpected error during conversion: {e}")

# Dictionary to track conversion progress
conversion_progress = {}

async def convert_pdf_to_slides_and_thumbnails(pdf_blob_name, user_alias, pdf_id, sas_token_pdf, db):
    """
    Takes a PDF stored in Azure Blob Storage. For each page:
    1. Extracts the page as a new 1-page PDF file.
    2. Creates a smaller thumbnail image of the page.
    3. Uploads both the 1-page PDF and the thumbnail image to Azure.
    4. Stores references in the database:
        - 1-page PDFs in 'slide_file' table (type='pdf').
        - Thumbnails in 'thumbnail' table, linking to the 'slide_file' entry of the 1-page PDF.
    
    Progress is tracked.
    """
    # Thumbnail generation settings
    thumbnail_zoom_x = 0.75 
    thumbnail_zoom_y = 0.75 
    thumbnail_matrix = fitz.Matrix(thumbnail_zoom_x, thumbnail_zoom_y)
    thumbnail_width_target = 300 # Target width for thumbnail images
    
    # Initialize progress tracking
    str_pdf_id = str(pdf_id)
    conversion_progress[str_pdf_id] = {
        "total": 0,
        "current": 0,
        "status": "initializing"
    }

    cursor = None
    try:
        cursor = db.cursor(dictionary=True, buffered=True)

        # Azure Blob Storage paths
        slide_pdf_blob_base = f"{user_alias}/slide_pdfs/{pdf_id}/slide_" # New path for 1-page PDFs
        thumbnail_blob_base = f"{user_alias}/thumbnails/{pdf_id}/thumb_" # Path for thumbnails

        # Build the URL to download the main PDF from Azure
        pdf_blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}"
        pdf_blob_url_with_sas = f"{pdf_blob_url}?{sas_token_pdf}"

        logger.info(f"Downloading PDF from Azure: {pdf_blob_url}")
        conversion_progress[str_pdf_id]["status"] = "downloading_pdf"

        # Download the PDF file asynchronously
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(pdf_blob_url_with_sas) as response:
                response.raise_for_status()  # Will raise an exception for HTTP errors
                pdf_bytes = await response.read()
                
        if not pdf_bytes:
            conversion_progress[str_pdf_id]["status"] = "error"
            raise Exception("Downloaded PDF is empty - check the source file")

        # Open the PDF with PyMuPDF
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # Update progress with total number of pages
        total_pages = len(pdf_document)
        conversion_progress[str_pdf_id]["total"] = total_pages
        conversion_progress[str_pdf_id]["status"] = "processing_slides"
        logger.info(f"Processing {total_pages} pages from PDF {pdf_id} for user {user_alias}")

        for page_number in range(total_pages):
            conversion_progress[str_pdf_id]["current"] = page_number + 1
            page = pdf_document.load_page(page_number)

            # 1. Create and store 1-page PDF for the current slide
            slide_pdf_doc = fitz.open()  # New empty PDF
            slide_pdf_doc.insert_pdf(pdf_document, from_page=page_number, to_page=page_number)
            # Apply mediabox from original page to ensure consistent sizing
            # slide_pdf_doc[0].set_mediabox(page.mediabox) # This might not be needed if insert_pdf handles it
            slide_pdf_bytes = slide_pdf_doc.tobytes(garbage=4, deflate=True, clean=True) # Use maximum garbage collection
            slide_pdf_doc.close()
            
            slide_pdf_blob_name = f"{slide_pdf_blob_base}{page_number + 1}.pdf"
            slide_pdf_url, sas_token_slide_pdf, sas_token_slide_pdf_expiry = await asyncio.get_event_loop().run_in_executor(
                image_pool, # Reusing image_pool for I/O bound tasks
                lambda: upload_to_blob(slide_pdf_blob_name, slide_pdf_bytes, "application/pdf", user_alias)
            )
            
            cursor.execute(
                "INSERT INTO slide_file (pdf_id, url, sas_token, sas_token_expiry, file_type, slide_number) VALUES (%s, %s, %s, %s, 'pdf', %s)",
                (pdf_id, slide_pdf_url, sas_token_slide_pdf, sas_token_slide_pdf_expiry, page_number + 1)
            )
            slide_file_id_for_pdf = cursor.lastrowid # This ID represents the 1-page slide PDF

            # 2. Create and store thumbnail for the current slide
            # Generate pixmap for thumbnail
            pix = page.get_pixmap(matrix=thumbnail_matrix) # Use the predefined thumbnail_matrix
            
            # Scale to target width if necessary (PyMuPDF might not have a direct scale to width)
            # Instead, create pixmap with good resolution and then resize if using PIL, or adjust zoom.
            # For simplicity, using a fixed zoom for thumbnails for now.
            # If pix.width > thumbnail_width_target:
            #    scale_factor = thumbnail_width_target / pix.width
            #    thumb_matrix_adjusted = fitz.Matrix(scale_factor, scale_factor)
            #    thumbnail_pix = page.get_pixmap(matrix=thumb_matrix_adjusted)
            # else:
            #    thumbnail_pix = pix 
            thumbnail_pix = page.get_pixmap(matrix=fitz.Matrix(thumbnail_width_target/page.rect.width, thumbnail_width_target/page.rect.width) if page.rect.width > 0 else thumbnail_matrix)


            thumbnail_bytes = thumbnail_pix.tobytes("png")
            
            thumbnail_blob_name = f"{thumbnail_blob_base}{page_number + 1}.png"
            thumbnail_url, sas_token_thumbnail, sas_token_thumbnail_expiry = await asyncio.get_event_loop().run_in_executor(
                image_pool,
                lambda: upload_to_blob(thumbnail_blob_name, thumbnail_bytes, "image/png", user_alias)
            )
            
            # Insert into thumbnail table, linking to the slide_file_id of the 1-page PDF
            cursor.execute(
                "INSERT INTO thumbnail (image_id, pdf_id, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s, %s)",
                (slide_file_id_for_pdf, pdf_id, thumbnail_url, sas_token_thumbnail, sas_token_thumbnail_expiry)
            )
            
            db.commit()
            logger.info(f"Processed slide {page_number + 1}/{total_pages} for PDF {pdf_id}: 1-page PDF and thumbnail created.")

        conversion_progress[str_pdf_id]["status"] = "complete"
        pdf_document.close()
        return total_pages

    except Exception as e:
        error_message = f"Error processing PDF slides and thumbnails for PDF {pdf_id}: {type(e).__name__} - {str(e)}"
        logger.error(error_message)
        if cursor: # Check if cursor was initialized
            try:
                db.rollback()
            except Exception as rollback_err:
                logger.error(f"Error during rollback for PDF {pdf_id}: {rollback_err}")
        
        if str_pdf_id in conversion_progress:
            conversion_progress[str_pdf_id]["status"] = "error"
            
        raise Exception(error_message)
    finally:
        # Always close the database cursor
        if cursor:
            try:
                cursor.close()
            except Exception as cursor_err:
                logger.error(f"Error closing cursor: {cursor_err}")
