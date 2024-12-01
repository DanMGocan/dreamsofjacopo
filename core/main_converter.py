
import os
import io
import fitz  # PyMuPDF
import subprocess
import requests
from azure.storage.blob import BlobServiceClient
from fastapi import HTTPException, Request, Depends
import tempfile
from database_op.database import get_db
import mysql.connector
from datetime import datetime, timedelta
from helpers.blob_op import generate_sas_token_for_file

from helpers.blob_op import upload_to_blob

# Azure Blob settings (replace these with your actual connection string and container name)
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_BLOB_CONTAINER_NAME = "slide-pull-main"

# Function to convert in-memory .pptx bytes to PDF bytes using LibreOffice
def convert_pptx_bytes_to_pdf(pptx_bytes, request: Request):
    try:
        # Create in-memory buffers for input (.pptx) and output (.pdf)
        pptx_in_memory = io.BytesIO(pptx_bytes)

        # Create a temporary directory for storing files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Define temporary file paths for PPTX and PDF inside the temporary directory
            temp_pptx_path = os.path.join(temp_dir, "temp_presentation.pptx")
            temp_pdf_path = os.path.join(temp_dir, "temp_presentation.pdf")

            # Write the PPTX to the temporary path
            with open(temp_pptx_path, "wb") as f:
                f.write(pptx_in_memory.getbuffer())

            # Get LibreOffice path (adjust for your environment)
            soffice_path = os.getenv("SOFFICE_PATH", r'C:\Program Files\LibreOffice\program\soffice.exe')

            # Run LibreOffice command to convert PPTX to PDF in memory
            subprocess.run([soffice_path, '--headless', '--convert-to', 'pdf', temp_pptx_path, '--outdir', temp_dir], check=True, timeout=120)

            # Read the PDF file as bytes
            with open(temp_pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()

            return pdf_data

    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to convert PPTX to PDF: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error: {e}")

def convert_pdf_to_images(pdf_blob_name, user_alias, pdf_id, sas_token_pdf, db):
    # Adjust the quality of the image 
    zoom_x = 2.0  # Horizontal scaling factor (e.g., 2.0 for 200% resolution)
    zoom_y = 2.0  # Vertical scaling factor
    matrix = fitz.Matrix(zoom_x, zoom_y)  # Create a scaling matrix

    try:
        cursor = db.cursor(dictionary=True, buffered=True)

        # Define the base blob names for images and thumbnails
        image_blob_base = f"{user_alias}/images/{pdf_id}/slide_"
        thumbnail_blob_base = f"{user_alias}/thumbnails/{pdf_id}/slide_"

        # Construct the download URL for the PDF using the SAS token
        pdf_blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{pdf_blob_name}"
        pdf_blob_url_with_sas = f"{pdf_blob_url}?{sas_token_pdf}"

        print(f"Downloading PDF from URL: {pdf_blob_url_with_sas}")

        # Download the PDF bytes using the SAS URL
        response = requests.get(pdf_blob_url_with_sas)
        response.raise_for_status()
        pdf_bytes = response.content
        if not pdf_bytes:
            raise Exception("Failed to download PDF content")

        # Open the PDF from in-memory bytes using PyMuPDF (fitz)
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Set desired thumbnail width
        thumbnail_width = 300  # Adjust as needed

        # Convert each page to an image and upload
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            pix = page.get_pixmap(matrix=matrix)  # Render the page with the scaling matrix

            # Get full-size image bytes
            image_bytes = pix.tobytes("png")

            # Define blob name for the current image
            image_blob_name = f"{image_blob_base}{page_number + 1}.png"

            # Upload full-size image to Azure Blob Storage
            image_url, sas_token_image, sas_token_expiry = upload_to_blob(
                image_blob_name, image_bytes, "image/png", user_alias
            )

            # Insert image record into database
            cursor.execute(
                "INSERT INTO image (pdf_id, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s)",
                (pdf_id, image_url, sas_token_image, sas_token_expiry)
            )
            image_id = cursor.lastrowid  # Get the inserted image_id

            # Generate thumbnail
            # Calculate scaling factor
            scale = thumbnail_width / pix.width
            # Create scaling matrix for thumbnail
            thumbnail_matrix = fitz.Matrix(scale, scale)
            # Generate thumbnail pixmap using the matrix
            thumbnail_pix = page.get_pixmap(matrix=thumbnail_matrix)
            # Get thumbnail bytes
            thumbnail_bytes = thumbnail_pix.tobytes("png")

            # Define blob name for the thumbnail
            thumbnail_blob_name = f"{thumbnail_blob_base}{page_number + 1}.png"

            # Upload thumbnail to Azure Blob Storage
            thumbnail_url, sas_token_thumbnail, sas_token_thumbnail_expiry = upload_to_blob(
                thumbnail_blob_name, thumbnail_bytes, "image/png", user_alias
            )

            # Insert thumbnail record into database
            cursor.execute(
                "INSERT INTO thumbnail (image_id, pdf_id, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s, %s)",
                (image_id, pdf_id, thumbnail_url, sas_token_thumbnail, sas_token_thumbnail_expiry)
            )

        db.commit()

        # Close the PDF document
        pdf_document.close()

        return "Images and thumbnails converted and uploaded successfully!"

    except Exception as e:
        db.rollback()
        raise Exception(f"Error converting PDF to images: {e}")
    finally:
        cursor.close()








