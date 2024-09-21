# app/session.py
from fastapi import Request, Response, HTTPException
from itsdangerous import URLSafeSerializer
import os

SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')  # Ensure to set this in your .env file
SESSION_COOKIE = 'session'

serializer = URLSafeSerializer(SECRET_KEY)

def create_session(response: Response, data: dict):
    session_data = serializer.dumps(data)
    response.set_cookie(key=SESSION_COOKIE, value=session_data, httponly=True)

def get_session(request: Request):
    session_data = request.cookies.get(SESSION_COOKIE)
    if session_data:
        try:
            return serializer.loads(session_data)
        except Exception:
            return None
    return None

def clear_session(response: Response):
    response.delete_cookie(SESSION_COOKIE)

# Authentication Dependency
def get_current_user(request: Request):
    session = get_session(request)
    if not session or 'user_id' not in session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session