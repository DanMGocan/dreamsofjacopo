from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
from core.qr_generator import generate_qr
from database_op.database import get_db
import mysql.connector
import os
from azure.storage.blob import BlobServiceClient, BlobClient
from dotenv import load_dotenv
import io

# Load environment variables
load_dotenv()

# Set up Azure Blob Storage connection
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
AZURE_BLOB_CONTAINER_NAME = os.getenv("AZURE_BLOB_CONTAINER_NAME")

# Initialize the Azure Blob Storage client
blob_service_client = BlobServiceClient(
    account_url=f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
    credential=AZURE_STORAGE_ACCOUNT_KEY
)

qrcode = APIRouter()

# Initialize templates
templates = Jinja2Templates(directory="templates")

# The commented out code below was the original content of this file.
# @qrcode.get("/generateqr")
# async def generate_qr(request: Request):
#     # Assuming you generate the QR code from a 'static/temp' directory
#     qr_code_path = generate_qr_code("static/temp")  # Directory with images
#     return templates.TemplateResponse("qr-code.html", {"request": request, "qr_code_path": qr_code_path})

@qrcode.post("/generate-pdf-qr/{pdf_id}")
async def generate_pdf_qr(
    pdf_id: int,
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Generates a QR code for the entire PDF presentation.
    """
    cursor = None
    try:
        # Get the PDF URL and SAS token from the database
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT url, sas_token FROM pdf WHERE pdf_id = %s",
            (pdf_id,)
        )
        pdf_data = cursor.fetchone()

        if not pdf_data:
            raise HTTPException(status_code=404, detail="PDF presentation not found")

        pdf_url = pdf_data['url']
        sas_token = pdf_data['sas_token']
        full_pdf_url = f"{pdf_url}?{sas_token}"

        # Get user alias for file organization
        user_id = request.session.get('user_id')
        if not user_id:
             raise HTTPException(status_code=401, detail="User not authenticated")

        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        if not user_data or 'alias' not in user_data:
            raise HTTPException(status_code=404, detail="User alias not found")
        user_alias = user_data['alias']

        # Generate the QR code
        # The generate_qr function is expected to return the URL of the generated QR code
        # and handle the saving to Azure Blob Storage.
        qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = generate_qr(
            link_with_sas=full_pdf_url,
            user_alias=user_alias,
            pdf_id=pdf_id,
            set_name="full_pdf" # Use a default name for the full PDF QR
        )

        # Download the generated QR code image from Azure
        full_qr_code_url = f"{qr_code_url}?{qr_code_sas_token}"
        blob_client = BlobClient.from_blob_url(full_qr_code_url)
        qr_code_bytes = blob_client.download_blob().readall()

        # Return the QR code image as a response
        return StreamingResponse(io.BytesIO(qr_code_bytes), media_type="image/png")

    except Exception as e:
        print(f"Error generating PDF QR code: {e}")
        raise HTTPException(status_code=500, detail="Error generating QR code")
    finally:
        if cursor:
            cursor.close()
