###############################################################################
# Functions pertaining to the conversion of .pptx files into images. ##########
###############################################################################


import subprocess
import os
import fitz  # PyMuPDF
import time
import psutil
from fastapi import HTTPException

# Convert PPTX to PDF using LibreOffice
def convert_pptx_to_pdf(pptx_path, output_dir):
    try:

        # This needs to be changed out to the cloud
        # Define the output PDF path
        pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(pptx_path))[0] + '.pdf')
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Specify the full path to soffice.exe (can be moved to an env variable or config)
        soffice_path = os.getenv("SOFFICE_PATH", r'C:\Program Files\LibreOffice\program\soffice.exe')
        
        # Run LibreOffice command to convert PPTX to PDF
        subprocess.run([soffice_path, '--headless', '--convert-to', 'pdf', pptx_path, '--outdir', output_dir], check=True)

        return pdf_path

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert PPTX to PDF: {e}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")

# Convert the generated PDF to images
def convert_pdf_to_images(pdf_path, output_dir):
    try:  
        # Open the PDF file
        pdf_document = fitz.open(pdf_path)
        
        os.makedirs(output_dir, exist_ok=True)

        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            image = page.get_pixmap()
            image_path = os.path.join(output_dir, f"slide_{page_number + 1}.png")
            image.save(image_path)
        
        pdf_document.close()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error converting PDF to images: {e}")

# Main conversion function (callable in FastAPI)
def convert_pptx(input_pptx):
    try:
        output_dir = os.path.dirname(input_pptx)

        # Convert PPTX to PDF
        pdf_path = convert_pptx_to_pdf(input_pptx, output_dir)

        # Convert PDF to images and get the document length
        doc_length = convert_pdf_to_images(pdf_path, output_dir)

        return {"message": "Conversion successful", "document_length": doc_length}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion process failed: {e}")
