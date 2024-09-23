import random
import string

# Used as a random password when a user logs in with Google or LinkedIn
def generate_password(length=18):
    # Define the set of characters to use for the password
    characters = string.ascii_letters + string.digits + string.punctuation
    # Generate a password by randomly selecting characters from the set
    password = ''.join(random.choice(characters) for i in range(length))
    return password