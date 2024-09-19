import mysql.connector
from mysql.connector import errorcode
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Database connection configuration using environment variables for security
config = {
    'user': os.getenv('DB_USER'),         # Use environment variables for sensitive data
    'password': os.getenv('DB_PASSWORD'), # Ensure to set env variables in your system
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME')      # Default database name if not set in env
}

# Function to get a connection to the MySQL database
def get_db():
    try:
        connection = mysql.connector.connect(**config)
        return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None
