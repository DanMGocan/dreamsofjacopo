from starlette.responses import RedirectResponse
from fastapi import Request

# Set a flash message
def set_flash_message(response: RedirectResponse, message: str):
    response.set_cookie(key="flash_message", value=message, max_age=5)

# Get and clear the flash message
def get_flash_message(request: Request):
    message = request.cookies.get("flash_message")
    if message:
        response = RedirectResponse(request.url)
        response.delete_cookie("flash_message")
        return message
    return None
