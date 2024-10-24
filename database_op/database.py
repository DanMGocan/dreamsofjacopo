import os
import mysql.connector
from mysql.connector import pooling
from typing import Generator
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Database connection configuration
config = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'pool_name': 'mypool',
    'pool_size': 5
}

# Initialize the connection pool
try:
    connection_pool = mysql.connector.pooling.MySQLConnectionPool(**config)
    logger.info("Database connection pool initialized.")
except mysql.connector.Error as err:
    logger.error(f"Error connecting to database pool: {err}")
    connection_pool = None

def get_db() -> Generator:
    connection = None
    try:
        connection = connection_pool.get_connection()
        yield connection
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        # Do not close the connection here
        # Optionally, re-raise the exception if you want the caller to handle it
        raise
    finally:
        if connection:
            try:
                connection.close()
            except Exception as e:
                print(f"Error closing connection: {e}")

