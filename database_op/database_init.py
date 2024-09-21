import mysql.connector
from mysql.connector import errorcode
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Database connection configuration
config = {
    'user': os.getenv('DB_USER'),         
    'password': os.getenv('DB_PASSWORD'), 
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME')
}

# Function to create the database if it doesn't exist
def create_database():
    try:
        # Connect to the MySQL server without specifying a database
        connection = mysql.connector.connect(
            user=config['user'],
            password=config['password'],
            host=config['host']
        )
        cursor = connection.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {config['database']}")
        print(f"Database '{config['database']}' created successfully!")
        cursor.close()
        connection.close()
    except mysql.connector.Error as err:
        print(f"Error creating database: {err}")

# Function to execute schema.sql and create tables
def initialize_database():
    try:
        # First, ensure the database exists
        create_database()
        
        # Connect to the database
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()

        # Read the schema.sql file and execute it
        with open('schema.sql', 'r') as schema_file:
            schema_sql = schema_file.read()
        
        # Split and execute statements
        for statement in schema_sql.split(';'):
            if statement.strip():
                cursor.execute(statement)
                print(f"Executed: {statement.strip()[:50]}...")
        
        # Commit the transaction
        connection.commit()
        print("Schema and data committed successfully!")
        cursor.close()
        connection.close()
    except mysql.connector.Error as err:
        print(f"Error initializing database: {err}")

if __name__ == "__main__":
    initialize_database()