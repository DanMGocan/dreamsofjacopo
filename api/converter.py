from fastapi import APIRouter, UploadFile, File, Request
import os
from core import main_converter  # Assuming your converter functions are here
from fastapi.templating import Jinja2Templates

TEMP_DIR = "static/temp/"
os.makedirs(TEMP_DIR, exist_ok=True)  # Ensure temp directory exists

converter = APIRouter()

# Initialize templates
templates = Jinja2Templates(directory="templates")

@converter.get("/upload")
async def create_user(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@converter.post("/upload-pptx")
async def upload_pptx(pptx_file: UploadFile = File(...)):
    try:
        # Define the temp directory path
        file_location = os.path.join(TEMP_DIR, pptx_file.filename)
        
        # Debug: Print the file location
        print(f"Saving file to: {file_location}")
        
        # Save the uploaded file temporarily
        with open(file_location, "wb+") as file_object:
            file_object.write(await pptx_file.read())
        
        # Debug: Check if the file was saved
        if os.path.exists(file_location):
            print(f"File saved successfully: {file_location}")
        else:
            print(f"Failed to save file: {file_location}")

        # Perform conversion (PPTX to PDF and then PDF to images)
        result = main_converter.convert_pptx(file_location)

        return {
            "message": "File uploaded and processed successfully!",
            "image_urls": result["image_paths"]
        }

    except Exception as e:
        return {"error": f"Failed to process file: {str(e)}"}
