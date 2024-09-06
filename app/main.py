from fastapi import FastAPI, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

import shutil
import os
from api import endpoints

# Create an instance of FastAPI
app = FastAPI()

# Mount the static folder to serve images
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include the API routes
app.include_router(endpoints.router)

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Static folder for uploaded files
UPLOAD_DIR = "app/static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    """Serve the HTML form for uploading .pptx files"""
    return templates.TemplateResponse("upload.html", {"request": request})

@app.post("/upload-pptx")
async def upload_pptx(pptx_file: UploadFile = File(...)):
    """Handle .pptx file upload"""
    try:
        file_location = f"{UPLOAD_DIR}/{pptx_file.filename}"
        # Save uploaded file
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(pptx_file.file, file_object)
        
        # You can call the conversion functions here
        # For example: convert_pptx(file_location)

        return {"message": f"File '{pptx_file.filename}' uploaded successfully!"}
    
    except Exception as e:
        return {"error": f"Failed to upload file: {str(e)}"}