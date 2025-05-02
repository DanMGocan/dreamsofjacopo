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

async def convert_pdf_to_images(pdf_blob_name, user_alias, pdf_id, sas_token_pdf, db):
    """
    Takes a PDF stored in Azure Blob Storage and converts each page to images and thumbnails.
    
    This is the second step in our conversion pipeline. We:
    1. Download the PDF from Azure
    2. Convert each page to a high-quality image
    3. Create a smaller thumbnail version of each image
    4. Upload both to Azure and store references in the database
    
    The thumbnails are what users will see when selecting slides to include in a set.
    
    Progress is tracked and can be accessed via the conversion_progress dictionary.
    
    This function is now asynchronous and won't block other requests.
    """
    # Set up image quality - we use 2x scaling for high-res images
    # This makes text crisp and readable even when zoomed in
    zoom_x = 0.75 # 200% resolution horizontally
    zoom_y = 0.75 # 200% resolution vertically
    matrix = fitz.Matrix(zoom_x, zoom_y)  # PyMuPDF scaling matrix
    
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

        # Set up our file paths in Azure - we organize by user and presentation
        image_blob_base = f"{user_alias}/images/{pdf_id}/slide_"
        thumbnail_blob_base = f"{user_alias}/thumbnails/{pdf_id}/slide_"

        # Build the URL to download the PDF from Azure
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
        conversion_progress[str_pdf_id]["status"] = "processing"
        logger.info(f"Processing {total_pages} pages from PDF")

        # We'll make thumbnails 300px wide - good balance of size and quality
        thumbnail_width = 300

        # Process each page of the PDF
        for page_number in range(total_pages):
            # Update progress (using 1-based indexing for better user display)
            conversion_progress[str_pdf_id]["current"] = page_number + 1
            
            # Load the page and render it at high quality
            page = pdf_document.load_page(page_number)
            pix = page.get_pixmap(matrix=matrix)
            
            # Convert the page to a PNG image
            image_bytes = pix.tobytes("png")
            
            # Name the image file based on slide number
            image_blob_name = f"{image_blob_base}{page_number + 1}.png"
            
            # Upload the full-size image to Azure asynchronously
            # We'll use a thread pool for this since upload_to_blob is not async
            image_url, sas_token_image, sas_token_expiry = await asyncio.get_event_loop().run_in_executor(
                image_pool,
                lambda: upload_to_blob(image_blob_name, image_bytes, "image/png", user_alias)
            )
            
            # Save the image info to our database
            cursor.execute(
                "INSERT INTO image (pdf_id, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s)",
                (pdf_id, image_url, sas_token_image, sas_token_expiry)
            )
            image_id = cursor.lastrowid
            
            # Now create a thumbnail version of the same image
            # Calculate how much to scale down to get our target width
            scale = thumbnail_width / pix.width
            thumbnail_matrix = fitz.Matrix(scale, scale)
            
            # Generate the smaller thumbnail image
            thumbnail_pix = page.get_pixmap(matrix=thumbnail_matrix)
            thumbnail_bytes = thumbnail_pix.tobytes("png")
            
            # Name and upload the thumbnail asynchronously
            thumbnail_blob_name = f"{thumbnail_blob_base}{page_number + 1}.png"
            thumbnail_url, sas_token_thumbnail, sas_token_thumbnail_expiry = await asyncio.get_event_loop().run_in_executor(
                image_pool,
                lambda: upload_to_blob(thumbnail_blob_name, thumbnail_bytes, "image/png", user_alias)
            )
            
            # Save the thumbnail info to our database
            cursor.execute(
                "INSERT INTO thumbnail (image_id, pdf_id, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s, %s)",
                (image_id, pdf_id, thumbnail_url, sas_token_thumbnail, sas_token_thumbnail_expiry)
            )
            
            # Commit after each page to avoid losing work if there's an error
            db.commit()
            
            logger.info(f"Processed page {page_number + 1}/{total_pages}")

        # Update progress to complete
        conversion_progress[str_pdf_id]["current"] = total_pages
        conversion_progress[str_pdf_id]["status"] = "complete"
        
        # Clean up
        pdf_document.close()

        # Return the total number of pages
        return total_pages

    except Exception as e:
        # If anything goes wrong, undo any partial database changes
        logger.error(f"Error converting PDF to images: {e}")
        try:
            db.rollback()
        except Exception as rollback_err:
            logger.error(f"Error during rollback: {rollback_err}")
        
        # Update progress with error
        if str_pdf_id in conversion_progress:
            conversion_progress[str_pdf_id]["status"] = "error"
            
        raise Exception(f"Error converting PDF to images: {e}")
    finally:
        # Always close the database cursor
        if cursor:
            try:
                cursor.close()
            except Exception as cursor_err:
                logger.error(f"Error closing cursor: {cursor_err}")
