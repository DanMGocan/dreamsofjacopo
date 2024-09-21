from fastapi import FastAPI, UploadFile, File, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from core.session import get_current_user

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

@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("/home.html", {"request": request})

# Protected route example
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user=Depends(get_current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": current_user})

