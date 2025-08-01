from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from typing import Optional
from jose import jwt, JWTError
from app.Database.db_connection import get_db_connection
import logging
import base64

router = APIRouter()
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

@router.post("/patients", status_code=status.HTTP_201_CREATED, tags=["patients"])
async def insert_patient_only(
    token: str = Form(...),
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    age: int = Form(...),
    sex: int = Form(...),
    bmi: float = Form(...),
    diabetes_mellitus: bool = Form(...),
    evolution_diabetes: float = Form(...),
    dyslipidemia: bool = Form(...),
    smoker: bool = Form(...),
    high_blood_pressure: bool = Form(...),
    kidney_failure: bool = Form(...),
    heart_failure: bool = Form(...),
    atrial_fibrillation: bool = Form(...),
    left_ventricular_ejection_fraction: float = Form(...),
    clinical_indication_for_angiogrphy: int = Form(...),
    number_of_vessels_affected: int = Form(...),
    maximum_degree_of_the_coronary_artery_involvement: float = Form(...),
    status: Optional[str] = Form("Pending Doctor Review"),
    assigned_doctor_id: Optional[int] = Form(None),
    image_file: Optional[UploadFile] = File(None)
):
    user_id = None
    conn, cur = None, None

    try:
        # Decode JWT token to get user_id
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user_id")

        conn, cur = get_db_connection()

        # Get hospital_id for user
        cur.execute("SELECT hospital_id FROM users WHERE user_id = %s", (user_id,))
        res = cur.fetchone()
        if not res or not res["hospital_id"]:
            raise HTTPException(status_code=404, detail="User or hospital not found")
        hospital_id = res["hospital_id"]

        # Validate assigned doctor if provided
        if assigned_doctor_id:
            cur.execute(
                "SELECT user_id FROM users WHERE user_id = %s AND role = 'doctor' AND hospital_id = %s",
                (assigned_doctor_id, hospital_id)
            )
            doctor_res = cur.fetchone()
            if not doctor_res:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid doctor assignment: Doctor not found or not in the same hospital"
                )

        # Prepare image base64 if provided
        image_base64 = None
        if image_file:
            contents = await image_file.read()
            image_base64 = base64.b64encode(contents).decode("utf-8")

        # Insert patient record
        cur.execute(
            """
            INSERT INTO patients (
                first_name, last_name, age, sex, bmi, diabetes_mellitus, evolution_diabetes,
                dyslipidemia, smoker, high_blood_pressure, kidney_failure, heart_failure,
                atrial_fibrillation, left_ventricular_ejection_fraction,
                clinical_indication_for_angiogrphy, number_of_vessels_affected,
                maximum_degree_of_the_coronary_artery_involvement, status,
                hospital_id, assigned_doctor_id, created_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING patient_id
            """,
            (
                first_name or "Unknown",
                last_name or "Unknown",
                age,
                sex,
                bmi,
                diabetes_mellitus,
                evolution_diabetes,
                dyslipidemia,
                smoker,
                high_blood_pressure,
                kidney_failure,
                heart_failure,
                atrial_fibrillation,
                left_ventricular_ejection_fraction,
                clinical_indication_for_angiogrphy,
                number_of_vessels_affected,
                maximum_degree_of_the_coronary_artery_involvement,
                status,
                hospital_id,
                assigned_doctor_id,
                user_id
            )
        )
        patient_id = cur.fetchone()["patient_id"]

        # Insert image if provided
        if image_base64:
            cur.execute(
                """
                INSERT INTO images (patient_id, image_path, base64_image)
                VALUES (%s, %s, %s)
                """,
                (patient_id, f"patient_{patient_id}_image", image_base64)
            )

        conn.commit()

        return {
            "message": "Patient data inserted successfully",
            "patient_id": patient_id,
            "has_image": image_base64 is not None,
            "assigned_doctor_id": assigned_doctor_id
        }

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Error inserting patient data: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to insert patient data")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
