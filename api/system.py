from fastapi import APIRouter, Request, Depends, HTTPException, Path, Body
from helpers.system_monitor import get_system_stats
from database_op.database import get_db
import mysql.connector
import logging
import subprocess
import os
import sys
from typing import Dict, Any
from datetime import datetime

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

@system.get("/bug-reports")
async def get_bug_reports(request: Request, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    Get all bug reports with user information.
    
    This endpoint retrieves all bug reports from the database along with the email
    of the user who submitted each report.
    """
    try:
        # Check admin access
        check_admin_access(request)
        
        # Get all bug reports with user email
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT br.report_id, br.bug_description, br.status, 
                   br.created_at, br.updated_at, u.email
            FROM bug_reports br
            JOIN user u ON br.user_id = u.user_id
            ORDER BY br.created_at DESC
        """)
        
        bug_reports = cursor.fetchall()
        cursor.close()
        
        # Convert datetime objects to strings for JSON serialization
        for report in bug_reports:
            report['created_at'] = report['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            report['updated_at'] = report['updated_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        return {"bug_reports": bug_reports}
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 Forbidden)
        raise
    except Exception as e:
        logger.error(f"Error getting bug reports: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting bug reports: {str(e)}")

@system.post("/bug-reports/{report_id}/status")
async def update_bug_report_status(
    request: Request,
    report_id: int = Path(...),
    status_data: Dict[str, Any] = Body(...),
    db: mysql.connector.connection.MySQLConnection = Depends(get_db)
):
    """
    Update the status of a bug report.
    
    This endpoint allows changing the status of a bug report to one of:
    - 0: pending
    - 1: investigating
    - 2: resolved
    - 3: not_a_bug
    """
    try:
        # Check admin access
        check_admin_access(request)
        
        # Get the new status from the request body
        new_status = status_data.get("status")
        if new_status is None or not isinstance(new_status, int) or new_status < 0 or new_status > 3:
            raise HTTPException(status_code=400, detail="Invalid status value. Must be 0, 1, 2, or 3.")
        
        # Update the bug report status
        cursor = db.cursor()
        cursor.execute(
            "UPDATE bug_reports SET status = %s, updated_at = %s WHERE report_id = %s",
            (new_status, datetime.now(), report_id)
        )
        db.commit()
        
        # Check if any rows were affected
        if cursor.rowcount == 0:
            cursor.close()
            raise HTTPException(status_code=404, detail=f"Bug report with ID {report_id} not found")
        
        cursor.close()
        
        return {"message": f"Bug report status updated successfully", "report_id": report_id, "new_status": new_status}
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 Forbidden)
        raise
    except Exception as e:
        logger.error(f"Error updating bug report status: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating bug report status: {str(e)}")

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
