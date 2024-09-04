import subprocess
import os
import fitz  # PyMuPDF

def convert_pptx_to_pdf(pptx_path, output_dir):
    # Define the output PDF path
    pdf_path = os.path.join(output_dir, os.path.splitext(os.path.basename(pptx_path))[0] + '.pdf')
    
    # Specify the full path to soffice.exe (LibreOffice)
    soffice_path = r'C:\Program Files\LibreOffice\program\soffice.exe'
    
    # Run the LibreOffice command to convert PPTX to PDF
    subprocess.run([soffice_path, '--headless', '--convert-to', 'pdf', pptx_path, '--outdir', output_dir])

    return pdf_path

def convert_pdf_to_images(pdf_path, output_dir):
    # Open the PDF file
    pdf_document = fitz.open(pdf_path)
    
    for page_number in range(len(pdf_document)):
        page = pdf_document.load_page(page_number)
        image = page.get_pixmap()
        image_path = os.path.join(output_dir, f"slide_{page_number + 1}.png")
        image.save(image_path)
    
    pdf_document.close()

def main(input_pptx):
    # Define the output directory (same as the input file's directory)
    output_dir = os.path.dirname(input_pptx)

    # Convert PPTX to PDF
    pdf_path = convert_pptx_to_pdf(input_pptx, output_dir)

    # Convert PDF to images
    convert_pdf_to_images(pdf_path, output_dir)

if __name__ == "__main__":
    # Example usage: specify your PPTX file
    input_pptx = 'presentation.pptx'
    main(input_pptx)
