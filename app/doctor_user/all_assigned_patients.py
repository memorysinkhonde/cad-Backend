from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel
from jose import jwt, JWTError
from typing import List, Optional
from datetime import datetime
from app.Database.db_connection import get_db_connection
import logging

router = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

# Response models
class ImageData(BaseModel):
    image_id: int
    image_path: str
    base64_image: str
    prediction_result: Optional[str]
    uploaded_at: Optional[datetime]

class PatientData(BaseModel):
    patient_id: int
    first_name: str
    last_name: str
    age: Optional[int]
    sex: Optional[str]
    bmi: Optional[float]
    diabetes_mellitus: Optional[bool]
    evolution_diabetes: Optional[str]
    dyslipidemia: Optional[bool]
    smoker: Optional[bool]
    high_blood_pressure: Optional[bool]
    kidney_failure: Optional[bool]
    heart_failure: Optional[bool]
    atrial_fibrillation: Optional[bool]
    left_ventricular_ejection_fraction: Optional[str]
    clinical_indication_for_angiogrphy: Optional[str]
    number_of_vessels_affected: Optional[int]
    maximum_degree_of_the_coronary_artery_involvement: Optional[str]
    status: Optional[str]
    prediction_result: Optional[str]
    prediction_label: Optional[str]
    prediction_confidence: Optional[float]
    predicted_at: Optional[datetime]
    hospital_id: Optional[int]
    assigned_doctor_id: Optional[int]
    created_by: Optional[int]
    created_at: Optional[datetime]
    nurse_first_name: Optional[str]
    nurse_last_name: Optional[str]
    images: List[ImageData] = []

class DoctorDashboardResponse(BaseModel):
    doctor_id: int
    doctor_name: Optional[str]
    assigned_patients: List[PatientData]

# Dependency to get current user from token query param
async def get_current_user(token: str = Query(...)):
    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")

        if not user_id or not role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid token payload"
            )
        return {"user_id": user_id, "role": role}

    except JWTError as e:
        logger.error(f"Token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

@router.get(
    "/doctor/dashboard-patients/list",
    response_model=DoctorDashboardResponse,
    status_code=status.HTTP_200_OK,
    tags=["doctor_user"],
    summary="Doctor dashboard: full patient and image data",
    description="Returns all patient data assigned to the doctor, including nurse and images for each patient."
)
async def enhanced_doctor_dashboard(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "doctor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied - doctor role required"
        )

    user_id = current_user["user_id"]
    conn, cur = None, None

    try:
        conn, cur = get_db_connection()

        # Get doctor name
        cur.execute("SELECT first_name, last_name FROM users WHERE user_id = %s", (user_id,))
        doctor_row = cur.fetchone()
        doctor_name = f"{doctor_row['first_name']} {doctor_row['last_name']}" if doctor_row else None

        # Get patients assigned to doctor
        cur.execute("""
            SELECT 
                p.*, u.first_name AS nurse_first_name, u.last_name AS nurse_last_name
            FROM patients p
            LEFT JOIN users u ON p.created_by = u.user_id
            WHERE p.assigned_doctor_id = %s
            ORDER BY p.created_at DESC
        """, (user_id,))
        patient_rows = cur.fetchall()

        if not patient_rows:
            return {
                "doctor_id": user_id,
                "doctor_name": doctor_name,
                "assigned_patients": []
            }

        patient_ids = [p["patient_id"] for p in patient_rows]
        logger.info(f"Patient IDs: {patient_ids}")

        # Fetch images for all patients
        cur.execute("""
            SELECT patient_id, image_id, image_path, base64_image, prediction_result, uploaded_at
            FROM images
            WHERE patient_id = ANY(%s)
        """, (patient_ids,))
        image_rows = cur.fetchall()

        # Map patient_id -> list of images
        image_map = {}
        for row in image_rows:
            image = {
                "image_id": row["image_id"],
                "image_path": row["image_path"],
                "base64_image": row["base64_image"],
                "prediction_result": row["prediction_result"],
                "uploaded_at": row["uploaded_at"]
            }
            pid = row["patient_id"]
            image_map.setdefault(pid, []).append(image)

        # Attach images to patients
        patients = []
        for patient in patient_rows:
            pid = patient["patient_id"]
            patient_dict = dict(patient)
            patient_dict["images"] = image_map.get(pid, [])
            patients.append(PatientData(**patient_dict))

        return DoctorDashboardResponse(
            doctor_id=user_id,
            doctor_name=doctor_name,
            assigned_patients=patients
        )

    except Exception as e:
        logger.error(f"Error fetching doctor dashboard data: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dashboard data"
        )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
