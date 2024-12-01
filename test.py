import subprocess
import os
import fitz  # PyMuPDF
import csv
import time
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

        if os.path.exists(pdf_path):
            print(f"PDF created successfully: {pdf_path}")
        else:
            raise Exception(f"PDF creation failed: {pdf_path}")

        return pdf_path

    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to convert PPTX to PDF: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error: {e}")

# Convert the generated PDF to images (Standard resolution)
def convert_pdf_to_images(pdf_path, output_dir):
    try:
        pdf_document = fitz.open(pdf_path)
        os.makedirs(output_dir, exist_ok=True)

        image_paths = []
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            image = page.get_pixmap()
            image_path = os.path.join(output_dir, f"slide_{page_number + 1}.png")
            image.save(image_path)
            image_paths.append(image_path)

        return image_paths, len(pdf_document)

    except Exception as e:
        raise Exception(f"Error converting PDF to images: {e}")

# Mid-resolution conversion
def convert_pdf_to_images_mid_resolution(pdf_path, output_dir, zoom_x=1.5, zoom_y=1.5):
    try:
        pdf_document = fitz.open(pdf_path)
        os.makedirs(output_dir, exist_ok=True)

        image_paths = []
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            mat = fitz.Matrix(zoom_x, zoom_y)
            image = page.get_pixmap(matrix=mat)
            image_path = os.path.join(output_dir, f"slide_{page_number + 1}.png")
            image.save(image_path)
            image_paths.append(image_path)

        return image_paths, len(pdf_document)

    except Exception as e:
        raise Exception(f"Error converting PDF to images: {e}")

# Max-resolution conversion
def convert_pdf_to_images_max_resolution(pdf_path, output_dir, zoom_x=2.0, zoom_y=2.0):
    try:
        pdf_document = fitz.open(pdf_path)
        os.makedirs(output_dir, exist_ok=True)

        image_paths = []
        for page_number in range(len(pdf_document)):
            page = pdf_document.load_page(page_number)
            mat = fitz.Matrix(zoom_x, zoom_y)
            image = page.get_pixmap(matrix=mat)
            image_path = os.path.join(output_dir, f"slide_{page_number + 1}.png")
            image.save(image_path)
            image_paths.append(image_path)

        return image_paths, len(pdf_document)

    except Exception as e:
        raise Exception(f"Error converting PDF to images: {e}")

# Record data to CSV with additional logging
def record_conversion_data(csv_path, pptx_filename, num_slides, standard_time, mid_time, max_time):
    try:
        print(f"Attempting to write data to CSV at: {csv_path}")
        print(f"Data being recorded: Filename={pptx_filename}, Slides={num_slides}, Standard Time={standard_time}, Mid Time={mid_time}, Max Time={max_time}")

        file_exists = os.path.isfile(csv_path)
        with open(csv_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            if not file_exists:
                print(f"CSV file not found, creating new file at {csv_path}")
                writer.writerow(['Filename', 'Number of Slides', 'Standard Time (seconds)', 'Mid Time (seconds)', 'Max Time (seconds)'])
            writer.writerow([pptx_filename, num_slides, standard_time, mid_time, max_time])
        print(f"Data for {pptx_filename} recorded successfully in CSV.")
    except Exception as e:
        print(f"Failed to write to CSV: {e}")

# Main conversion function for all PPTX files in a folder
def convert_all_pptx_in_folder(folder_path, output_dir, csv_path):
    for file_name in os.listdir(folder_path):
        if file_name.endswith('.pptx'):
            pptx_path = os.path.join(folder_path, file_name)

            try:
                # Convert PPTX to PDF
                pdf_path = convert_pptx_to_pdf(pptx_path, output_dir)

                # Measure standard resolution conversion time
                start_time = time.time()
                _, num_slides = convert_pdf_to_images(pdf_path, output_dir)
                standard_time = time.time() - start_time

                # Measure mid resolution conversion time
                start_time = time.time()
                convert_pdf_to_images_mid_resolution(pdf_path, output_dir)
                mid_time = time.time() - start_time

                # Measure max resolution conversion time
                start_time = time.time()
                convert_pdf_to_images_max_resolution(pdf_path, output_dir)
                max_time = time.time() - start_time

                # Record the number of slides and individual conversion times
                record_conversion_data(csv_path, file_name, num_slides, standard_time, mid_time, max_time)

            except Exception as e:
                print(f"Error processing file {file_name}: {e}")

# Example usage
folder_path = 'ppts'
output_dir = 'pdfs'
csv_path = 'data_conversion.csv'

convert_all_pptx_in_folder(folder_path, output_dir, csv_path)
