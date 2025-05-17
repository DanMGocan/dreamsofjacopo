import os
import mysql.connector
from mysql.connector import pooling
from typing import Generator
import logging
import time

# Configure logging
# logging.basicConfig(level=logging.INFO) # Removed: basicConfig is configured in app/main.py
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
    'pool_size': 10,  # Increased pool size for better concurrency
    'pool_reset_session': True,  # Reset session variables when returning to pool
    'connect_timeout': 60,       # Increased connection timeout
    'connection_timeout': 60,    # Timeout for getting a connection from the pool
    'autocommit': False,         # Explicit transaction control
    'use_pure': True,            # Use pure Python implementation for better stability
    'get_warnings': True,        # Get warnings from MySQL
    'raise_on_warnings': False,  # Don't raise exceptions on warnings
    'buffered': True,            # Use buffered cursors by default
    'raw': False,                # Return Python types
    'consume_results': True      # Consume results automatically
}

# Ensure all required environment variables are loaded
assert config['user'], "Environment variable DB_USER is missing"
assert config['password'], "Environment variable DB_PASSWORD is missing"
assert config['host'], "Environment variable DB_HOST is missing"
assert config['database'], "Environment variable DB_NAME is missing"

# Initialize the connection pool with retry logic
max_retries = 3
retry_delay = 2  # seconds

for attempt in range(max_retries):
    try:
        connection_pool = mysql.connector.pooling.MySQLConnectionPool(**config)
        logger.info("Database connection pool initialized successfully.")
        
        # Test a connection from the pool to verify it works
        test_conn = connection_pool.get_connection()
        test_cursor = test_conn.cursor()
        test_cursor.execute("SELECT 1")
        test_cursor.fetchone()
        test_cursor.close()
        test_conn.close()
        logger.info("Database connection test successful.")
        break
    except mysql.connector.Error as err:
        logger.error(f"Attempt {attempt+1}/{max_retries}: Error initializing database connection pool: {err}", exc_info=True)
        if attempt < max_retries - 1:
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
        else:
            logger.error("All connection attempts failed.")
            raise RuntimeError("Failed to initialize database connection pool") from err

def get_connection():
    """Helper function to get a valid connection with retry logic"""
    max_conn_retries = 3  # Increased retries
    
    for attempt in range(max_conn_retries):
        try:
            logger.info(f"Getting a connection from the pool (attempt {attempt+1}/{max_conn_retries}).")
            connection = connection_pool.get_connection()
            
            # Test the connection to make sure it's still valid
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            
            # Set session variables for better performance
            cursor = connection.cursor()
            cursor.execute("SET SESSION wait_timeout = 600")  # 10 minutes
            cursor.execute("SET SESSION interactive_timeout = 600")  # 10 minutes
            cursor.close()
            
            logger.info("Connection is valid.")
            return connection
        except mysql.connector.Error as err:
            logger.error(f"Error with database connection: {err}", exc_info=True)
            if 'connection' in locals() and connection:
                try:
                    connection.close()
                except Exception:
                    pass
            
            if attempt < max_conn_retries - 1:
                logger.info(f"Retrying connection in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("All connection attempts failed.")
                raise
    
    # This should never be reached due to the raise in the except block
    raise mysql.connector.Error("Failed to get a valid database connection")

def get_db() -> Generator:
    """
    Provides a database connection from the pool.
    Ensures the connection is returned to the pool after use.
    """
    connection = None
    try:
        connection = get_connection()
        yield connection
    finally:
        if connection:
            try:
                logger.info("Closing the connection and returning it to the pool.")
                connection.close()
            except Exception as e:
                logger.error(f"Error closing the connection: {e}", exc_info=True)
