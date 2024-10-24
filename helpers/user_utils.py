from fastapi import Request, HTTPException
import mysql.connector
from typing import Dict, Optional
from passlib.context import CryptContext

# Helper function to extract session data and fetch user details from the database
async def get_user_data_from_session(
    request: Request,
    db: mysql.connector.connection.MySQLConnection
) -> Dict[str, Optional[str]]:
    try:
        # Extract the user_id from session
        user_id = request.session.get('user_id')

        if not user_id:
            raise HTTPException(status_code=401, detail="User not authenticated")

        # Query the database to get the user details
        cursor = db.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT user_id, email, premium_status, member_since, account_activated, login_method, alias FROM user WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        # Ensure to close the cursor after the operation
        cursor.close()

        return {
            "user_id": user_data['user_id'],
            "email": user_data['email'],
            "premium_status": user_data['premium_status'],
            "member_since": user_data['member_since'],
            "account_activated": user_data['account_activated'],
            "login_method": user_data['login_method'],
            "alias": user_data['alias']
        }

    except Exception as e:
        # Ensure the cursor is closed in case of exception
        try:
            cursor.close()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Error retrieving session data: {str(e)}")
    
# Password hashing context (assuming it's being used in your app)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def authenticate_user(
    email: str,
    password: str,
    db: mysql.connector.connection.MySQLConnection
) -> dict:
    try:
        # Query the database to get all user details
        cursor = db.cursor(dictionary=True, buffered=True)
        query = """
        SELECT 
            user_id, email, password, premium_status, 
            member_since, account_activated, login_method, alias 
        FROM user WHERE email = %s
        """
        cursor.execute(query, (email,))
        user = cursor.fetchone()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Ensure the user registered with slide_pull login method
        if user['login_method'] != 'slide_pull':
            raise HTTPException(status_code=403, detail="You registered with a different login method. Please use that method to log in.")

        # Verify the password using Passlib's context
        if not pwd_context.verify(password, user['password']):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Close the cursor after querying
        cursor.close()

        # Return all the user data (excluding the password)
        return {
            "user_id": user['user_id'],
            "email": user['email'],
            "premium_status": user['premium_status'],
            "member_since": user['member_since'],
            "account_activated": user['account_activated'],
            "login_method": user['login_method'],
            "alias": user['alias']
        }

    except mysql.connector.Error as e:
        # Ensure cursor is closed in case of a database error
        try:
            cursor.close()
        except:
            pass
        raise HTTPException(status_code=500, detail="Database error")

