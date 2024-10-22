# import subprocess
# import os
# import fitz  # PyMuPDF
# from fastapi import HTTPException

# # Convert PPTX to PDF using LibreOffice
# def convert_pptx_to_pdf(pptx_path, output_dir):
#     try:
#         # Define the output PDF path
#         pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(pptx_path))[0] + '.pdf')
        
#         # Ensure output directory exists
#         os.makedirs(output_dir, exist_ok=True)

#         # Get LibreOffice path
#         soffice_path = os.getenv("SOFFICE_PATH", r'C:\Program Files\LibreOffice\program\soffice.exe')
        
#         # Run LibreOffice command to convert PPTX to PDF
#         subprocess.run([soffice_path, '--headless', '--convert-to', 'pdf', pptx_path, '--outdir', output_dir], check=True, timeout=120)

#         # Check if the PDF was created
#         if os.path.exists(pdf_path):
#             print(f"PDF created successfully: {pdf_path}")
#         else:
#             print(f"PDF creation failed: {pdf_path}")

#         return pdf_path

#     except subprocess.CalledProcessError as e:
#         raise Exception(f"Failed to convert PPTX to PDF: {e}")
#     except Exception as e:
#         raise Exception(f"Unexpected error: {e}")


# # Convert the generated PDF to images
# def convert_pdf_to_images(pdf_path, output_dir):
# # Same function with Zoom applied to increase resolution     
# # def convert_pdf_to_images(pdf_path, output_dir, zoom_x=2.0, zoom_y=2.0):

#     try:
#         # Open the PDF file
#         pdf_document = fitz.open(pdf_path)
#         os.makedirs(output_dir, exist_ok=True)

#         image_paths = []

#         for page_number in range(len(pdf_document)):
#             page = pdf_document.load_page(page_number)

#             # Apply zoom to increase resolution
#             # mat = fitz.Matrix(zoom_x, zoom_y)  # Control resolution here
#             # pixmap = page.get_pixmap(matrix=mat)
#             # Also, delete next line to make this work 
#             image = page.get_pixmap()
#             image_path = os.path.join(output_dir, f"slide_{page_number + 1}.png")
#             image.save(image_path)

#             # Check if the file was successfully saved
#             if os.path.exists(image_path):
#                 print(f"Image saved successfully: {image_path}")
#             else:
#                 print(f"Image creation failed: {image_path}")

#             image_paths.append(image_path)

#         pdf_document.close()
#         return image_paths

#     except Exception as e:
#         raise Exception(f"Error converting PDF to images: {e}")


#     except subprocess.CalledProcessError as e:
#         raise Exception(f"Failed to convert PPTX to PDF: {e}")
#     except Exception as e:
#         raise Exception(f"Unexpected error: {e}")



# # Main conversion function (if needed)
# def convert_pptx(input_pptx):
#     try:
#         output_dir = os.path.dirname(input_pptx)

#         # Convert PPTX to PDF
#         pdf_path = convert_pptx_to_pdf(input_pptx, output_dir)
#         print(f"{pdf_path} pdf path")

#         # Convert PDF to images
#         image_paths = convert_pdf_to_images(pdf_path, output_dir)

#         return {"message": "Conversion successful", "image_paths": image_paths}

#     except Exception as e:
#         raise Exception(f"Conversion process failed: {e}")


# ##################################################################################

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
        thumbnail_width = 200  # Adjust as needed

        # Convert each page to an image and upload
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            pix = page.get_pixmap()

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

            # Generate thumbnail
            # Calculate scaling factor
            scale = thumbnail_width / pix.width
            # Create scaling matrix
            matrix = fitz.Matrix(scale, scale)
            # Generate thumbnail pixmap using the matrix
            thumbnail_pix = page.get_pixmap(matrix=matrix)
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
                "INSERT INTO thumbnail (pdf_id, url, sas_token, sas_token_expiry) VALUES (%s, %s, %s, %s)",
                (pdf_id, thumbnail_url, sas_token_thumbnail, sas_token_thumbnail_expiry)
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






