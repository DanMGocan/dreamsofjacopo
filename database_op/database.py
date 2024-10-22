import mysql.connector.pooling
import os
from dotenv import load_dotenv
from typing import Generator
from fastapi import Depends


# Load environment variables from a .env file
load_dotenv()

# Database connection configuration using environment variables for security
config = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME'),
    'pool_name': 'mypool',
    'pool_size': 5  # Set a connection pool size (can adjust based on app's needs)
}

# Initialize the connection pool
try:
    connection_pool = mysql.connector.pooling.MySQLConnectionPool(**config)
except mysql.connector.Error as err:
    print(f"Error connecting to database pool: {err}")

def get_db() -> Generator:
    connection = None
    try:
        connection = connection_pool.get_connection()
        yield connection
    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        if connection:
            connection.close()
    finally:
        if connection and connection.is_connected():
            connection.close()


        