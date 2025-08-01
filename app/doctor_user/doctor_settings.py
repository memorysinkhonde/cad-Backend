from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, constr
from jose import jwt, JWTError
from app.Database.db_connection import get_db_connection
import logging
import bcrypt

router = APIRouter()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

# Token-only input
class TokenRequest(BaseModel):
    token: str

# Update profile input
class ProfileUpdateRequest(BaseModel):
    token: str
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: EmailStr

# Change password input
class ChangePasswordRequest(BaseModel):
    token: str
    old_password: constr(min_length=6) # type: ignore
    new_password: constr(min_length=6) # type: ignore

# ✅ Delete doctor account
@router.delete(
    "/doctor/delete-account",
    status_code=status.HTTP_200_OK,
    tags=["doctor_user"],
    summary="Delete doctor account",
    description="Deletes the authenticated doctor's account."
)
async def delete_doctor_account(token_req: TokenRequest):
    token = token_req.token

    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not user_id or role != "doctor":
            raise HTTPException(status_code=403, detail="Unauthorized: Only doctors can delete their account.")
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()
        cur.execute("SELECT * FROM users WHERE user_id = %s AND role = 'doctor'", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Doctor not found")

        cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        conn.commit()
        return {"message": "Doctor account deleted successfully."}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Error deleting doctor: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Internal server error while deleting doctor.")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ✅ Update doctor profile
@router.put(
    "/doctor/update-profile",
    status_code=status.HTTP_200_OK,
    tags=["doctor_user"],
    summary="Update doctor profile",
    description="Updates the authenticated doctor's profile."
)
async def update_doctor_profile(update_req: ProfileUpdateRequest):
    try:
        payload = jwt.decode(update_req.token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not user_id or role != "doctor":
            raise HTTPException(status_code=403, detail="Unauthorized: Only doctors can update profile.")
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        cur.execute("SELECT * FROM users WHERE user_id = %s AND role = 'doctor'", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Doctor not found")

        cur.execute("""
            UPDATE users
            SET first_name = %s,
                last_name = %s,
                email = %s
            WHERE user_id = %s
        """, (
            update_req.first_name,
            update_req.last_name,
            update_req.email,
            user_id
        ))

        conn.commit()
        return {"message": "Doctor profile updated successfully."}

    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Error updating doctor profile: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Internal server error while updating profile.")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ✅ Get doctor profile
@router.post(
    "/doctor/user-details-doctor-all",
    status_code=status.HTTP_200_OK,
    tags=["doctor_user"],
    summary="Get doctor profile",
    description="Returns the profile of the authenticated doctor."
)
async def get_doctor_profile(token_req: TokenRequest):
    token = token_req.token

    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        logger.info(f"[DEBUG] Token payload: user_id={user_id}, role={role}")
        if not user_id or role != "doctor":
            logger.warning(f"[DEBUG] Access denied: user_id={user_id}, role={role}")
            raise HTTPException(status_code=403, detail="Access denied: not a doctor.")
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        cur.execute("""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.role, u.hospital_id, h.hospital_name
            FROM users u
            LEFT JOIN hospitals h ON u.hospital_id = h.hospital_id
            WHERE u.user_id = %s AND u.role = 'doctor'
        """, (user_id,))
        user = cur.fetchone()
        logger.info(f"[DEBUG] DB query result: {user}")
        if not user:
            logger.warning(f"[DEBUG] Doctor not found for user_id={user_id}")
            raise HTTPException(status_code=404, detail="Doctor not found")

        return {"doctor": user}

    except Exception as e:
        logger.error(f"Error fetching doctor data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch doctor profile")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# ✅ Change doctor password
@router.put(
    "/doctor/change-password",
    status_code=status.HTTP_200_OK,
    tags=["doctor_user"],
    summary="Change doctor password",
    description="Allows a doctor to change their password after verifying the old password."
)
async def change_password(req: ChangePasswordRequest):
    try:
        payload = jwt.decode(req.token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not user_id or role != "doctor":
            raise HTTPException(status_code=403, detail="Unauthorized access.")
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Fetch existing hashed password
        cur.execute("SELECT password_hash FROM users WHERE user_id = %s AND role = 'doctor'", (user_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Doctor not found")

        current_hashed = row["password_hash"].encode('utf-8')

        if not bcrypt.checkpw(req.old_password.encode('utf-8'), current_hashed):
            raise HTTPException(status_code=400, detail="Old password is incorrect")

        new_hashed = bcrypt.hashpw(req.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        cur.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (new_hashed, user_id))
        conn.commit()

        return {"message": "Password changed successfully"}

    except Exception as e:
        logger.error(f"Error changing password: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to change password.")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
