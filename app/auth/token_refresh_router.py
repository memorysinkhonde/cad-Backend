from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from jose import jwt, JWTError
from datetime import datetime, timedelta
from app.Database.db_connection import get_db_connection
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",  # Use your actual secret here
    "algorithm": "HS256",
    "access_token_expire_minutes": 30,
}

class TokenRefreshRequest(BaseModel):
    token: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    role: str
    email: str

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, APP_CONFIG["secret_key"], algorithm=APP_CONFIG["algorithm"])
    return encoded_jwt

@router.post(
    "/refresh-token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
    summary="Refresh JWT token",
    description="Validate the current JWT token and return a new token with fresh expiry."
)
async def refresh_token(token_req: TokenRefreshRequest):
    token = token_req.token
    conn, cur = None, None
    try:
        # Decode and validate current token (will raise if expired or invalid)
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        email = payload.get("sub")
        role = payload.get("role")

        if user_id is None or email is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # Check if user still exists in database
        conn, cur = get_db_connection()
        cur.execute("SELECT user_id, email, role FROM users WHERE user_id = %s", (user_id,))
        user_record = cur.fetchone()
        
        if not user_record:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify that the token data matches the database record
        if (user_record["email"] != email or 
            user_record["role"] != role or 
            user_record["user_id"] != user_id):
            raise HTTPException(status_code=401, detail="Token data mismatch with database")

        # Create new token with fresh expiry
        access_token_expires = timedelta(minutes=APP_CONFIG["access_token_expire_minutes"])
        new_token = create_access_token(
            data={"sub": email, "user_id": user_id, "role": role},
            expires_delta=access_token_expires,
        )

        return {
            "access_token": new_token,
            "token_type": "bearer",
            "user_id": user_id,
            "role": role,
            "email": email,
        }

    except HTTPException:
        raise
    except JWTError as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except Exception as e:
        logger.error(f"Error during token refresh: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to refresh token")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
