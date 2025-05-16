import random
import string
from passlib.context import CryptContext

# Setup the context for password hashing (e.g., using bcrypt)
# It's good practice to define this once and reuse it.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hashes a plain text password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

# Used as a random password when a user logs in with Google or LinkedIn
def generate_password(length=18):
    # Define the set of characters to use for the password
    characters = string.ascii_letters + string.digits + string.punctuation
    # Generate a password by randomly selecting characters from the set
    password = ''.join(random.choice(characters) for i in range(length))
    return password
