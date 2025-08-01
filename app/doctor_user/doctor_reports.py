from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, constr
from jose import jwt, JWTError
from datetime import datetime
from app.Database.db_connection import get_db_connection
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
import logging
import base64

router = APIRouter()

# ================= CONFIG =================
APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

EMAIL_CONFIG = {
    "address": "thandiechongwe@gmail.com",
    "password": "rkrefuxopjmdmwgp",  # App Password
    "sender_name": "Healthcare Diagnostic System",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465
}

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= MODELS =================
class TokenOnly(BaseModel):
    token: str

class PatientEmailRequest(BaseModel):
    token: str
    patient_id: int
    email: EmailStr  # Doctor-supplied patient email

# ================= HELPER FUNCTIONS =================
def send_patient_email(to_email: str, subject: str, html_content: str, image_base64: str):
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((EMAIL_CONFIG["sender_name"], EMAIL_CONFIG["address"]))
        msg["To"] = to_email
        msg.set_content("This is an HTML email. Please view it in an HTML-compatible client.")
        msg.add_alternative(html_content, subtype="html")

        if image_base64:
            msg.add_attachment(
                base64.b64decode(image_base64),
                maintype='image',
                subtype='jpeg',
                filename='diagnostic_image.jpg'
            )

        with smtplib.SMTP_SSL(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as smtp:
            smtp.login(EMAIL_CONFIG["address"], EMAIL_CONFIG["password"])
            smtp.send_message(msg)

        logger.info(f"Patient report email sent to {to_email}")
    except Exception as e:
        logger.error(f"Email sending failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send email.")

# ================= ROUTES =================
@router.post(
    "/doctor/assigned-patients-get-all",
    status_code=200,
    tags=["Doctor Dashboard"],
    summary="Get assigned patients",
    description="Returns all patient data assigned to the authenticated doctor."
)
async def get_assigned_patients(data: TokenOnly):
    token = data.token
    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not user_id or role != "doctor":
            raise HTTPException(status_code=403, detail="Access denied: Only doctors allowed.")
    except JWTError as e:
        logger.error(f"JWT error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()
        cur.execute("""
            SELECT p.*, u.first_name AS nurse_first_name, u.last_name AS nurse_last_name,
                   json_agg(json_build_object('base64_image', i.base64_image)) AS images
            FROM patients p
            LEFT JOIN users u ON p.created_by = u.user_id
            LEFT JOIN images i ON p.patient_id = i.patient_id
            WHERE assigned_doctor_id = %s
            GROUP BY p.patient_id, u.first_name, u.last_name
            ORDER BY p.created_at DESC
        """, (user_id,))
        patients = cur.fetchall()

        return {"doctor_id": user_id, "assigned_patients": patients}

    except Exception as e:
        logger.error(f"DB error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch assigned patients")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@router.post(
    "/doctor/send-patient-email",
    status_code=200,
    tags=["Doctor Dashboard"],
    summary="Send patient report to patient email",
    description="Sends a patient's full diagnostic record to a doctor-specified patient email."
)
async def send_patient_email_report(req: PatientEmailRequest):
    try:
        payload = jwt.decode(req.token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not user_id or role != "doctor":
            raise HTTPException(status_code=403, detail="Access denied: Only doctors allowed.")
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Verify patient ownership
        cur.execute("SELECT * FROM patients WHERE patient_id = %s AND assigned_doctor_id = %s", (req.patient_id, user_id))
        patient = cur.fetchone()

        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found or not assigned to this doctor")

        # Fetch doctor details
        cur.execute("SELECT first_name, last_name FROM users WHERE user_id = %s", (user_id,))
        doctor = cur.fetchone()

        # Fetch latest image
        cur.execute("SELECT base64_image FROM images WHERE patient_id = %s ORDER BY uploaded_at DESC LIMIT 1", (req.patient_id,))
        image = cur.fetchone()
        image_base64 = image["base64_image"] if image else ""

        # Format clinical indication description
        clinical_indication_map = {
            0: "No specific indication",
            1: "Stable angina",
            2: "Unstable angina",
            3: "Myocardial infarction",
            4: "Heart failure",
            5: "Other"
        }
        clinical_indication = clinical_indication_map.get(patient['clinical_indication_for_angiogrphy'], "Unknown")

        email_content = f"""
        <html>
            <head>
                <style>
                    body {{
                        font-family: 'Segoe UI', Arial, sans-serif;
                        background-color: #f7f9fa;
                        color: #222;
                        max-width: 700px;
                        margin: 0 auto;
                        padding: 24px;
                    }}
                    .header {{
                        background: linear-gradient(90deg, #2c3e50 60%, #2980b9 100%);
                        color: #fff;
                        padding: 24px 0 16px 0;
                        text-align: center;
                        border-radius: 8px 8px 0 0;
                        box-shadow: 0 2px 8px rgba(44,62,80,0.08);
                    }}
                    .content {{
                        background: #fff;
                        border: 1px solid #e1e4e8;
                        padding: 24px;
                        border-radius: 0 0 8px 8px;
                        box-shadow: 0 2px 8px rgba(44,62,80,0.04);
                    }}
                    .section {{
                        margin-bottom: 24px;
                    }}
                    .section-title {{
                        color: #2980b9;
                        border-bottom: 1px solid #e1e4e8;
                        padding-bottom: 6px;
                        margin-bottom: 12px;
                        font-size: 1.1em;
                    }}
                    .row {{
                        display: flex;
                        margin-bottom: 10px;
                    }}
                    .label {{
                        font-weight: 500;
                        width: 260px;
                        color: #34495e;
                    }}
                    .footer {{
                        margin-top: 32px;
                        font-size: 0.95em;
                        color: #888;
                        text-align: center;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1 style="margin-bottom: 0.5em;">Healthcare Diagnostic System</h1>
                    <h2 style="margin-top: 0; font-weight: 400;">Your Personalized Patient Report</h2>
                </div>
                <div class="content">
                    <p style="font-size:1.1em; margin-bottom: 2em;">Dear {patient['first_name']},<br>
                    We are pleased to share your latest diagnostic results. Please review the details below and reach out to your healthcare provider if you have any questions or concerns.</p>
                    <div class="section">
                        <h3 class="section-title">Patient Information</h3>
                        <div class="row">
                            <div class="label">Full Name:</div>
                            <div>{patient['first_name']} {patient['last_name']}</div>
                        </div>
                        <div class="row">
                            <div class="label">Age:</div>
                            <div>{patient['age']}</div>
                        </div>
                        <div class="row">
                            <div class="label">Sex:</div>
                            <div>{'Male' if patient['sex'] == 1 else 'Female'}</div>
                        </div>
                        <div class="row">
                            <div class="label">BMI:</div>
                            <div>{patient['bmi']}</div>
                        </div>
                    </div>
                    <div class="section">
                        <h3 class="section-title">Medical Conditions</h3>
                        <div class="row"><div class="label">Diabetes Mellitus:</div><div>{'Yes' if patient['diabetes_mellitus'] else 'No'}</div></div>
                        <div class="row"><div class="label">Diabetes Evolution (years):</div><div>{patient['evolution_diabetes']}</div></div>
                        <div class="row"><div class="label">Dyslipidemia:</div><div>{'Yes' if patient['dyslipidemia'] else 'No'}</div></div>
                        <div class="row"><div class="label">Smoker:</div><div>{'Yes' if patient['smoker'] else 'No'}</div></div>
                        <div class="row"><div class="label">High Blood Pressure:</div><div>{'Yes' if patient['high_blood_pressure'] else 'No'}</div></div>
                        <div class="row"><div class="label">Kidney Failure:</div><div>{'Yes' if patient['kidney_failure'] else 'No'}</div></div>
                        <div class="row"><div class="label">Heart Failure:</div><div>{'Yes' if patient['heart_failure'] else 'No'}</div></div>
                        <div class="row"><div class="label">Atrial Fibrillation:</div><div>{'Yes' if patient['atrial_fibrillation'] else 'No'}</div></div>
                    </div>
                    <div class="section">
                        <h3 class="section-title">Cardiac Assessment</h3>
                        <div class="row"><div class="label">Left Ventricular Ejection Fraction:</div><div>{patient['left_ventricular_ejection_fraction']}%</div></div>
                        <div class="row"><div class="label">Clinical Indication for Angiography:</div><div>{clinical_indication}</div></div>
                    </div>
                    <div class="section">
                        <h3 class="section-title">Diagnostic Results</h3>
                        <div class="row"><div class="label">Number of Vessels Affected:</div><div>{patient['number_of_vessels_affected']}</div></div>
                        <div class="row"><div class="label">Maximum Degree of Coronary Artery Involvement:</div><div>{patient['maximum_degree_of_the_coronary_artery_involvement']}%</div></div>
                        <div class="row"><div class="label">Prediction Result:</div><div>{patient['prediction_label'].capitalize() if patient['prediction_label'] else 'N/A'}</div></div>
                    </div>
                    <div class="section">
                        <h3 class="section-title">Attending Physician</h3>
                        <div class="row"><div class="label">Doctor:</div><div>Dr. {doctor['first_name']} {doctor['last_name']}</div></div>
                    </div>
                    <div class="footer">
                        <p>This report was generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.</p>
                        <p>If you have any questions, please contact your healthcare provider or reply to this email for assistance.</p>
                        <p style="margin-top:1em;">Wishing you good health,<br><b>Healthcare Diagnostic System Team</b></p>
                    </div>
                </div>
            </body>
        </html>
        """

        send_patient_email(
            to_email=req.email,
            subject=f"Diagnostic Report for {patient['first_name']} {patient['last_name']} - Healthcare System",
            html_content=email_content,
            image_base64=image_base64
        )

        # Update patient status to "Completed"
        cur.execute("""
            UPDATE patients 
            SET status = 'Completed'
            WHERE patient_id = %s
        """, (req.patient_id,))
        conn.commit()

        return {"message": f"Patient report sent to {req.email} successfully."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending patient report: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Server error while sending report.")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()