from fastapi import APIRouter, HTTPException, Request, status, Depends
from pydantic import BaseModel, EmailStr, constr, validator
import smtplib
import random
from email.message import EmailMessage
from email.utils import formataddr
import logging
from datetime import datetime, timedelta
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
import psycopg2
from psycopg2 import sql
from jose import jwt
from typing import Optional
import datetime as dt  # Separate import for datetime module
from app.Database.db_connection import get_db_connection

router = APIRouter()

# ========== CONFIGURATION ==========
# Email Configuration
EMAIL_CONFIG = {
    "address": "thandiechongwe@gmail.com",
    "password": "rkrefuxopjmdmwgp",  # App Password
    "sender_name": "Healthcare Verification System",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465
}

# Application Configuration
APP_CONFIG = {
    "verification_code_expiry_hours": 24,
    "resend_cooldown_minutes": 15,
    "secret_key": "memodzashe",  # Change this to a strong secret key
    "algorithm": "HS256",
    "access_token_expire_minutes": 30
}

# ========== SETUP ==========
# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# ========== MODELS ==========
class SignUpRequest(BaseModel):
    email: EmailStr
    password: constr(min_length=8)  # type: ignore
    first_name: constr(min_length=1, max_length=50)  # type: ignore
    last_name: constr(min_length=1, max_length=50)  # type: ignore
    role: constr(pattern="^(nurse|doctor)$")  # type: ignore
    hospital_name: constr(min_length=1, max_length=100)  # type: ignore

    @validator('password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        if not any(not c.isalnum() for c in v):
            raise ValueError('Password must contain at least one special character')
        return v

class VerifyRequest(BaseModel):
    email: EmailStr
    verification_code: constr(min_length=6, max_length=6)  # type: ignore

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    role: str
    email: str

# ========== HELPER FUNCTIONS ==========
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, APP_CONFIG["secret_key"], algorithm=APP_CONFIG["algorithm"])
    return encoded_jwt

async def send_verification_email(to_email: str, code: str):
    """Send verification email with the code"""
    try:
        msg = EmailMessage()
        msg["Subject"] = "Your Verification Code for Healthcare Access"
        msg["From"] = formataddr((EMAIL_CONFIG["sender_name"], EMAIL_CONFIG["address"]))
        msg["To"] = to_email

        # Plain text version
        msg.set_content(f"""
        Healthcare Access Verification

        Your verification code is: {code}

        This code will expire in {APP_CONFIG["verification_code_expiry_hours"]} hours.

        If you didn't request this, please ignore this email.
        """)

        # HTML version - Fixed datetime reference
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #2563eb;">Healthcare Access Verification</h2>
                <p>Your verification code is:</p>
                <div style="background: #f3f4f6; padding: 10px; border-radius: 5px; 
                            display: inline-block; margin: 10px 0;">
                    <h3 style="margin: 0; color: #2563eb; font-size: 24px;">{code}</h3>
                </div>
                <p style="color: #6b7280;">This code expires in {APP_CONFIG["verification_code_expiry_hours"]} hours.</p>
                <hr style="border: 0; border-top: 1px solid #e5e7eb;">
                <small style="color: #9ca3af;">
                    © {dt.datetime.now().year} Healthcare System
                </small>
            </body>
        </html>
        """
        msg.add_alternative(html_content, subtype="html")

        with smtplib.SMTP_SSL(
            EMAIL_CONFIG["smtp_server"], 
            EMAIL_CONFIG["smtp_port"]
        ) as smtp:
            smtp.login(EMAIL_CONFIG["address"], EMAIL_CONFIG["password"])
            smtp.send_message(msg)

        logger.info(f"Verification email sent to {to_email}")

    except Exception as e:
        logger.error(f"Email sending failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification email"
        )

def cleanup_expired_data(cur):
    """Clean up expired verification tokens and temp user data"""
    try:
        expiry_hours = APP_CONFIG["verification_code_expiry_hours"]
        
        # Delete verification tokens
        cur.execute(sql.SQL("""
            DELETE FROM verification_tokens 
            WHERE created_at <= NOW() - INTERVAL '{} hours'
        """).format(sql.Literal(expiry_hours)))
        
        # Delete temp user data
        cur.execute(sql.SQL("""
            DELETE FROM temp_user_data 
            WHERE created_at <= NOW() - INTERVAL '{} hours'
        """).format(sql.Literal(expiry_hours)))
    except Exception as e:
        logger.error(f"Failed to clean up expired data: {str(e)}")
        raise

# ========== API ENDPOINTS ==========
@router.post("/sign-up", 
            status_code=status.HTTP_201_CREATED,
            tags=["Authentication"],
            summary="Register a new user",
            description="Creates a new user account and sends verification email")
async def sign_up(user: SignUpRequest):
    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Clean up expired data first
        cleanup_expired_data(cur)

        # Check if email already exists
        cur.execute("SELECT 1 FROM users WHERE email = %s", (user.email,))
        if cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Check for recent unverified codes
        cur.execute(sql.SQL("""
            SELECT 1 FROM verification_tokens 
            WHERE email = %s AND is_verified = FALSE
            AND created_at > NOW() - INTERVAL '{} minutes'
        """).format(sql.Literal(APP_CONFIG["resend_cooldown_minutes"])), 
                   (user.email,))
        if cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {APP_CONFIG['resend_cooldown_minutes']} minutes before requesting another code"
            )

        # Generate verification code
        verification_code = f"{random.randint(100000, 999999)}"
        hashed_password = get_password_hash(user.password)

        # Store user data temporarily
        cur.execute("""
            INSERT INTO temp_user_data 
            (email, password_hash, first_name, last_name, role, hospital_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                role = EXCLUDED.role,
                hospital_name = EXCLUDED.hospital_name,
                created_at = CURRENT_TIMESTAMP
        """, (
            user.email,
            hashed_password,
            user.first_name,
            user.last_name,
            user.role,
            user.hospital_name
        ))

        # Store verification code
        cur.execute("""
            INSERT INTO verification_tokens (email, verification_code)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET
                verification_code = EXCLUDED.verification_code,
                is_verified = FALSE,
                created_at = CURRENT_TIMESTAMP
        """, (user.email, verification_code))

        conn.commit()

        # Send verification email
        await send_verification_email(user.email, verification_code)

        return {
            "message": "Verification code sent to your email",
            "email": user.email
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign up failed for {user.email}: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration process failed"
        )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@router.post("/verify-email",
            status_code=status.HTTP_200_OK,
            tags=["Authentication"],
            summary="Verify email address",
            description="Verify user's email with the received code",
            response_model=TokenResponse)
async def verify_email(data: VerifyRequest):
    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Clean up expired data first
        cleanup_expired_data(cur)

        # Verify the code
        cur.execute(sql.SQL("""
            SELECT verification_code, is_verified
            FROM verification_tokens 
            WHERE email = %s 
            AND created_at > NOW() - INTERVAL '{} hours'
            FOR UPDATE
        """).format(sql.Literal(APP_CONFIG["verification_code_expiry_hours"])), 
                   (data.email,))
        record = cur.fetchone()

        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification code expired or not found"
            )

        stored_code, is_verified = record

        if is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already verified"
            )

        if data.verification_code != stored_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code"
            )

        # Get temporary user data
        cur.execute("""
            SELECT first_name, last_name, role, hospital_name, password_hash
            FROM temp_user_data
            WHERE email = %s
            FOR UPDATE
        """, (data.email,))
        user_data = cur.fetchone()

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration session expired. Please sign up again."
            )

        first_name, last_name, role, hospital_name, password_hash = user_data

        # Ensure hospital exists
        cur.execute("""
            INSERT INTO hospitals (hospital_name)
            VALUES (%s)
            ON CONFLICT (hospital_name) DO NOTHING
            RETURNING hospital_id
        """, (hospital_name,))
        hospital_id = cur.fetchone()
        
        if not hospital_id:
            cur.execute("""
                SELECT hospital_id FROM hospitals 
                WHERE hospital_name = %s
            """, (hospital_name,))
            hospital_id = cur.fetchone()

        # Create the user
        cur.execute("""
            INSERT INTO users 
            (email, password_hash, first_name, last_name, role, hospital_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING user_id
        """, (
            data.email,
            password_hash,
            first_name,
            last_name,
            role,
            hospital_id[0] if hospital_id else None
        ))
        user_result = cur.fetchone()
        if not user_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )
        user_id = user_result[0]

        # Mark as verified
        cur.execute("""
            UPDATE verification_tokens 
            SET is_verified = TRUE 
            WHERE email = %s
        """, (data.email,))

        # Remove temp data
        cur.execute("""
            DELETE FROM temp_user_data 
            WHERE email = %s
        """, (data.email,))

        conn.commit()

        # Create access token
        access_token_expires = timedelta(minutes=APP_CONFIG["access_token_expire_minutes"])
        access_token = create_access_token(
            data={"sub": data.email, "role": role, "user_id": user_id},
            expires_delta=access_token_expires
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user_id,
            "role": role,
            "email": data.email
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification process failed"
        )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()