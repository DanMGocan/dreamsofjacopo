import qrcode
import io
from helpers.blob_op import upload_to_blob

def generate_qr(link_with_sas, user_alias, pdf_id, set_name):
    """
    Creates a QR code that links to the user's slides and uploads it to Azure.
    
    This is the final step in our process - we take the URL of the slides (which includes
    a security token), generate a QR code for it, and store that QR code in Azure so the
    user can download and share it.
    
    When someone scans this QR code with their phone, they'll be taken directly to
    the slides the user selected.
    """
    try:
        # Set up our QR code with good defaults
        # Version 1 is the smallest QR code, and we use low error correction
        # since we expect these to be printed clearly
        qr = qrcode.QRCode(
            version=1,                                  # QR code version (size)
            error_correction=qrcode.constants.ERROR_CORRECT_L,  # Low error correction
            box_size=10,                                # Size of each box in pixels
            border=4,                                   # White border around the QR code
        )
        
        # Add the URL to the QR code
        qr.add_data(link_with_sas)
        qr.make(fit=True)  # Optimize the QR code size

        # Create the QR code image in memory (no need to save to disk)
        qr_buffer = io.BytesIO()
        qr_image = qr.make_image(fill_color="black", back_color="white")
        qr_image.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)  # Reset buffer position to the beginning

        # Set up the path where we'll store this in Azure
        # We organize by user and presentation ID to keep things tidy
        qr_blob_name = f"{user_alias}/qrcodes/{pdf_id}_qr.png"

        # When users download the QR code, we want it to have a nice filename
        # that includes the set name they chose
        filename = f"{set_name}_qrcode.png"
        content_disposition = f'attachment; filename="{filename}"'

        # Upload the QR code to Azure and get back the URL and security token
        # The content_disposition ensures the file downloads with the right name
        qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = upload_to_blob(
            blob_name=qr_blob_name,
            file_content=qr_buffer.getvalue(),
            content_type="image/png",
            user_alias=user_alias,
            content_disposition=content_disposition
        )

        # Return everything the app needs to display and link to the QR code
        return qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry

    except Exception as e:
        # If anything goes wrong, provide a helpful error message
        raise Exception(f"Couldn't create your QR code: {e}")
