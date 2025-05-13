from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse, RedirectResponse
from core.qr_generator import generate_qr
from database_op.database import get_db
import mysql.connector
import os
from azure.storage.blob import BlobServiceClient, BlobClient
from dotenv import load_dotenv
import io
import logging
from datetime import datetime, timezone
from helpers.blob_op import refresh_sas_token_if_needed

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

@qrcode.get("/download-qr/{type}/{id}")
async def download_qr(
    type: str,
    id: int,
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Serves QR code images with proper Content-Disposition headers to force download.
    
    This endpoint fetches the QR code from Azure Blob Storage and serves it with
    headers that force the browser to download it rather than display it.
    
    Args:
        type: Either 'pdf' or 'set' to indicate which type of QR code to download
        id: The ID of the PDF or set
    """
    cursor = None
    try:
        # Get the user's ID from the session
        user_id = request.session.get('user_id')
        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        # Get the user's alias
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()
        if not user_data or 'alias' not in user_data:
            raise HTTPException(status_code=404, detail="User alias not found")
        user_alias = user_data['alias']
        
        # Get the QR code URL and SAS token based on the type
        if type == 'pdf':
            cursor.execute(
                "SELECT pdf_qrcode_url, pdf_qrcode_sas_token, original_filename FROM pdf WHERE pdf_id = %s AND user_id = %s",
                (id, user_id)
            )
            qr_data = cursor.fetchone()
            if not qr_data:
                raise HTTPException(status_code=404, detail="PDF QR code not found")
            
            qr_url = qr_data['pdf_qrcode_url']
            qr_sas_token = qr_data['pdf_qrcode_sas_token']
            filename = qr_data['original_filename'].replace('.pptx', '').replace('.pdf', '')
            download_filename = f"{filename}_qr.png"
            
        elif type == 'set':
            cursor.execute(
                "SELECT qrcode_url, qrcode_sas_token, name FROM `set` WHERE set_id = %s AND user_id = %s",
                (id, user_id)
            )
            qr_data = cursor.fetchone()
            if not qr_data:
                raise HTTPException(status_code=404, detail="Set QR code not found")
            
            qr_url = qr_data['qrcode_url']
            qr_sas_token = qr_data['qrcode_sas_token']
            download_filename = f"{qr_data['name']}_qr.png"
            
        else:
            raise HTTPException(status_code=400, detail="Invalid QR code type")
        
        # Fetch the QR code from Azure Blob Storage
        full_qr_url = f"{qr_url}?{qr_sas_token}"
        try:
            blob_client = BlobClient.from_blob_url(full_qr_url)
            qr_code_bytes = blob_client.download_blob().readall()
        except Exception as e:
            logging.error(f"Error downloading QR code from Azure: {e}")
            
            # If the QR code doesn't exist, regenerate it
            if type == 'pdf':
                logging.info(f"QR code not found for PDF {id}, regenerating...")
                
                # Get the PDF URL and SAS token
                cursor.execute(
                    "SELECT url, sas_token, original_filename FROM pdf WHERE pdf_id = %s",
                    (id,)
                )
                pdf_data = cursor.fetchone()
                if not pdf_data:
                    raise HTTPException(status_code=404, detail="PDF not found")
                
                # Generate a new QR code
                full_pdf_url = f"{pdf_data['url']}?{pdf_data['sas_token']}"
                qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry = generate_qr(
                    link_with_sas=full_pdf_url,
                    user_alias=user_alias,
                    pdf_id=id,
                    set_name="full_pdf"
                )
                
                # Update the database with the new QR code information
                cursor.execute(
                    """
                    UPDATE pdf
                    SET pdf_qrcode_url = %s, pdf_qrcode_sas_token = %s, pdf_qrcode_sas_token_expiry = %s
                    WHERE pdf_id = %s
                    """,
                    (qr_code_url, qr_code_sas_token, qr_code_sas_token_expiry, id)
                )
                db.commit()
                
                # Try to fetch the newly generated QR code
                try:
                    full_qr_url = f"{qr_code_url}?{qr_code_sas_token}"
                    blob_client = BlobClient.from_blob_url(full_qr_url)
                    qr_code_bytes = blob_client.download_blob().readall()
                    
                    # Update the filename for the download
                    filename = pdf_data['original_filename'].replace('.pptx', '').replace('.pdf', '')
                    download_filename = f"{filename}_qr.png"
                    
                    logging.info(f"Successfully regenerated QR code for PDF {id}")
                except Exception as fetch_err:
                    logging.error(f"Error fetching regenerated QR code: {fetch_err}")
                    raise HTTPException(status_code=500, detail="Error generating QR code")
            else:
                # For sets, we can't easily regenerate the QR code without knowing the slides
                raise HTTPException(status_code=404, detail="QR code not found")
        
        # Return the QR code with headers that force download
        response = StreamingResponse(io.BytesIO(qr_code_bytes), media_type="image/png")
        response.headers["Content-Disposition"] = f'attachment; filename="{download_filename}"'
        response.headers["Content-Type"] = "image/png"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
        
    except Exception as e:
        logging.error(f"Error in download_qr: {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading QR code: {str(e)}")
    finally:
        if cursor:
            cursor.close()

# We'll keep these endpoints for future use, but we won't use them for QR codes directly
# Instead, we'll track downloads when users access the dashboard

@qrcode.post("/increment-pdf-download/{pdf_id}")
async def increment_pdf_download(
    pdf_id: int,
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Increments the download count for a PDF presentation.
    This endpoint can be called via AJAX when a user downloads a PDF.
    """
    cursor = None
    try:
        # Increment the download count
        cursor = db.cursor()
        cursor.execute(
            "UPDATE pdf SET download_count = download_count + 1 WHERE pdf_id = %s",
            (pdf_id,)
        )
        db.commit()
        return {"success": True, "message": "Download count incremented"}
    except Exception as e:
        print(f"Error incrementing PDF download count: {e}")
        raise HTTPException(status_code=500, detail="Error tracking download")
    finally:
        if cursor:
            cursor.close()

@qrcode.post("/increment-set-download/{set_id}")
async def increment_set_download(
    set_id: int,
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Increments the download count for a set.
    This endpoint can be called via AJAX when a user downloads a set.
    """
    cursor = None
    try:
        # Increment the download count
        cursor = db.cursor()
        cursor.execute(
            "UPDATE `set` SET download_count = download_count + 1 WHERE set_id = %s",
            (set_id,)
        )
        db.commit()
        return {"success": True, "message": "Download count incremented"}
    except Exception as e:
        print(f"Error incrementing set download count: {e}")
        raise HTTPException(status_code=500, detail="Error tracking download")
    finally:
        if cursor:
            cursor.close()
