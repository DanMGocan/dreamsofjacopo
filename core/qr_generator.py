import qrcode
import os

def generate_qr_code(directory):
    try:
        # Create the base URL (adjust based on your actual server/URL structure)
        base_url = "http://127.0.0.1:8000/static/temp/"
        
        # Get the list of image URLs
        image_files = os.listdir(directory)
        if not image_files:
            print(f"No images found in {directory}")
            return None

        image_urls = [f"{base_url}{file}" for file in image_files]
        qr_data = "\n".join(image_urls)  # You can customize how you generate this URL list
        print("QR data (URLs):", qr_data)

        # Generate the QR code from the image URLs
        qr_img = qrcode.make(qr_data)
        
        # Ensure the 'qrcode' directory exists
        output_dir = "static/qrcode"
        os.makedirs(output_dir, exist_ok=True)

        # Save the QR code image
        qr_code_path = os.path.join(output_dir, "qr_code.png")
        qr_img.save(qr_code_path)
        print(f"QR code saved at {qr_code_path}")
        
        return f"/static/qrcode/qr_code.png"  # Return the path relative to the static directory

    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None
