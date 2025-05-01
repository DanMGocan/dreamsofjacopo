from fastapi import APIRouter, Request, Depends, HTTPException
from helpers.system_monitor import get_system_stats
from database_op.database import get_db
import mysql.connector
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Create our API router
system = APIRouter()

@system.get("/stats")
async def get_stats(request: Request):
    """
    Get current system statistics including CPU and memory usage.
    
    This endpoint provides real-time information about the server's resource usage,
    which can be helpful for diagnosing performance issues.
    """
    try:
        # Check if the user is logged in (optional - remove if you want public access)
        if 'user_id' not in request.session:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Get the system stats
        stats = get_system_stats()
        
        return stats
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting system stats: {str(e)}")
