import qrcode
import io
from helpers.blob_op import upload_to_blob

def generate_qr(link_with_sas, user_alias, pdf_id, set_name):
    """
    Generates a QR code for the provided link and uploads it to Azure Blob Storage.

    Args:
        link_with_sas (str): The URL (with SAS token) for the ZIP file.
        user_alias (str): The user's alias (for organizing the blob structure).
        pdf_id (int): The ID of the presentation for organizing blob storage.
        set_name (str): The name of the set, used for naming the QR code file.

    Returns:
        tuple: (qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry)
    """
    try:
        # Generate QR code image
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(link_with_sas)
        qr.make(fit=True)

        # Create an in-memory buffer for the image
        qr_buffer = io.BytesIO()
        qr_image = qr.make_image(fill_color="black", back_color="white")
        qr_image.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)

        # Define the blob name for the QR code
        qr_blob_name = f"{user_alias}/qrcodes/{pdf_id}_qr.png"

        # Specify the filename for Content-Disposition
        filename = f"{set_name}_qrcode.png"
        content_disposition = f'attachment; filename="{filename}"'

        # Upload the QR code to Azure Blob Storage with the content_disposition
        qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = upload_to_blob(
            blob_name=qr_blob_name,
            file_content=qr_buffer.getvalue(),
            content_type="image/png",
            user_alias=user_alias,
            content_disposition=content_disposition  # Pass content_disposition
        )

        return qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry

    except Exception as e:
        raise Exception(f"Failed to generate and upload QR code: {e}")
