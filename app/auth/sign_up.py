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
from typing import Optional, Literal
import datetime as dt  # Separate import for datetime module
from app.Database.db_connection import get_db_connection

router = APIRouter()

# ========== CONFIGURATION ==========
# Email Configuration
EMAIL_CONFIG = {
    "address": "thandiechongwe@gmail.com",
    "password": "rkrefuxopjmdmwgp",  # App Password
    "sender_name": "Healthcare Management System",
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
    role: Literal["nurse", "doctor"]  # Enforce allowed values
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
        msg["Subject"] = "Healthcare Management System - Email Verification Required"
        msg["From"] = formataddr((EMAIL_CONFIG["sender_name"], EMAIL_CONFIG["address"]))
        msg["To"] = to_email

        # Plain text version
        msg.set_content(f"""
Healthcare Access Verification System

Dear User,

Thank you for registering with our Healthcare Management System.

Your verification code is: {code}

Please enter this code to complete your registration. This code will expire in {APP_CONFIG["verification_code_expiry_hours"]} hours for security purposes.

If you did not request this verification, please ignore this email and contact our support team.

Best regards,
Healthcare Management Team

---
This is an automated message. Please do not reply to this email.
        """)

        # Professional HTML version
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Email Verification</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8fafc; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; text-align: center;">
                    <div style="background-color: #ffffff; border-radius: 50%; width: 80px; height: 80px; margin: 0 auto 20px; display: flex; align-items: center; justify-content: center;">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M9 12L11 14L15 10M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="#667eea" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </div>
                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">Healthcare Management System</h1>
                    <p style="color: #e2e8f0; margin: 10px 0 0; font-size: 16px;">Email Verification Required</p>
                </div>
                
                <!-- Content -->
                <div style="padding: 40px 30px;">
                    <h2 style="color: #1a202c; margin: 0 0 20px; font-size: 24px; font-weight: 600;">Verify Your Email Address</h2>
                    
                    <p style="color: #4a5568; margin: 0 0 25px; font-size: 16px;">
                        Thank you for registering with our Healthcare Management System. To complete your registration and secure your account, please verify your email address using the verification code below.
                    </p>
                    
                    <!-- Verification Code Box -->
                    <div style="background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%); border: 2px solid #e2e8f0; border-radius: 12px; padding: 30px; text-align: center; margin: 30px 0;">
                        <p style="color: #718096; margin: 0 0 15px; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">Your Verification Code</p>
                        <div style="background-color: #ffffff; border: 2px dashed #667eea; border-radius: 8px; padding: 20px; display: inline-block;">
                            <span style="font-family: 'Courier New', monospace; font-size: 32px; font-weight: bold; color: #667eea; letter-spacing: 4px;">{code}</span>
                        </div>
                        <p style="color: #a0aec0; margin: 15px 0 0; font-size: 12px;">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align: middle; margin-right: 8px;">
                                <path d="M12 2C6.48 2 2 6.48 2 12S6.48 22 12 22 22 17.52 22 12 17.52 2 12 2ZM13 17H11V15H13V17ZM13 13H11V7H13V13Z" fill="#a0aec0"/>
                            </svg>
                            This code expires in {APP_CONFIG["verification_code_expiry_hours"]} hours
                        </p>
                    </div>
                    
                    <!-- Instructions -->
                    <div style="background-color: #ebf8ff; border-left: 4px solid #3182ce; padding: 20px; margin: 25px 0; border-radius: 0 8px 8px 0;">
                        <h3 style="color: #2c5282; margin: 0 0 10px; font-size: 16px; font-weight: 600;">How to use this code:</h3>
                        <ol style="color: #2d3748; margin: 0; padding-left: 20px; font-size: 14px;">
                            <li style="margin-bottom: 5px;">Return to the registration page</li>
                            <li style="margin-bottom: 5px;">Enter the 6-digit verification code above</li>
                            <li style="margin-bottom: 5px;">Click "Verify Email" to complete your registration</li>
                        </ol>
                    </div>
                    
                    <!-- Security Notice -->
                    <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 15px; margin: 25px 0; border-radius: 0 8px 8px 0;">
                        <p style="color: #92400e; margin: 0; font-size: 14px;">
                            <strong>Security Notice:</strong> If you did not request this verification, please ignore this email. Your account will remain unverified and no further action is required.
                        </p>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f7fafc; padding: 30px; text-align: center; border-top: 1px solid #e2e8f0;">
                    <p style="color: #718096; margin: 0 0 10px; font-size: 14px;">
                        Need help? Contact our support team at <a href="mailto:support@healthcare.com" style="color: #3182ce; text-decoration: none;">support@healthcare.com</a>
                    </p>
                    <p style="color: #a0aec0; margin: 0; font-size: 12px;">
                        © {dt.datetime.now().year} Healthcare Management System. All rights reserved.
                    </p>
                    <p style="color: #cbd5e0; margin: 10px 0 0; font-size: 11px;">
                        This is an automated message. Please do not reply to this email.
                    </p>
                </div>
            </div>
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
        
        # Delete expired verification tokens (both verified and unverified)
        cur.execute(sql.SQL("""
            DELETE FROM verification_tokens 
            WHERE created_at <= NOW() - INTERVAL '{} hours'
        """).format(sql.Literal(expiry_hours)))
        
        # Delete expired temp user data
        cur.execute(sql.SQL("""
            DELETE FROM temp_user_data 
            WHERE created_at <= NOW() - INTERVAL '{} hours'
        """).format(sql.Literal(expiry_hours)))
        
        logger.info("Expired verification data cleaned up successfully")
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

        # Store verification code - Delete any existing token first to ensure clean state
        cur.execute("""
            DELETE FROM verification_tokens WHERE email = %s
        """, (user.email,))
        
        # FIXED: Remove duplicate VALUES clause
        cur.execute("""
            INSERT INTO verification_tokens (email, verification_code, is_verified, created_at)
            VALUES (%s, %s, FALSE, CURRENT_TIMESTAMP)
        """, (user.email, verification_code))
        
        logger.info(f"New verification token created for {user.email}")

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
            logger.warning(f"Verification attempt failed - no valid token found for email: {data.email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification code expired or not found"
            )

        stored_code, is_verified = record
        logger.info(f"Verification attempt for {data.email}: is_verified={is_verified}")

        if is_verified:
            logger.warning(f"Verification attempt failed - email already verified: {data.email}")
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

        if not hospital_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create or find hospital record"
            )

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
            hospital_id[0]
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
