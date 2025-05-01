from fastapi import APIRouter, Request, Depends, HTTPException
from helpers.system_monitor import get_system_stats
from database_op.database import get_db
import mysql.connector
import logging
import subprocess
import os
import sys

# Configure logging
logger = logging.getLogger(__name__)

# Create our API router
system = APIRouter()

# Admin email for access control
ADMIN_EMAIL = "admin@slidepull.net"

def check_admin_access(request: Request):
    """Check if the current user has admin access"""
    if 'email' not in request.session or request.session['email'] != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")
    return True

@system.get("/stats")
async def get_stats(request: Request):
    """
    Get current system statistics including CPU and memory usage.
    
    This endpoint provides real-time information about the server's resource usage,
    which can be helpful for diagnosing performance issues.
    """
    try:
        # Check if the user is logged in and has admin access
        if 'email' not in request.session:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        if request.session['email'] != ADMIN_EMAIL:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get the system stats
        stats = get_system_stats()
        
        return stats
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting system stats: {str(e)}")

@system.post("/kill-libreoffice")
async def kill_libreoffice(request: Request):
    """
    Kill all LibreOffice processes.
    
    This endpoint is useful when LibreOffice processes are hanging or consuming too many resources.
    """
    try:
        # Check admin access
        check_admin_access(request)
        
        # Kill LibreOffice processes based on the operating system
        if os.name == 'posix':  # Linux/Unix
            subprocess.run(['pkill', 'soffice'], stderr=subprocess.DEVNULL)
            subprocess.run(['pkill', 'libreoffice'], stderr=subprocess.DEVNULL)
        elif os.name == 'nt':  # Windows
            subprocess.run(['taskkill', '/F', '/IM', 'soffice.exe'], stderr=subprocess.DEVNULL)
            subprocess.run(['taskkill', '/F', '/IM', 'soffice.bin'], stderr=subprocess.DEVNULL)
        
        return {"message": "LibreOffice processes terminated successfully"}
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 Forbidden)
        raise
    except Exception as e:
        logger.error(f"Error killing LibreOffice processes: {e}")
        raise HTTPException(status_code=500, detail=f"Error killing LibreOffice processes: {str(e)}")

@system.post("/restart-app")
async def restart_app(request: Request):
    """
    Restart the application.
    
    This endpoint is useful when the application is in an inconsistent state.
    """
    try:
        # Check admin access
        check_admin_access(request)
        
        # Schedule a restart after a short delay to allow the response to be sent
        def restart_after_delay():
            import time
            time.sleep(1)  # Wait for 1 second
            os.execv(sys.executable, ['python'] + sys.argv)
        
        # Start the restart process in a separate thread
        import threading
        threading.Thread(target=restart_after_delay).start()
        
        return {"message": "Application restart initiated"}
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 Forbidden)
        raise
    except Exception as e:
        logger.error(f"Error restarting application: {e}")
        raise HTTPException(status_code=500, detail=f"Error restarting application: {str(e)}")
