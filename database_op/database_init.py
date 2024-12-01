import mysql.connector
from mysql.connector import errorcode
import os
from dotenv import load_dotenv
import bcrypt  # Import bcrypt for password hashing

# Load environment variables from a .env file
load_dotenv()

# Database connection configuration
config = {
    'user': os.getenv('DB_USER'),         
    'password': os.getenv('DB_PASSWORD'), 
    'host': os.getenv('DB_HOST'),
    'database': os.getenv('DB_NAME')
}

# Function to drop and recreate the database
def recreate_database():
    try:
        # Connect to the MySQL server without specifying a database
        connection = mysql.connector.connect(
            user=config['user'],
            password=config['password'],
            host=config['host']
        )
        cursor = connection.cursor()

        # Drop the existing database if it exists
        cursor.execute(f"DROP DATABASE IF EXISTS {config['database']}")
        print(f"Database '{config['database']}' dropped successfully!")

        # Create a new database
        cursor.execute(f"CREATE DATABASE {config['database']}")
        print(f"Database '{config['database']}' created successfully!")

        cursor.close()
        connection.close()
    except mysql.connector.Error as err:
        print(f"Error recreating database: {err}")

# Function to execute schema.sql and create tables
def initialize_database():
    try:
        # First, recreate the database
        recreate_database()
        
        # Connect to the newly created database
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()

        # Read the schema.sql file and execute it
        with open('schema.sql', 'r') as schema_file:
            schema_sql = schema_file.read()
        
        # Split and execute statements
        for statement in schema_sql.split(';'):
            if statement.strip():
                cursor.execute(statement)
                print(f"Executed: {statement.strip()[:50]}...")  # Show first 50 chars of the statement
        
        # Commit the schema creation
        connection.commit()
        print("Schema and tables created successfully!")

        # Now insert the test user
        # Use the same password hashing as the application
        test_email = 'sad@sad.sad'
        test_password = '123'  # Plain text password for the test account
        hashed_password = bcrypt.hashpw(test_password.encode('utf-8'), bcrypt.gensalt())

        # Prepare the insert statement
        insert_user_query = """
        INSERT INTO user (email, password, premium_status, account_activated, login_method, alias)
        VALUES (%s, %s, %s, %s, %s, %s)
        """

        cursor.execute(insert_user_query, (
            test_email,
            hashed_password.decode('utf-8'),  # Decode to convert bytes to string
            1,  # premium_status (1 for premium, 0 for free)
            True,  # account_activated (True means the account is activated)
            'slide_pull',  # login_method
            'testuser'  # alias (must be unique)
        ))

        # Commit the test user insertion
        connection.commit()
        print("Test user inserted successfully!")

        cursor.close()
        connection.close()
    except mysql.connector.Error as err:
        print(f"Error initializing database: {err}")

if __name__ == "__main__":
    initialize_database()
