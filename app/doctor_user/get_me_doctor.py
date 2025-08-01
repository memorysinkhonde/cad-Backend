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

# Request body model
class TokenRequest(BaseModel):
    token: str

@router.post(
    "/user-details-doctor",
    status_code=status.HTTP_200_OK,
    tags=["doctor_user"],
    summary="Get doctor details from token",
    description="Returns full doctor details decoded from JWT token"
)
async def get_doctor_details(token_req: TokenRequest):
    token = token_req.token

    try:
        # Decode the JWT
        payload = jwt.decode(
            token,
            APP_CONFIG["secret_key"],
            algorithms=[APP_CONFIG["algorithm"]]
        )

        user_id = payload.get("user_id")
        role = payload.get("role")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing user_id"
            )

        if role != "doctor":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Only doctors allowed."
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

        # Query doctor + hospital info
        cur.execute("""
            SELECT u.user_id, u.email, u.first_name, u.last_name, u.role,
                   u.hospital_id, h.hospital_name
            FROM users u
            LEFT JOIN hospitals h ON u.hospital_id = h.hospital_id
            WHERE u.user_id = %s AND u.role = 'doctor'
        """, (user_id,))

        row = cur.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doctor not found"
            )

        # Map row to dictionary with specific field names
        doctor_data = {
            "user_id": row["user_id"],
            "email": row["email"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "role": row["role"],
            "hospital_id": row["hospital_id"],
            "hospital_name": row["hospital_name"]
        }

        return doctor_data

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch doctor details"
        )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
