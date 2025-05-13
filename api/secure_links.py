from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from database_op.database import get_db
import mysql.connector
import logging
import os
import io
from azure.storage.blob import BlobClient
from datetime import datetime, timezone
from helpers.blob_op import refresh_sas_token_if_needed
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize router
secure_links = APIRouter()

@secure_links.get("/s/{link_type}/{unique_code}")
async def secure_redirect(
    link_type: str,
    unique_code: str,
    request: Request,
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Securely serves resources like PDFs and slide sets using unique codes.
    
    This endpoint acts as a secure intermediary between public QR codes and private Azure storage.
    It validates the request using the unique code, refreshes SAS tokens if needed, and redirects to the content.
    
    Args:
        link_type: Either 'pdf' or 'set' to indicate which type of resource
        unique_code: The unique code associated with the PDF or set
    """
    cursor = None
    try:
        cursor = db.cursor(dictionary=True)
        
        # Get resource information based on the link type and unique code
        if link_type == 'pdf':
            cursor.execute(
                """
                SELECT p.*, u.alias 
                FROM pdf p
                JOIN user u ON p.user_id = u.user_id
                WHERE p.unique_code = %s
                """,
                (unique_code,)
            )
            resource = cursor.fetchone()
            if not resource:
                raise HTTPException(status_code=404, detail="PDF not found")
                
            # Track this view/download
            cursor.execute(
                "UPDATE pdf SET download_count = download_count + 1 WHERE pdf_id = %s",
                (resource['pdf_id'],)
            )
            db.commit()
                
            # Check if SAS token is still valid, refresh if needed
            url = resource['url']
            
            # Make sas_token_expiry timezone-aware if it's not
            sas_expiry_aware = resource['sas_token_expiry']
            if sas_expiry_aware and sas_expiry_aware.tzinfo is None:
                 sas_expiry_aware = sas_expiry_aware.replace(tzinfo=timezone.utc)

            sas_token, sas_expiry = refresh_sas_token_if_needed(
                alias=resource['alias'],
                file_path=url.split('/')[-1],  # Extract blob name from URL
                current_sas_token=resource['sas_token'],
                sas_token_expiry=sas_expiry_aware
            )
            
            # Update token in database if it was refreshed
            if sas_token != resource['sas_token']:
                cursor.execute(
                    "UPDATE pdf SET sas_token = %s, sas_token_expiry = %s WHERE pdf_id = %s",
                    (sas_token, sas_expiry, resource['pdf_id'])
                )
                db.commit()
            
            # Instead of redirecting to the Azure URL (which would expose the SAS token),
            # download the file and serve it as a streaming response with download headers
            full_url = f"{url}?{sas_token}"
            
            try:
                # Download the PDF from Azure
                blob_client = BlobClient.from_blob_url(full_url)
                pdf_data = blob_client.download_blob().readall()
                
                # Create a filename for the download
                filename = resource.get('original_filename', 'presentation.pdf')
                if not filename.lower().endswith('.pdf'):
                    filename = f"{filename}.pdf"
                
                # Return the PDF with headers that force download
                response = StreamingResponse(io.BytesIO(pdf_data), media_type="application/pdf")
                response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
                response.headers["Content-Type"] = "application/pdf"
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                
                return response
                
            except Exception as e:
                logging.error(f"Error downloading PDF: {e}")
                # If there's an error, fall back to direct redirect
                full_url = f"{url}?{sas_token}"
                return RedirectResponse(url=full_url)
            
        elif link_type == 'set':
            # For sets, find the associated set using the unique code
            cursor.execute(
                """
                SELECT s.set_id, s.pdf_id, s.url, s.sas_token, s.sas_token_expiry, s.name, u.alias
                FROM `set` s
                JOIN user u ON s.user_id = u.user_id
                WHERE s.unique_code = %s
                """,
                (unique_code,)
            )
            set_data = cursor.fetchone()
            
            if not set_data:
                raise HTTPException(status_code=404, detail="Slide set not found")
                
            # Track this view/download
            cursor.execute(
                "UPDATE `set` SET download_count = download_count + 1 WHERE set_id = %s",
                (set_data['set_id'],)
            )
            db.commit()
            
            # Check if we have a URL for the set's PDF file
            if not set_data.get('url'):
                # If the URL is not available, return an error message
                # This should not happen with new sets after the code changes
                raise HTTPException(
                    status_code=404, 
                    detail="This set does not have a downloadable PDF. Please recreate the set."
                )
            
            # Make sas_token_expiry timezone-aware if it's not
            sas_expiry_aware = set_data['sas_token_expiry']
            if sas_expiry_aware and sas_expiry_aware.tzinfo is None:
                 sas_expiry_aware = sas_expiry_aware.replace(tzinfo=timezone.utc)
            
            # Check if SAS token is still valid, refresh if needed
            sas_token, sas_expiry = refresh_sas_token_if_needed(
                alias=set_data['alias'],
                file_path=set_data['url'].split('/')[-1],  # Extract blob name from URL
                current_sas_token=set_data['sas_token'],
                sas_token_expiry=sas_expiry_aware
            )
            
            # Update token in database if it was refreshed
            if sas_token != set_data['sas_token']:
                cursor.execute(
                    "UPDATE `set` SET sas_token = %s, sas_token_expiry = %s WHERE set_id = %s",
                    (sas_token, sas_expiry, set_data['set_id'])
                )
                db.commit()
            
            # Instead of redirecting to the Azure URL (which would expose the SAS token),
            # download the file and serve it as a streaming response with download headers
            full_url = f"{set_data['url']}?{sas_token}"
            
            try:
                # Download the PDF from Azure
                blob_client = BlobClient.from_blob_url(full_url)
                pdf_data = blob_client.download_blob().readall()
                
                # Create a filename for the download
                filename = f"{set_data['name']}.pdf"
                
                # Return the PDF with headers that force download
                response = StreamingResponse(io.BytesIO(pdf_data), media_type="application/pdf")
                response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
                response.headers["Content-Type"] = "application/pdf"
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                
                return response
                
            except Exception as e:
                logging.error(f"Error downloading set PDF: {e}")
                # If there's an error, return an error message instead of redirecting to the viewer
                raise HTTPException(
                    status_code=500, 
                    detail="Error downloading the set PDF. Please try again later."
                )
            
        else:
            raise HTTPException(status_code=400, detail="Invalid link type")
            
    except Exception as e:
        logging.error(f"Error in secure_redirect: {e}")
        raise HTTPException(status_code=500, detail=f"Error serving content: {str(e)}")
    finally:
        if cursor:
            cursor.close()


# The viewer endpoint has been removed as it's no longer needed
# All sets are now directly downloaded as PDFs
