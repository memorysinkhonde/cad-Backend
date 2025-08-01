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

class RecentPatientResponse(BaseModel):
    patient_id: int
    patient_name: str
    assigned_doctor: Optional[str]
    priority: str
    medical_data_summary: str
    status: str
    recorded: str

def decode_token_get_user(token: str):
    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user_id")
        if role != "nurse":
            raise HTTPException(status_code=403, detail="Access denied: Only nurses can access this endpoint")
        return user_id, role
    except JWTError as e:
        logger.error(f"Token decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def calculate_priority(patient_data):
    """Calculate priority based on medical conditions"""
    high_risk_conditions = [
        patient_data.get("heart_failure", False),
        patient_data.get("kidney_failure", False),
        patient_data.get("diabetes_mellitus", False) and patient_data.get("evolution_diabetes", 0) > 10,
        patient_data.get("atrial_fibrillation", False),
        patient_data.get("left_ventricular_ejection_fraction", 100) < 40
    ]
    
    risk_count = sum(high_risk_conditions)
    
    if risk_count >= 3:
        return "High"
    elif risk_count >= 1:
        return "Medium"
    else:
        return "Low"

def create_medical_summary(patient_data):
    """Create a medical data summary from patient information"""
    conditions = []
    
    # Add key medical conditions
    if patient_data.get("diabetes_mellitus"):
        evolution = patient_data.get("evolution_diabetes", 0)
        conditions.append(f"Diabetes ({evolution}y)")
    
    if patient_data.get("high_blood_pressure"):
        conditions.append("Hypertension")
    
    if patient_data.get("heart_failure"):
        conditions.append("Heart Failure")
    
    if patient_data.get("kidney_failure"):
        conditions.append("Kidney Failure")
    
    if patient_data.get("atrial_fibrillation"):
        conditions.append("A-Fib")
    
    if patient_data.get("dyslipidemia"):
        conditions.append("Dyslipidemia")
    
    if patient_data.get("smoker"):
        conditions.append("Smoker")
    
    # Add BMI info
    bmi = patient_data.get("bmi")
    if bmi:
        conditions.append(f"BMI: {bmi}")
    
    # Add ejection fraction
    ef = patient_data.get("left_ventricular_ejection_fraction")
    if ef:
        conditions.append(f"EF: {ef}%")
    
    # Add vessel involvement
    vessels = patient_data.get("number_of_vessels_affected", 0)
    if vessels > 0:
        conditions.append(f"{vessels} vessel(s)")
    
    return "; ".join(conditions) if conditions else "No significant conditions recorded"

@router.post("/recent-patients", response_model=List[RecentPatientResponse], tags=["patients"], summary="Get 10 most recent patients (Nurse only)")
async def get_recent_patients(token_req: TokenRequest):
    user_id, role = decode_token_get_user(token_req.token)
    conn, cur = None, None
    
    try:
        conn, cur = get_db_connection()
        
        # Get hospital_id for the nurse user
        cur.execute("SELECT hospital_id FROM users WHERE user_id = %s AND role = 'nurse'", (user_id,))
        res = cur.fetchone()
        if not res or not res["hospital_id"]:
            raise HTTPException(status_code=404, detail="Nurse user or hospital not found")
        hospital_id = res["hospital_id"]
        
        # Get recent patients with all required information
        cur.execute("""
            SELECT 
                p.patient_id,
                p.first_name,
                p.last_name,
                p.age,
                p.sex,
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
                p.clinical_indication_for_angiogrphy,
                p.number_of_vessels_affected,
                p.maximum_degree_of_the_coronary_artery_involvement,
                p.status,
                p.created_at,
                CONCAT(doc.first_name, ' ', doc.last_name) as doctor_name
            FROM patients p
            LEFT JOIN users doc ON p.assigned_doctor_id = doc.user_id AND doc.role = 'doctor'
            WHERE p.hospital_id = %s
            ORDER BY p.created_at DESC
            LIMIT 10
        """, (hospital_id,))
        
        patients_data = cur.fetchall()
        
        recent_patients = []
        for patient in patients_data:
            # Convert patient data to dict for processing
            patient_dict = dict(patient)
            
            # Calculate priority
            priority = calculate_priority(patient_dict)
            
            # Create medical summary
            medical_summary = create_medical_summary(patient_dict)
            
            # Format recorded date
            recorded_date = patient["created_at"].strftime("%Y-%m-%d %H:%M") if patient["created_at"] else "Unknown"
            
            # Build patient response
            patient_response = RecentPatientResponse(
                patient_id=patient["patient_id"],
                patient_name=f"{patient['first_name']} {patient['last_name']}",
                assigned_doctor=patient["doctor_name"] if patient["doctor_name"] else "Unassigned",
                priority=priority,
                medical_data_summary=medical_summary,
                status=patient["status"],
                recorded=recorded_date
            )
            
            recent_patients.append(patient_response)
        
        return recent_patients
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recent patients: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch recent patients")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
