from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from core.qr_generator import generate_qr_code

qrcode = APIRouter()

# Initialize templates
templates = Jinja2Templates(directory="templates")

@qrcode.get("/generateqr")
async def generate_qr(request: Request):
    # Assuming you generate the QR code from a 'static/temp' directory
    qr_code_path = generate_qr_code("static/temp")  # Directory with images
    return templates.TemplateResponse("qr-code.html", {"request": request, "qr_code_path": qr_code_path})
