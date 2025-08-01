from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from jose import jwt, JWTError
from app.Database.db_connection import get_db_connection
import logging
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

class TokenRequest(BaseModel):
    token: str

class PatientDetailResponse(BaseModel):
    # Basic Patient Info
    patient_id: int
    first_name: str
    last_name: str
    age: int
    sex: str  # "Male" or "Female"
    status: str
    created_at: str
    
    # Medical Vitals
    bmi: float
    diabetes_mellitus: bool
    evolution_diabetes: float
    dyslipidemia: bool
    smoker: bool
    high_blood_pressure: bool
    kidney_failure: bool
    heart_failure: bool
    atrial_fibrillation: bool
    left_ventricular_ejection_fraction: float
    
    # Clinical Data
    clinical_indication_for_angiogrphy: int
    number_of_vessels_affected: int
    maximum_degree_of_the_coronary_artery_involvement: float
    
    # Prediction Results
    prediction_result: Optional[int]
    prediction_label: Optional[str]
    prediction_confidence: Optional[float]
    predicted_at: Optional[str]
    
    # Assignment Info
    assigned_doctor: Optional[str]
    assigned_doctor_id: Optional[int]
    created_by_nurse: Optional[str]
    
    # Hospital Info
    hospital_name: str
    
    # Image Data
    has_image: bool
    image_data: Optional[str]  # Base64 image data
    image_prediction: Optional[str]  # Image prediction result
    image_uploaded_at: Optional[str]  # When image was uploaded

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

@router.post("/all-patients", response_model=List[PatientDetailResponse], tags=["patients"], summary="Get all patients with complete details (Nurse only)")
async def get_all_patients(token_req: TokenRequest):
    user_id = decode_token_get_nurse(token_req.token)
    conn, cur = None, None
    
    try:
        conn, cur = get_db_connection()
        
        # Get hospital_id for the nurse user
        cur.execute("SELECT hospital_id FROM users WHERE user_id = %s AND role = 'nurse'", (user_id,))
        res = cur.fetchone()
        if not res or not res["hospital_id"]:
            raise HTTPException(status_code=404, detail="Nurse user or hospital not found")
        hospital_id = res["hospital_id"]
        
        # Get all patients with complete details from the nurse's hospital
        cur.execute("""
            SELECT 
                -- Basic Patient Info
                p.patient_id,
                p.first_name,
                p.last_name,
                p.age,
                p.sex,
                p.status,
                p.created_at,
                
                -- Medical Vitals
                p.bmi,
                p.diabetes_mellitus,
                p.evolution_diabetes,
                p.dyslipidemia,
                p.smoker,
                p.high_blood_pressure,
                p.kidney_failure,
                p.heart_failure,
                p.atrial_fibrillation,
                p.left_ventricular_ejection_fraction,
                
                -- Clinical Data
                p.clinical_indication_for_angiogrphy,
                p.number_of_vessels_affected,
                p.maximum_degree_of_the_coronary_artery_involvement,
                
                -- Prediction Results
                p.prediction_result,
                p.prediction_label,
                p.prediction_confidence,
                p.predicted_at,
                
                -- Assignment Info
                p.assigned_doctor_id,
                CONCAT(doc.first_name, ' ', doc.last_name) as assigned_doctor_name,
                CONCAT(nurse.first_name, ' ', nurse.last_name) as created_by_nurse_name,
                
                -- Hospital Info
                h.hospital_name,
                
                -- Image Data
                img.base64_image as image_base64,
                img.prediction_result as image_prediction,
                img.uploaded_at as image_uploaded_at
                
            FROM patients p
            LEFT JOIN users doc ON p.assigned_doctor_id = doc.user_id AND doc.role = 'doctor'
            LEFT JOIN users nurse ON p.created_by = nurse.user_id AND nurse.role = 'nurse'
            LEFT JOIN hospitals h ON p.hospital_id = h.hospital_id
            LEFT JOIN images img ON p.patient_id = img.patient_id
            WHERE p.hospital_id = %s
            ORDER BY p.created_at DESC
        """, (hospital_id,))
        
        patients_data = cur.fetchall()
        
        all_patients = []
        for patient in patients_data:
            # Convert sex from integer to string
            sex_str = "Male" if patient["sex"] == 1 else "Female"
            
            # Format dates
            created_at_str = patient["created_at"].strftime("%Y-%m-%d %H:%M:%S") if patient["created_at"] else "Unknown"
            predicted_at_str = patient["predicted_at"].strftime("%Y-%m-%d %H:%M:%S") if patient["predicted_at"] else None
            
            # Build patient response with all details
            patient_response = PatientDetailResponse(
                # Basic Patient Info
                patient_id=patient["patient_id"],
                first_name=patient["first_name"],
                last_name=patient["last_name"],
                age=patient["age"],
                sex=sex_str,
                status=patient["status"],
                created_at=created_at_str,
                
                # Medical Vitals
                bmi=float(patient["bmi"]),
                diabetes_mellitus=patient["diabetes_mellitus"],
                evolution_diabetes=float(patient["evolution_diabetes"]),
                dyslipidemia=patient["dyslipidemia"],
                smoker=patient["smoker"],
                high_blood_pressure=patient["high_blood_pressure"],
                kidney_failure=patient["kidney_failure"],
                heart_failure=patient["heart_failure"],
                atrial_fibrillation=patient["atrial_fibrillation"],
                left_ventricular_ejection_fraction=float(patient["left_ventricular_ejection_fraction"]),
                
                # Clinical Data
                clinical_indication_for_angiogrphy=patient["clinical_indication_for_angiogrphy"],
                number_of_vessels_affected=patient["number_of_vessels_affected"],
                maximum_degree_of_the_coronary_artery_involvement=float(patient["maximum_degree_of_the_coronary_artery_involvement"]),
                
                # Prediction Results
                prediction_result=patient["prediction_result"],
                prediction_label=patient["prediction_label"],
                prediction_confidence=float(patient["prediction_confidence"]) if patient["prediction_confidence"] else None,
                predicted_at=predicted_at_str,
                
                # Assignment Info
                assigned_doctor=patient["assigned_doctor_name"] if patient["assigned_doctor_name"] else None,
                assigned_doctor_id=patient["assigned_doctor_id"],
                created_by_nurse=patient["created_by_nurse_name"] if patient["created_by_nurse_name"] else None,
                
                # Hospital Info
                hospital_name=patient["hospital_name"],
                
                # Image Data
                has_image=bool(patient.get("image_base64")),
                image_data=f"data:image/jpeg;base64,{patient['image_base64']}" if patient.get("image_base64") else None,
                image_prediction=patient.get("image_prediction"),
                image_uploaded_at=patient["image_uploaded_at"].strftime("%Y-%m-%d %H:%M:%S") if patient.get("image_uploaded_at") else None
            )
            
            all_patients.append(patient_response)
        
        return all_patients
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching all patients: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch all patients")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@router.post("/patient-details/{patient_id}", response_model=PatientDetailResponse, tags=["patients"], summary="Get specific patient details by ID (Nurse only)")
async def get_patient_by_id(patient_id: int, token_req: TokenRequest):
    user_id = decode_token_get_nurse(token_req.token)
    conn, cur = None, None
    
    try:
        conn, cur = get_db_connection()
        
        # Get hospital_id for the nurse user
        cur.execute("SELECT hospital_id FROM users WHERE user_id = %s AND role = 'nurse'", (user_id,))
        res = cur.fetchone()
        if not res or not res["hospital_id"]:
            raise HTTPException(status_code=404, detail="Nurse user or hospital not found")
        hospital_id = res["hospital_id"]
        
        # Get specific patient details from the nurse's hospital
        cur.execute("""
            SELECT 
                -- Basic Patient Info
                p.patient_id,
                p.first_name,
                p.last_name,
                p.age,
                p.sex,
                p.status,
                p.created_at,
                
                -- Medical Vitals
                p.bmi,
                p.diabetes_mellitus,
                p.evolution_diabetes,
                p.dyslipidemia,
                p.smoker,
                p.high_blood_pressure,
                p.kidney_failure,
                p.heart_failure,
                p.atrial_fibrillation,
                p.left_ventricular_ejection_fraction,
                
                -- Clinical Data
                p.clinical_indication_for_angiogrphy,
                p.number_of_vessels_affected,
                p.maximum_degree_of_the_coronary_artery_involvement,
                
                -- Prediction Results
                p.prediction_result,
                p.prediction_label,
                p.prediction_confidence,
                p.predicted_at,
                
                -- Assignment Info
                p.assigned_doctor_id,
                CONCAT(doc.first_name, ' ', doc.last_name) as assigned_doctor_name,
                CONCAT(nurse.first_name, ' ', nurse.last_name) as created_by_nurse_name,
                
                -- Hospital Info
                h.hospital_name,
                
                -- Image Data
                img.base64_image as image_base64,
                img.prediction_result as image_prediction,
                img.uploaded_at as image_uploaded_at
                
            FROM patients p
            LEFT JOIN users doc ON p.assigned_doctor_id = doc.user_id AND doc.role = 'doctor'
            LEFT JOIN users nurse ON p.created_by = nurse.user_id AND nurse.role = 'nurse'
            LEFT JOIN hospitals h ON p.hospital_id = h.hospital_id
            LEFT JOIN images img ON p.patient_id = img.patient_id
            WHERE p.hospital_id = %s AND p.patient_id = %s
        """, (hospital_id, patient_id))
        
        patient = cur.fetchone()
        
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found in your hospital")
        
        # Convert sex from integer to string
        sex_str = "Male" if patient["sex"] == 1 else "Female"
        
        # Format dates
        created_at_str = patient["created_at"].strftime("%Y-%m-%d %H:%M:%S") if patient["created_at"] else "Unknown"
        predicted_at_str = patient["predicted_at"].strftime("%Y-%m-%d %H:%M:%S") if patient["predicted_at"] else None
        
        # Build patient response with all details
        patient_response = PatientDetailResponse(
            # Basic Patient Info
            patient_id=patient["patient_id"],
            first_name=patient["first_name"],
            last_name=patient["last_name"],
            age=patient["age"],
            sex=sex_str,
            status=patient["status"],
            created_at=created_at_str,
            
            # Medical Vitals
            bmi=float(patient["bmi"]),
            diabetes_mellitus=patient["diabetes_mellitus"],
            evolution_diabetes=float(patient["evolution_diabetes"]),
            dyslipidemia=patient["dyslipidemia"],
            smoker=patient["smoker"],
            high_blood_pressure=patient["high_blood_pressure"],
            kidney_failure=patient["kidney_failure"],
            heart_failure=patient["heart_failure"],
            atrial_fibrillation=patient["atrial_fibrillation"],
            left_ventricular_ejection_fraction=float(patient["left_ventricular_ejection_fraction"]),
            
            # Clinical Data
            clinical_indication_for_angiogrphy=patient["clinical_indication_for_angiogrphy"],
            number_of_vessels_affected=patient["number_of_vessels_affected"],
            maximum_degree_of_the_coronary_artery_involvement=float(patient["maximum_degree_of_the_coronary_artery_involvement"]),
            
            # Prediction Results
            prediction_result=patient["prediction_result"],
            prediction_label=patient["prediction_label"],
            prediction_confidence=float(patient["prediction_confidence"]) if patient["prediction_confidence"] else None,
            predicted_at=predicted_at_str,
            
            # Assignment Info
            assigned_doctor=patient["assigned_doctor_name"] if patient["assigned_doctor_name"] else None,
            assigned_doctor_id=patient["assigned_doctor_id"],
            created_by_nurse=patient["created_by_nurse_name"] if patient["created_by_nurse_name"] else None,
            
            # Hospital Info
            hospital_name=patient["hospital_name"],
            
            # Image Data
            has_image=bool(patient.get("image_base64")),
            image_data=f"data:image/jpeg;base64,{patient['image_base64']}" if patient.get("image_base64") else None,
            image_prediction=patient.get("image_prediction"),
            image_uploaded_at=patient["image_uploaded_at"].strftime("%Y-%m-%d %H:%M:%S") if patient.get("image_uploaded_at") else None
        )
        
        return patient_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch patient details")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
