from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from datetime import timedelta, datetime
from jose import jwt
from passlib.context import CryptContext
import logging

from app.Database.db_connection import get_db_connection  # Adjust the path if needed

# ========== SETUP ==========
router = APIRouter()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security config
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# App config (keep secret key safe in production)
APP_CONFIG = {
    "secret_key": "memodzashe",  # Replace with a strong secure key
    "algorithm": "HS256",
    "access_token_expire_minutes": 30
}

# ========== MODELS ==========
class SignInRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    role: str
    email: str

# ========== TOKEN HELPER ==========
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, APP_CONFIG["secret_key"], algorithm=APP_CONFIG["algorithm"])
    return encoded_jwt

# ========== SIGN-IN ROUTE ==========
@router.post(
    "/sign-in",
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
    summary="Sign in a verified user",
    description="Authenticate user and return JWT access token",
    response_model=TokenResponse,
)
async def sign_in(credentials: SignInRequest):
    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Check if user exists
        cur.execute(
            """
            SELECT user_id, password_hash, role, email
            FROM users
            WHERE email = %s
            """,
            (credentials.email,),
        )
        record = cur.fetchone()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Destructure the returned dictionary
        user_id = record["user_id"]
        password_hash = record["password_hash"]
        role = record["role"]
        email = record["email"]

        # Verify password
        if not pwd_context.verify(credentials.password, password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Create access token
        access_token_expires = timedelta(minutes=APP_CONFIG["access_token_expire_minutes"])
        access_token = create_access_token(
            data={"sub": email, "user_id": user_id, "role": role},
            expires_delta=access_token_expires,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user_id,
            "role": role,
            "email": email,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign-in failed for {credentials.email}: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sign-in process failed",
        )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
