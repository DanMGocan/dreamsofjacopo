from fastapi import FastAPI, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

import shutil
import os
from api import converter, users, qrcode

# Create an instance of FastAPI
app = FastAPI()

# Mount the static folder to serve images
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../static")), name="static")

# Include the API routes
app.include_router(converter.converter)
app.include_router(users.users)
app.include_router(qrcode.qrcode)

# Initialize templates
templates = Jinja2Templates(directory="templates")

# To debug current location
print(f"Current working directory: {os.getcwd()}")

@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    """Serve the HTML form for uploading .pptx files"""
    return templates.TemplateResponse("/home.html", {"request": request})

