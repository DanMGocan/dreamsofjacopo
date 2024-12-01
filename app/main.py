from fastapi import FastAPI, UploadFile, File, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from helpers.flash_utils import get_flash_message
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import mysql.connector
from database_op.database import get_db

load_dotenv()

import os
from api import converter, users, qrcode

# Create an instance of FastAPI
app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY"),
    max_age=3600,  # Session lifetime in seconds
    same_site="Lax",  # Adjust depending on your needs
    # https_only=True  # Use only if you are using HTTPS
)

# Mount the static folder to serve images
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../static")), name="static")

# Include the API routes
app.include_router(converter.converter)
app.include_router(users.users)

# Initialize templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("/home.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    # Ensure the user is logged in
    if 'email' not in request.session:
        return RedirectResponse(url="/login")

    # Get user session details
    email = request.session['email']
    user_id = request.session['user_id']
    account_activated = request.session['account_activated']
    premium_status = request.session['premium_status']
    member_since = request.session['member_since']

    # Check if there's a flash message to display
    flash_message = get_flash_message(request)

    cursor = db.cursor(dictionary=True)

    # Fetch presentations and associated sets using LEFT JOIN
    cursor.execute("""
        SELECT pdf.pdf_id, pdf.original_filename, pdf.url, pdf.sas_token_expiry AS uploaded_on,
               `set`.set_id, `set`.name AS set_name, `set`.qrcode_url, `set`.qrcode_sas_token
        FROM pdf
        LEFT JOIN `set` ON pdf.pdf_id = `set`.pdf_id
        WHERE pdf.user_id = %s
        ORDER BY pdf.pdf_id
    """, (user_id,))

    rows = cursor.fetchall()

    # Organize data into presentations with their sets
    presentations = []
    presentation_dict = {}
    for row in rows:
        pdf_id = row['pdf_id']
        if pdf_id not in presentation_dict:
            # New presentation
            presentation = {
                'pdf_id': pdf_id,
                'original_filename': row['original_filename'],
                'url': row['url'],
                'uploaded_on': row['uploaded_on'],
                'sets': []
            }
            presentation_dict[pdf_id] = presentation
            presentations.append(presentation)
        else:
            presentation = presentation_dict[pdf_id]

        # Add set if it exists
        if row['set_id'] is not None:
            # Construct the full QR code URL with SAS token
            qrcode_url_with_sas = f"{row['qrcode_url']}?{row['qrcode_sas_token']}"
            presentation['sets'].append({
                'set_id': row['set_id'],
                'name': row['set_name'],
                'qrcode_url_with_sas': qrcode_url_with_sas
            })

    cursor.close()

    # Render the dashboard template with all the user and presentation data
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user_id": user_id,
        "email": email,
        "flash_message": flash_message,
        "account_activated": account_activated,
        "premium_status": premium_status,
        "member_since": member_since,
        "presentations": presentations  # Pass the list of presentations to the template
    })
