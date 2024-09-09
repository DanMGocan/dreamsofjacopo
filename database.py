import mysql.connector
from mysql.connector import errorcode

# Database connection configuration
config = {
    'user': 'root',             # Replace with your MySQL username
    'password': '////////////////////', # Replace with your MySQL password
    'host': '127.0.0.1',         # Replace with your MySQL host (localhost)
    'database': '////////////'  # Name of the database
}

# Function to connect to the MySQL database
def create_connection():
    try:
        connection = mysql.connector.connect(**config)
        print("Successfully connected to the database")
        return connection
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Error: Access denied, please check your username/password")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print(f"Database '{config['database']}' does not exist. Creating it...")
            create_database()
            # After creating the database, connect again with the new database
            connection = mysql.connector.connect(**config)
            return connection
        else:
            print(err)

# Function to create the database if it doesn't exist
def create_database():
    try:
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
    connection = create_connection()
    if connection:
        cursor = connection.cursor()

        # Read and execute the schema.sql file
        with open('schema.sql', 'r') as f:
            schema_sql = f.read()
        
        try:
            # Splitting by semicolon, but also ensuring each statement is committed.
            for statement in schema_sql.split(';'):  # Splitting SQL by semicolon
                if statement.strip():
                    cursor.execute(statement)
                    print(f"Executed: {statement.strip()[:50]}...")  # Short print for executed statements
            
            # Commit the transaction to ensure data is saved to the database
            connection.commit()
            print("Schema and data committed successfully!")

        except mysql.connector.Error as err:
            print(f"Error executing schema.sql: {err}")
        
        # Close cursor and connection
        cursor.close()
        connection.close()

if __name__ == "__main__":
    initialize_database()