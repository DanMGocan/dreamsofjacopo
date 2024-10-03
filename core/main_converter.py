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
from azure.storage.blob import BlobServiceClient
from fastapi import HTTPException

# Azure Blob settings (replace these with your actual connection string and container name)
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_BLOB_CONTAINER_NAME = "slide-pull-main"

# Helper function to upload a file to Azure Blob Storage (from in-memory bytes)
def upload_to_blob(blob_name, data, content_type):
    try:
        # Create BlobServiceClient
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        blob_client = blob_service_client.get_blob_client(container=AZURE_BLOB_CONTAINER_NAME, blob=blob_name)

        # Upload data to blob (in-memory data as bytes)
        blob_client.upload_blob(data, blob_type="BlockBlob", content_settings={"content_type": content_type}, overwrite=True)
        
        # Return the URL to the uploaded blob
        blob_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER_NAME}/{blob_name}"
        print(f"Uploaded to Azure Blob: {blob_url}")
        return blob_url

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file to Azure Blob Storage: {e}")

# Convert PPTX to PDF using LibreOffice and upload the result to Azure Blob
def convert_pptx_to_pdf(pptx_blob_url, user_alias, presentation_id):
    try:
        # Define the output PDF blob name
        pdf_blob_name = f"{user_alias}/pdf/{presentation_id}/presentation.pdf"

        # Download PPTX from Azure Blob Storage (fetch in-memory)
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        pptx_blob_client = blob_service_client.get_blob_client(container=AZURE_BLOB_CONTAINER_NAME, blob=pptx_blob_url)
        pptx_bytes = pptx_blob_client.download_blob().readall()

        # Write PPTX bytes to temporary in-memory file
        temp_pptx_path = "/tmp/temp_presentation.pptx"
        with open(temp_pptx_path, "wb") as f:
            f.write(pptx_bytes)

        # Define the temporary output path for PDF
        temp_pdf_path = "/tmp/temp_presentation.pdf"

        # Get LibreOffice path
        soffice_path = os.getenv("SOFFICE_PATH", r'C:\Program Files\LibreOffice\program\soffice.exe')

        # Run LibreOffice command to convert PPTX to PDF
        subprocess.run([soffice_path, '--headless', '--convert-to', 'pdf', temp_pptx_path, '--outdir', "/tmp"], check=True, timeout=120)

        # Check if PDF was created
        if not os.path.exists(temp_pdf_path):
            raise Exception("PDF creation failed")

        # Read the PDF file as bytes
        with open(temp_pdf_path, "rb") as pdf_file:
            pdf_data = pdf_file.read()

        # Upload PDF to Azure Blob Storage
        pdf_url = upload_to_blob(pdf_blob_name, pdf_data, "application/pdf")
        
        return pdf_url

    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to convert PPTX to PDF: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error: {e}")

# Convert the generated PDF to images (in-memory processing)
def convert_pdf_to_images(pdf_blob_url, user_alias, presentation_id):
    try:
        # Define the base blob name for images
        image_blob_base = f"{user_alias}/images/{presentation_id}/slide_"

        # Download PDF from Azure Blob Storage (in-memory)
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        pdf_blob_client = blob_service_client.get_blob_client(container=AZURE_BLOB_CONTAINER_NAME, blob=pdf_blob_url)
        pdf_bytes = pdf_blob_client.download_blob().readall()

        # Open the PDF from in-memory bytes
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

        image_urls = []

        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            image = page.get_pixmap()

            # Save the image in-memory (to be uploaded to Azure Blob Storage)
            image_bytes = io.BytesIO()
            image.save(image_bytes, format="PNG")
            image_bytes.seek(0)

            # Define blob name for the current image
            image_blob_name = f"{image_blob_base}{page_number + 1}.png"

            # Upload image to Azure Blob Storage
            image_url = upload_to_blob(image_blob_name, image_bytes.getvalue(), "image/png")
            image_urls.append(image_url)

        pdf_document.close()
        return image_urls

    except Exception as e:
        raise Exception(f"Error converting PDF to images: {e}")

# Main conversion function (entire process in-memory)
def convert_pptx(input_pptx_blob_url, user_alias, presentation_id):
    try:
        # Convert PPTX to PDF and upload the PDF to Azure Blob Storage
        pdf_url = convert_pptx_to_pdf(input_pptx_blob_url, user_alias, presentation_id)

        # Convert PDF to images and upload images to Azure Blob Storage
        image_urls = convert_pdf_to_images(pdf_url, user_alias, presentation_id)

        return {"message": "Conversion successful", "pdf_url": pdf_url, "image_urls": image_urls}

    except Exception as e:
        raise Exception(f"Conversion process failed: {e}")
