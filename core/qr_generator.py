import qrcode
import os

def generate_qr_code(directory):
    # Create a URL (for simplicity, assume we serve images from a static directory)
    base_url = "http://127.0.0.1:8000/static/images/"
    
    # Generate a QR code that links to the images
    image_urls = [f"{base_url}{file}" for file in os.listdir(directory)]
    qr_data = "\n".join(image_urls)  # You can customize how you generate this URL list
    
    qr_img = qrcode.make(qr_data)
    qr_code_path = f"{directory}/qr_code.png"
    qr_img.save(qr_code_path)
    
    return qr_code_path
