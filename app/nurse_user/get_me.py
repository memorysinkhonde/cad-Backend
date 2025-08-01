from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from jose import jwt, JWTError
from app.Database.db_connection import get_db_connection
import logging

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# JWT configuration
APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

# Pydantic model for token input
class TokenRequest(BaseModel):
    token: str

@router.post(
    "/user-details",
    status_code=status.HTTP_200_OK,
    tags=["nurse_user"],
    summary="Get user details from token",
    description="Returns full user details decoded from JWT token"
)
async def get_user_details(token_req: TokenRequest):
    token = token_req.token

    # Decode token and extract payload
    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token does not contain a valid user ID"
            )
    except JWTError as e:
        logger.error(f"Token decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        cur.execute("""
            SELECT u.user_id, u.email, u.first_name, u.last_name, u.role, u.hospital_id, h.hospital_name
            FROM users u
            LEFT JOIN hospitals h ON u.hospital_id = h.hospital_id
            WHERE u.user_id = %s
        """, (user_id,))

        user = cur.fetchone()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Return user info as a dictionary
        return {
            "user_id": user.get("user_id"),
            "email": user.get("email"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "role": user.get("role"),
            "hospital_id": user.get("hospital_id"),
            "hospital_name": user.get("hospital_name"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user details"
        )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
