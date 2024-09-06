import subprocess
import os
import fitz  # PyMuPDF
import time
import psutil

def convert_pptx_to_pdf(pptx_path, output_dir):
    start_time = time.time()

    # Define the output PDF path
    pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(pptx_path))[0] + '.pdf')
    
    # Specify the full path to soffice.exe (LibreOffice)
    soffice_path = r'C:\Program Files\LibreOffice\program\soffice.exe'
    
    # Run the LibreOffice command to convert PPTX to PDF
    subprocess.run([soffice_path, '--headless', '--convert-to', 'pdf', pptx_path, '--outdir', output_dir])

    end_time = time.time()
    print(f"convert_pptx_to_pdf execution time: {end_time - start_time:.2f} seconds")
    return pdf_path

def convert_pdf_to_images(pdf_path, output_dir):
    start_time = time.time()
    
    # Open the PDF file
    pdf_document = fitz.open(pdf_path)
    doc_length = len(pdf_document)
    
    for page_number in range(doc_length):
        page = pdf_document.load_page(page_number)
        image = page.get_pixmap()
        image_path = os.path.join(output_dir, f"slide_{page_number + 1}.png")
        image.save(image_path)
    
    pdf_document.close()
    end_time = time.time()

    print(f"convert_pdf_to_images execution time: {end_time - start_time:.2f} seconds")
    
    return doc_length

def monitor_cpu():
    # Capture CPU usage
    cpu_percent = psutil.cpu_percent(interval=1)
    return cpu_percent

def main(input_pptx):
    output_dir = os.path.dirname(input_pptx)

    # Monitor CPU usage before running
    print(f'CPU usage before execution: {monitor_cpu()}%')

    pdf_path = convert_pptx_to_pdf(input_pptx, output_dir)

    # Capture exec_time and doc_length
    doc_length = convert_pdf_to_images(pdf_path, output_dir)

    # Monitor CPU usage after running
    print(f'CPU usage after execution: {monitor_cpu()}%')

    # Print the execution time and document length
    print(f"Length of document: {doc_length}")

if __name__ == "__main__":
    input_pptx = 'presentation.pptx'
    main(input_pptx)
