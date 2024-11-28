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

# Ensure all required environment variables are loaded
assert config['user'], "Environment variable DB_USER is missing"
assert config['password'], "Environment variable DB_PASSWORD is missing"
assert config['host'], "Environment variable DB_HOST is missing"
assert config['database'], "Environment variable DB_NAME is missing"

# Initialize the connection pool
try:
    connection_pool = mysql.connector.pooling.MySQLConnectionPool(**config)
    logger.info("Database connection pool initialized successfully.")
except mysql.connector.Error as err:
    logger.error(f"Error initializing database connection pool: {err}", exc_info=True)
    raise RuntimeError("Failed to initialize database connection pool") from err

def get_db() -> Generator:
    """
    Provides a database connection from the pool.
    Ensures the connection is returned to the pool after use.
    """
    connection = None
    try:
        logger.info("Getting a connection from the pool.")
        connection = connection_pool.get_connection()
        yield connection
    except mysql.connector.Error as err:
        logger.error(f"Error while getting a connection from the pool: {err}", exc_info=True)
        raise
    finally:
        if connection:
            try:
                logger.info("Closing the connection and returning it to the pool.")
                connection.close()
            except Exception as e:
                logger.error(f"Error closing the connection: {e}", exc_info=True)
