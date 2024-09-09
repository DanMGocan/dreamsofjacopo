import subprocess
import os
import fitz  # PyMuPDF
from fastapi import HTTPException

# Convert PPTX to PDF using LibreOffice
def convert_pptx_to_pdf(pptx_path, output_dir):
    try:
        # Define the output PDF path
        pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(pptx_path))[0] + '.pdf')
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Get LibreOffice path
        soffice_path = os.getenv("SOFFICE_PATH", r'C:\Program Files\LibreOffice\program\soffice.exe')
        
        # Run LibreOffice command to convert PPTX to PDF
        subprocess.run([soffice_path, '--headless', '--convert-to', 'pdf', pptx_path, '--outdir', output_dir], check=True, timeout=120)

        # Check if the PDF was created
        if os.path.exists(pdf_path):
            print(f"PDF created successfully: {pdf_path}")
        else:
            print(f"PDF creation failed: {pdf_path}")

        return pdf_path

    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to convert PPTX to PDF: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error: {e}")


# Convert the generated PDF to images
def convert_pdf_to_images(pdf_path, output_dir):
# Same function with Zoom applied to increase resolution     
# def convert_pdf_to_images(pdf_path, output_dir, zoom_x=2.0, zoom_y=2.0):

    try:
        # Open the PDF file
        pdf_document = fitz.open(pdf_path)
        os.makedirs(output_dir, exist_ok=True)

        image_paths = []

        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)

            # Apply zoom to increase resolution
            # mat = fitz.Matrix(zoom_x, zoom_y)  # Control resolution here
            # pixmap = page.get_pixmap(matrix=mat)
            # Also, delete next line to make this work 
            image = page.get_pixmap()
            image_path = os.path.join(output_dir, f"slide_{page_number + 1}.png")
            image.save(image_path)

            # Check if the file was successfully saved
            if os.path.exists(image_path):
                print(f"Image saved successfully: {image_path}")
            else:
                print(f"Image creation failed: {image_path}")

            image_paths.append(image_path)

        pdf_document.close()
        return image_paths

    except Exception as e:
        raise Exception(f"Error converting PDF to images: {e}")


    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to convert PPTX to PDF: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error: {e}")



# Main conversion function (if needed)
def convert_pptx(input_pptx):
    try:
        output_dir = os.path.dirname(input_pptx)

        # Convert PPTX to PDF
        pdf_path = convert_pptx_to_pdf(input_pptx, output_dir)
        print(f"{pdf_path} pdf path")

        # Convert PDF to images
        image_paths = convert_pdf_to_images(pdf_path, output_dir)

        return {"message": "Conversion successful", "image_paths": image_paths}

    except Exception as e:
        raise Exception(f"Conversion process failed: {e}")
