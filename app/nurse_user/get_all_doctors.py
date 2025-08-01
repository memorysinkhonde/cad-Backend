from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from jose import jwt, JWTError
from app.Database.db_connection import get_db_connection
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

class TokenRequest(BaseModel):
    token: str

class DoctorResponse(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str

def decode_token_get_user(token: str):
    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user_id")
        return user_id
    except JWTError as e:
        logger.error(f"Token decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@router.post("/doctors", response_model=list[DoctorResponse], tags=["users"], summary="Get all doctors in nurse's hospital")
async def get_doctors(token_req: TokenRequest):
    user_id = decode_token_get_user(token_req.token)
    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Get hospital_id for the nurse user
        cur.execute("SELECT hospital_id FROM users WHERE user_id = %s AND role = 'nurse'", (user_id,))
        res = cur.fetchone()
        if not res or not res["hospital_id"]:
            raise HTTPException(status_code=404, detail="Nurse user or hospital not found")
        hospital_id = res["hospital_id"]

        # Get all doctors for that hospital
        cur.execute("""
            SELECT user_id, email, first_name, last_name
            FROM users
            WHERE hospital_id = %s AND role = 'doctor'
        """, (hospital_id,))

        doctors = []
        for row in cur.fetchall():
            doctors.append(DoctorResponse(
                user_id=row["user_id"],
                email=row["email"],
                first_name=row["first_name"],
                last_name=row["last_name"]
            ))

        return doctors

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching doctors: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch doctors")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
