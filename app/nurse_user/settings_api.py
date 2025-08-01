from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from jose import jwt, JWTError
from app.Database.db_connection import get_db_connection
import logging
import bcrypt

router = APIRouter()
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

class TokenRequest(BaseModel):
    token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None

class DeleteAccountRequest(BaseModel):
    password: str  # Require password confirmation for account deletion

class ProfileResponse(BaseModel):
    user_id: int
    email: str
    first_name: str
    last_name: str
    role: str
    hospital_name: str

def decode_token_get_nurse(token: str):
    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user_id")
        if role != "nurse":
            raise HTTPException(status_code=403, detail="Access denied: Only nurses can access this endpoint")
        return user_id
    except JWTError as e:
        logger.error(f"Token decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

@router.post("/user-details", response_model=ProfileResponse, tags=["settings"], summary="Get nurse profile information")
async def get_nurse_profile(token_req: TokenRequest):
    user_id = decode_token_get_nurse(token_req.token)
    conn, cur = None, None
    
    try:
        conn, cur = get_db_connection()
        
        # Get nurse profile with hospital information
        cur.execute("""
            SELECT 
                u.user_id,
                u.email,
                u.first_name,
                u.last_name,
                u.role,
                h.hospital_name
            FROM users u
            LEFT JOIN hospitals h ON u.hospital_id = h.hospital_id
            WHERE u.user_id = %s AND u.role = 'nurse'
        """, (user_id,))
        
        user_data = cur.fetchone()
        
        if not user_data:
            raise HTTPException(status_code=404, detail="Nurse profile not found")
        
        return ProfileResponse(
            user_id=user_data["user_id"],
            email=user_data["email"],
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
            role=user_data["role"],
            hospital_name=user_data["hospital_name"] if user_data["hospital_name"] else "No Hospital Assigned"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching nurse profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch profile")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@router.put("/password/change", tags=["settings"], summary="Change nurse password")
async def change_password(token_req: TokenRequest, request: ChangePasswordRequest):
    user_id = decode_token_get_nurse(token_req.token)
    conn, cur = None, None
    
    try:
        conn, cur = get_db_connection()
        
        # Get current password hash
        cur.execute("SELECT password_hash FROM users WHERE user_id = %s AND role = 'nurse'", (user_id,))
        user_data = cur.fetchone()
        
        if not user_data:
            raise HTTPException(status_code=404, detail="Nurse not found")
        
        # Verify current password
        if not verify_password(request.current_password, user_data["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Validate new password
        if len(request.new_password) < 8:
            raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
        
        # Hash new password
        new_password_hash = hash_password(request.new_password)
        
        # Update password
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s AND role = 'nurse'",
            (new_password_hash, user_id)
        )
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=400, detail="Failed to update password")
        
        conn.commit()
        
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Error changing password: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to change password")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@router.put("/profile/update", response_model=ProfileResponse, tags=["settings"], summary="Update nurse profile")
async def update_profile(token_req: TokenRequest, request: UpdateProfileRequest):
    user_id = decode_token_get_nurse(token_req.token)
    conn, cur = None, None
    
    try:
        conn, cur = get_db_connection()
        
        # Build update query dynamically based on provided fields
        update_fields = []
        update_values = []
        
        if request.first_name is not None:
            update_fields.append("first_name = %s")
            update_values.append(request.first_name)
        
        if request.last_name is not None:
            update_fields.append("last_name = %s")
            update_values.append(request.last_name)
        
        if request.email is not None:
            # Check if email already exists
            cur.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (request.email, user_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Email already exists")
            
            update_fields.append("email = %s")
            update_values.append(request.email)
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields provided for update")
        
        # Add user_id to values for WHERE clause
        update_values.append(user_id)
        
        # Execute update
        update_query = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = %s AND role = 'nurse'"
        cur.execute(update_query, update_values)
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Nurse not found or no changes made")
        
        conn.commit()
        
        # Get updated profile
        cur.execute("""
            SELECT 
                u.user_id,
                u.email,
                u.first_name,
                u.last_name,
                u.role,
                h.hospital_name
            FROM users u
            LEFT JOIN hospitals h ON u.hospital_id = h.hospital_id
            WHERE u.user_id = %s AND u.role = 'nurse'
        """, (user_id,))
        
        updated_user = cur.fetchone()
        
        return ProfileResponse(
            user_id=updated_user["user_id"],
            email=updated_user["email"],
            first_name=updated_user["first_name"],
            last_name=updated_user["last_name"],
            role=updated_user["role"],
            hospital_name=updated_user["hospital_name"] if updated_user["hospital_name"] else "No Hospital Assigned"
        )
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Error updating profile: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to update profile")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@router.delete("/account/delete", tags=["settings"], summary="Delete nurse account permanently")
async def delete_account(token_req: TokenRequest, request: DeleteAccountRequest):
    user_id = decode_token_get_nurse(token_req.token)
    conn, cur = None, None
    
    try:
        conn, cur = get_db_connection()
        
        # Get user data for verification
        cur.execute("SELECT password_hash, email FROM users WHERE user_id = %s AND role = 'nurse'", (user_id,))
        user_data = cur.fetchone()
        
        if not user_data:
            raise HTTPException(status_code=404, detail="Nurse not found")
        
        # Verify password before deletion
        if not verify_password(request.password, user_data["password_hash"]):
            raise HTTPException(status_code=400, detail="Password is incorrect")
        
        # Check if nurse has created any patients
        cur.execute("SELECT COUNT(*) as patient_count FROM patients WHERE created_by = %s", (user_id,))
        patient_count = cur.fetchone()["patient_count"]
        
        if patient_count > 0:
            # Instead of preventing deletion, we'll set created_by to NULL for existing patients
            cur.execute("UPDATE patients SET created_by = NULL WHERE created_by = %s", (user_id,))
            logger.info(f"Updated {patient_count} patient records to remove reference to deleted nurse {user_id}")
        
        # Delete the nurse account
        cur.execute("DELETE FROM users WHERE user_id = %s AND role = 'nurse'", (user_id,))
        
        if cur.rowcount == 0:
            raise HTTPException(status_code=400, detail="Failed to delete account")
        
        conn.commit()
        
        return {
            "message": "Account deleted successfully",
            "deleted_user_email": user_data["email"],
            "patients_affected": patient_count
        }
        
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Error deleting account: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete account")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
