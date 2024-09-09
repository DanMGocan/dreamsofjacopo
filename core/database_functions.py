###########################################################################

# Use Prepared Statements: Always use parameterized queries (%s) to prevent SQL injection.
# Handle Exceptions: Catch exceptions to ensure that errors (like duplicate entries or connection issues) are managed properly.
# Commit Transactions: Make sure to call connection.commit() to persist data in the database.
# Close Connections: Always close the cursor and the connection after you're done to prevent resource leaks.

#################################################################################

import mysql.connector

# Database connection configuration
config = {
    'user': 'root',
    'password': 'your_password',
    'host': '127.0.0.1',
    'database': 'your_database_name'
}

def insert_user(name, email):
    try:
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()

        # Insert a new user
        insert_query = "INSERT INTO users (name, email) VALUES (%s, %s)"
        cursor.execute(insert_query, (name, email))

        # Commit the transaction
        connection.commit()

        print(f"User {name} added successfully!")

    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

# Example usage
insert_user('Charlie Brown', 'charlie.brown@example.com')

def insert_post(user_id, content):
    try:
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()

        # Insert a new post
        insert_query = "INSERT INTO posts (user_id, content) VALUES (%s, %s)"
        cursor.execute(insert_query, (user_id, content))

        # Commit the transaction
        connection.commit()

        print(f"Post added for user_id {user_id}!")

    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

# Example usage
insert_post(1, 'This is Charlie Brown’s first post')

def insert_multiple_users(users):
    try:
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()

        # Insert multiple users
        insert_query = "INSERT INTO users (name, email) VALUES (%s, %s)"
        cursor.executemany(insert_query, users)

        # Commit the transaction
        connection.commit()

        print(f"{cursor.rowcount} users added successfully!")

    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

# Example usage: Inserting multiple users
users_data = [
    ('Snoopy', 'snoopy@example.com'),
    ('Lucy Van Pelt', 'lucy@example.com'),
    ('Linus Van Pelt', 'linus@example.com')
]

insert_multiple_users(users_data)
