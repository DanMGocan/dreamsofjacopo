from fastapi import APIRouter, UploadFile, File
from core import main_converter, qr_generator
from fastapi.responses import JSONResponse
import os

router = APIRouter()

@router.post("/upload-pptx")
async def upload_pptx(pptx_file: UploadFile = File(...)):
    return main_converter(pptx_file)

    try:
        # Step 1: Save the uploaded file temporarily
        file_location = f"{TEMP_DIR}{pptx_file.filename}"
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(pptx_file.file, file_object)

        # Step 2: Convert PPTX to PDF
        pdf_path = convert_pptx_to_pdf(file_location, TEMP_DIR)

        # Step 3: Convert PDF to images
        images_output_dir = f"{TEMP_DIR}images/"
        os.makedirs(images_output_dir, exist_ok=True)
        main_converter.convert_pdf_to_images(pdf_path, images_output_dir)

        # Step 4: Upload PDF to Azure Blob Storage
        pdf_blob_url = upload_to_azure(pdf_path, os.path.basename(pdf_path))

        # Step 5: Upload images to Azure Blob Storage
        image_blob_urls = []
        for image_file in os.listdir(images_output_dir):
            image_path = os.path.join(images_output_dir, image_file)
            image_blob_url = upload_to_azure(image_path, f"images/{image_file}")
            image_blob_urls.append(image_blob_url)

        # Step 6: Store metadata (PDF and images URLs)
        store_metadata_in_db(pptx_file.filename, pdf_blob_url, image_blob_urls)

        # Step 7: Clean up - delete original pptx, PDF, and images
        os.remove(file_location)  # Delete the original PPTX file
        os.remove(pdf_path)  # Delete the PDF file
        shutil.rmtree(images_output_dir)  # Delete the images directory

        return {
            "message": "File uploaded and processed successfully!",
            "pdf_url": pdf_blob_url,
            "image_urls": image_blob_urls
        }

    except Exception as e:
        return {"error": f"Failed to process file: {str(e)}"}