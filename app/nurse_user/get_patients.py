from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional
from pydantic import BaseModel
from app.Database.db_connection import get_db_connection
import base64
import logging
from jose import jwt, JWTError

router = APIRouter()
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

# Response models for structured output
class VitalsResponse(BaseModel):
    bmi: Optional[float]
    height_cm: Optional[float]
    weight_kg: Optional[float]
    diabetes_mellitus: Optional[bool]
    dyslipidemia: Optional[bool]
    high_blood_pressure: Optional[bool]
    atrial_fibrillation: Optional[bool]
    left_ventricular_ejection_fraction: Optional[float]
    clinical_indicator_for_angiography: Optional[str]

class DemographicsResponse(BaseModel):
    age: Optional[int]
    sex: Optional[str]
    smoking_status: Optional[bool]
    heart_failure: Optional[bool]
    evolution_diabetes_years: Optional[int]
    kidney_failure: Optional[bool]

class PatientResponse(BaseModel):
    patient_id: int
    first_name: str
    last_name: str
    status: str
    created_at: str
    vitals: Optional[VitalsResponse]
    demographics: Optional[DemographicsResponse]
    # base64 encoded image string, or None if no image
    image_base64: Optional[str]

# Token model for authentication
class TokenRequest(BaseModel):
    token: str

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

@router.post("/patients/all", response_model=List[PatientResponse], tags=["patients"], summary="Get all patients with details and latest image")
async def get_all_patients(token_req: TokenRequest):
    user_id = decode_token_get_user(token_req.token)
    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Get hospital_id for the user to restrict patients to their hospital
        cur.execute("SELECT hospital_id FROM users WHERE user_id = %s", (user_id,))
        res = cur.fetchone()
        if not res or not res[0]:
            raise HTTPException(status_code=404, detail="User or hospital not found")
        hospital_id = res[0]

        # Query to get patients with vitals, demographics, and latest image
        cur.execute("""
            SELECT
                p.patient_id,
                p.first_name,
                p.last_name,
                p.status,
                p.created_at,
                v.bmi,
                v.height_cm,
                v.weight_kg,
                v.diabetes_mellitus,
                v.dyslipidemia,
                v.high_blood_pressure,
                v.atrial_fibrillation,
                v.left_ventricular_ejection_fraction,
                v.clinical_indicator_for_angiography,
                d.age,
                d.sex,
                d.smoking_status,
                d.heart_failure,
                d.evolution_diabetes_years,
                d.kidney_failure,
                i.image_path
            FROM patients p
            LEFT JOIN vitals v ON p.patient_id = v.patient_id
            LEFT JOIN demographics d ON p.patient_id = d.patient_id
            LEFT JOIN LATERAL (
                SELECT image_path FROM images
                WHERE patient_id = p.patient_id
                ORDER BY uploaded_at DESC
                LIMIT 1
            ) i ON TRUE
            WHERE p.hospital_id = %s
            ORDER BY p.created_at DESC
        """, (hospital_id,))

        rows = cur.fetchall()
        patients = []

        for row in rows:
            (
                patient_id, first_name, last_name, status, created_at,
                bmi, height_cm, weight_kg, diabetes_mellitus, dyslipidemia,
                high_blood_pressure, atrial_fibrillation, left_ventricular_ejection_fraction,
                clinical_indicator_for_angiography,
                age, sex, smoking_status, heart_failure, evolution_diabetes_years,
                kidney_failure,
                image_path_base64
            ) = row

            # Validate image base64 if exists, else None
            image_base64 = image_path_base64 if image_path_base64 else None

            patient = PatientResponse(
                patient_id=patient_id,
                first_name=first_name,
                last_name=last_name,
                status=status,
                created_at=created_at.isoformat() if created_at else None,
                vitals=VitalsResponse(
                    bmi=bmi,
                    height_cm=height_cm,
                    weight_kg=weight_kg,
                    diabetes_mellitus=diabetes_mellitus,
                    dyslipidemia=dyslipidemia,
                    high_blood_pressure=high_blood_pressure,
                    atrial_fibrillation=atrial_fibrillation,
                    left_ventricular_ejection_fraction=left_ventricular_ejection_fraction,
                    clinical_indicator_for_angiography=clinical_indicator_for_angiography
                ) if bmi is not None or height_cm is not None else None,
                demographics=DemographicsResponse(
                    age=age,
                    sex=sex,
                    smoking_status=smoking_status,
                    heart_failure=heart_failure,
                    evolution_diabetes_years=evolution_diabetes_years,
                    kidney_failure=kidney_failure
                ) if age is not None or sex is not None else None,
                image_base64=image_base64
            )
            patients.append(patient)

        return patients

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch patients: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch patients data")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
