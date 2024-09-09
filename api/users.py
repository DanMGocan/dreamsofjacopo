from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

users = APIRouter()

# Initialize templates
templates = Jinja2Templates(directory="templates")

@users.get("/registration")
async def create_user(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})