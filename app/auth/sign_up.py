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
    
    @validator('first_name', 'last_name')
    def validate_names(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty or contain only whitespace')
        # Remove extra whitespace and capitalize properly
        return ' '.join(word.capitalize() for word in v.strip().split())
    
    @validator('hospital_name')
    def validate_hospital_name(cls, v):
        if not v.strip():
            raise ValueError('Hospital name cannot be empty or contain only whitespace')
        # Remove extra whitespace but preserve original capitalization
        return ' '.join(v.strip().split())

class VerifyRequest(BaseModel):
    email: EmailStr
    verification_code: constr(min_length=6, max_length=6)  # type: ignore
    
    @validator('verification_code')
    def validate_verification_code(cls, v):
        if not v.isdigit():
            raise ValueError('Verification code must contain only digits')
        return v

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
        expired_tokens = cur.rowcount
        
        # Delete expired temp user data
        cur.execute(sql.SQL("""
            DELETE FROM temp_user_data 
            WHERE created_at <= NOW() - INTERVAL '{} hours'
        """).format(sql.Literal(expiry_hours)))
        expired_temp_data = cur.rowcount
        
        logger.info(f"Cleanup completed: {expired_tokens} expired tokens, {expired_temp_data} expired temp records removed")
    except Exception as e:
        logger.error(f"Failed to clean up expired data: {str(e)}")
        raise

def force_cleanup_email_data(cur, email: str):
    """Aggressively clean up ALL data related to an email to ensure fresh start"""
    try:
        # Step 1: Check if user exists
        cur.execute("SELECT user_id, email FROM users WHERE email = %s", (email,))
        existing_user = cur.fetchone()
        if existing_user:
            logger.warning(f"Email {email} already exists in users table (ID: {existing_user['user_id']})")
            return False, f"Email already registered (User ID: {existing_user['user_id']})"
        
        # Step 2: Force delete ALL verification tokens for this email (regardless of status)
        cur.execute("DELETE FROM verification_tokens WHERE email = %s", (email,))
        tokens_removed = cur.rowcount
        
        # Step 3: Force delete ALL temp user data for this email
        cur.execute("DELETE FROM temp_user_data WHERE email = %s", (email,))
        temp_data_removed = cur.rowcount
        
        # Step 4: Double-check no data remains
        cur.execute("SELECT COUNT(*) as count FROM verification_tokens WHERE email = %s", (email,))
        remaining_tokens = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) as count FROM temp_user_data WHERE email = %s", (email,))
        remaining_temp = cur.fetchone()['count']
        
        if remaining_tokens > 0 or remaining_temp > 0:
            logger.error(f"CRITICAL: Failed to completely clean data for {email} - tokens: {remaining_tokens}, temp: {remaining_temp}")
            return False, "Failed to clean existing data"
        
        logger.info(f"Force cleanup for {email}: {tokens_removed} tokens, {temp_data_removed} temp records removed")
        return True, "Complete cleanup successful"
        
    except Exception as e:
        logger.error(f"Force cleanup failed for {email}: {str(e)}")
        return False, f"Cleanup error: {str(e)}"

def verify_database_integrity(cur, email: str):
    """Verify database integrity for email verification process"""
    try:
        # Check for orphaned verification tokens (tokens without corresponding temp_user_data)
        cur.execute("""
            SELECT COUNT(*) as count FROM verification_tokens vt
            LEFT JOIN temp_user_data td ON vt.email = td.email
            WHERE vt.email = %s AND td.email IS NULL
        """, (email,))
        orphaned_tokens = cur.fetchone()['count']
        
        if orphaned_tokens > 0:
            logger.warning(f"Found {orphaned_tokens} orphaned verification tokens for {email}, cleaning up...")
            cur.execute("DELETE FROM verification_tokens WHERE email = %s AND email NOT IN (SELECT email FROM temp_user_data)", (email,))
        
        # Check for orphaned temp_user_data (temp data without corresponding verification tokens)
        cur.execute("""
            SELECT COUNT(*) as count FROM temp_user_data td
            LEFT JOIN verification_tokens vt ON td.email = vt.email
            WHERE td.email = %s AND vt.email IS NULL
        """, (email,))
        orphaned_temp_data = cur.fetchone()['count']
        
        if orphaned_temp_data > 0:
            logger.warning(f"Found {orphaned_temp_data} orphaned temp user data for {email}, cleaning up...")
            cur.execute("DELETE FROM temp_user_data WHERE email = %s AND email NOT IN (SELECT email FROM verification_tokens)", (email,))
        
        return True
    except Exception as e:
        logger.error(f"Database integrity check failed for {email}: {str(e)}")
        return False

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

        # Force cleanup any existing verification data for this email and check if user exists
        cleanup_success, cleanup_message = force_cleanup_email_data(cur, user.email)
        if not cleanup_success:
            logger.info(f"Sign-up blocked: {cleanup_message} for {user.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered. Please log in instead."
            )

        # Check for recent unverified codes (rate limiting)
        cur.execute(sql.SQL("""
            SELECT created_at FROM verification_tokens 
            WHERE email = %s AND is_verified = FALSE
            AND created_at > NOW() - INTERVAL '{} minutes'
            ORDER BY created_at DESC
            LIMIT 1
        """).format(sql.Literal(APP_CONFIG["resend_cooldown_minutes"])), 
                   (user.email,))
        recent_token = cur.fetchone()
        
        if recent_token:
            time_remaining = APP_CONFIG['resend_cooldown_minutes'] - int(
                (datetime.utcnow() - recent_token['created_at']).total_seconds() / 60
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {max(1, time_remaining)} more minutes before requesting another code"
            )

        # Store verification code - Data is already cleaned up
        # Generate verification code
        verification_code = f"{random.randint(100000, 999999)}"
        hashed_password = get_password_hash(user.password)

        # Store user data temporarily (fresh insert after cleanup)
        cur.execute("""
            INSERT INTO temp_user_data 
            (email, password_hash, first_name, last_name, role, hospital_name)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user.email,
            hashed_password,
            user.first_name,
            user.last_name,
            user.role,
            user.hospital_name
        ))

        # Create new verification token (guaranteed to be fresh)
        cur.execute("""
            INSERT INTO verification_tokens (email, verification_code, is_verified, created_at)
            VALUES (%s, %s, FALSE, CURRENT_TIMESTAMP)
        """, (user.email, verification_code))
        
        logger.info(f"New verification token created for {user.email}")

        conn.commit()

        # Send verification email - if this fails, we should still inform user that code was created
        try:
            await send_verification_email(user.email, verification_code)
            logger.info(f"Verification email successfully sent to {user.email}")
        except HTTPException as email_error:
            # If email sending fails, we should still let the user know the code was created
            # but inform them about email delivery issues
            logger.error(f"Failed to send verification email to {user.email}: {email_error.detail}")
            return {
                "message": "Verification code created but email delivery failed. Please contact support.",
                "email": user.email,
                "email_sent": False
            }

        return {
            "message": "Verification code sent to your email",
            "email": user.email,
            "email_sent": True
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
        
        # Verify database integrity for this email
        verify_database_integrity(cur, data.email)

        # CRITICAL: Triple check that email is not already registered
        cur.execute("SELECT user_id, email FROM users WHERE email = %s", (data.email,))
        existing_user = cur.fetchone()
        if existing_user:
            logger.error(f"CRITICAL: Verification attempt for already registered user: {data.email} (ID: {existing_user['user_id'] if existing_user else 'unknown'})")
            # Aggressively clean up any orphaned verification data
            cur.execute("DELETE FROM verification_tokens WHERE email = %s", (data.email,))
            cur.execute("DELETE FROM temp_user_data WHERE email = %s", (data.email,))
            conn.commit()  # Commit the cleanup immediately
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered. Please log in instead."
            )

        # Debug: Check current state of verification data
        cur.execute("SELECT COUNT(*) as count FROM verification_tokens WHERE email = %s", (data.email,))
        token_result = cur.fetchone()
        token_count = token_result['count'] if token_result else 0
        
        cur.execute("SELECT COUNT(*) as count FROM temp_user_data WHERE email = %s", (data.email,))
        temp_result = cur.fetchone()
        temp_count = temp_result['count'] if temp_result else 0
        
        logger.info(f"Pre-verification state for {data.email}: {token_count} tokens, {temp_count} temp records")

        # Get the verification token with all necessary info
        cur.execute("""
            SELECT 
                vt.verification_code, 
                vt.is_verified, 
                vt.created_at,
                vt.token_id,
                td.first_name,
                td.last_name,
                td.role,
                td.hospital_name,
                td.password_hash,
                td.temp_id
            FROM verification_tokens vt
            INNER JOIN temp_user_data td ON vt.email = td.email
            WHERE vt.email = %s 
            AND vt.created_at > NOW() - INTERVAL %s
            FOR UPDATE
        """, (data.email, f"{APP_CONFIG['verification_code_expiry_hours']} hours"))
        
        verification_record = cur.fetchone()

        if not verification_record:
            logger.warning(f"Verification attempt failed - no valid token/temp data found for: {data.email}")
            # Clean up any orphaned data
            cur.execute("DELETE FROM verification_tokens WHERE email = %s", (data.email,))
            cur.execute("DELETE FROM temp_user_data WHERE email = %s", (data.email,))
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification code expired or not found. Please request a new code."
            )

        # Extract values from dictionary result with safe access
        stored_code = verification_record['verification_code']
        is_verified = verification_record['is_verified']
        token_created_at = verification_record['created_at']
        token_id = verification_record['token_id']
        first_name = verification_record['first_name']
        last_name = verification_record['last_name']
        role = verification_record['role']
        hospital_name = verification_record['hospital_name']
        password_hash = verification_record['password_hash']
        temp_id = verification_record['temp_id']
        
        # Validate all required fields are present
        if not all([stored_code, token_id, first_name, last_name, role, hospital_name, password_hash, temp_id]):
            logger.error(f"Missing required fields in verification record for {data.email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid verification data. Please request a new code."
            )
        
        logger.info(f"Verification attempt for {data.email}: token_id={token_id}, temp_id={temp_id}, is_verified={is_verified}")

        if is_verified:
            logger.error(f"CRITICAL: Token already verified - token_id={token_id}, email={data.email}")
            # This should never happen with our new logic, so let's investigate
            cur.execute("SELECT COUNT(*) as count FROM users WHERE email = %s", (data.email,))
            user_result = cur.fetchone()
            user_count = user_result.get('count', 0) if user_result else 0
            logger.error(f"Users table check: {user_count} users found for {data.email}")
            
            # Clean up the problematic token
            cur.execute("DELETE FROM verification_tokens WHERE email = %s", (data.email,))
            cur.execute("DELETE FROM temp_user_data WHERE email = %s", (data.email,))
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This verification code has already been used. Please request a new code."
            )

        if data.verification_code != stored_code:
            logger.warning(f"Invalid verification code attempt for {data.email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code"
            )

        # Ensure hospital exists and get hospital_id
        cur.execute("""
            INSERT INTO hospitals (hospital_name)
            VALUES (%s)
            ON CONFLICT (hospital_name) DO NOTHING
            RETURNING hospital_id
        """, (hospital_name,))
        hospital_result = cur.fetchone()
        
        if hospital_result:
            hospital_id = hospital_result.get('hospital_id')
        else:
            # Hospital already exists, get its ID
            cur.execute("""
                SELECT hospital_id FROM hospitals 
                WHERE hospital_name = %s
            """, (hospital_name,))
            hospital_result = cur.fetchone()
            
            if not hospital_result:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create or find hospital record"
                )
            hospital_id = hospital_result.get('hospital_id')

        # Create the user with proper transaction handling
        try:
            # Start a savepoint for user creation
            cur.execute("SAVEPOINT user_creation")
            
            # Final check before user creation (race condition protection)
            cur.execute("SELECT COUNT(*) as count FROM users WHERE email = %s", (data.email,))
            existing_result = cur.fetchone()
            existing_user_count = existing_result.get('count', 0) if existing_result else 0
            if existing_user_count > 0:
                logger.error(f"RACE CONDITION DETECTED: User {data.email} was created during verification process")
                cur.execute("ROLLBACK TO SAVEPOINT user_creation")
                # Clean up verification data
                cur.execute("DELETE FROM verification_tokens WHERE email = %s", (data.email,))
                cur.execute("DELETE FROM temp_user_data WHERE email = %s", (data.email,))
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email was registered by another process. Please log in instead."
                )
            
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
                hospital_id
            ))
            user_result = cur.fetchone()
            
            if not user_result:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user"
                )
            user_id = user_result.get('user_id')
            
            # Mark verification token as verified ONLY after successful user creation
            cur.execute("""
                UPDATE verification_tokens 
                SET is_verified = TRUE 
                WHERE email = %s AND token_id = %s
            """, (data.email, token_id))
            
            # Verify the update worked
            cur.execute("SELECT is_verified FROM verification_tokens WHERE token_id = %s", (token_id,))
            updated_status = cur.fetchone()
            if not updated_status or not updated_status.get('is_verified'):
                logger.error(f"Failed to mark token {token_id} as verified for {data.email}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update verification status"
                )
            
            # Clean up temp data
            cur.execute("""
                DELETE FROM temp_user_data 
                WHERE email = %s AND temp_id = %s
            """, (data.email, temp_id))
            
            # Release savepoint - all operations succeeded
            cur.execute("RELEASE SAVEPOINT user_creation")
            
        except psycopg2.IntegrityError as e:
            # Rollback to savepoint
            cur.execute("ROLLBACK TO SAVEPOINT user_creation")
            if "duplicate key value violates unique constraint" in str(e):
                logger.error(f"User creation failed - email already exists: {data.email}")
                # Clean up verification data for already registered email
                cur.execute("DELETE FROM verification_tokens WHERE email = %s", (data.email,))
                cur.execute("DELETE FROM temp_user_data WHERE email = %s", (data.email,))
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered. Please log in instead."
                )
            else:
                logger.error(f"Database integrity error during user creation: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="User creation failed due to database error"
                )
        except Exception as e:
            # Rollback to savepoint for any other error
            cur.execute("ROLLBACK TO SAVEPOINT user_creation")
            logger.error(f"Unexpected error during user creation: {str(e)}")
            raise

        conn.commit()
        
        logger.info(f"User successfully created and verified: {data.email} (ID: {user_id})")

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
