from itsdangerous import URLSafeTimedSerializer
import os

serializer = URLSafeTimedSerializer(os.getenv('SECRET_KEY'))

def generate_activation_token(user_id):
    return serializer.dumps(user_id, salt='activate-account')

def verify_activation_token(token, expiration=3600):
    try:
        user_id = serializer.loads(token, salt='activate-account', max_age=expiration)
        return user_id
    except Exception:
        return None