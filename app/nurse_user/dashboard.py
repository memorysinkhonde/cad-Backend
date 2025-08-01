from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from jose import jwt, JWTError
from app.Database.db_connection import get_db_connection
import logging
from datetime import date

router = APIRouter()
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

class TokenRequest(BaseModel):
    token: str

@router.post(
    "/dashboard-overview",
    status_code=status.HTTP_200_OK,
    tags=["nurse_user"],
    summary="Get dashboard overview data",
    description="Returns hospital stats and recent patients for the nurse dashboard"
)
async def get_dashboard_data(token_req: TokenRequest):
    token = token_req.token

    # Decode token and extract user info
    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user_id")
    except JWTError as e:
        logger.error(f"Token decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Get hospital_id for the user
        cur.execute("SELECT hospital_id FROM users WHERE user_id = %s", (user_id,))
        res = cur.fetchone()
        if not res or not res["hospital_id"]:
            raise HTTPException(status_code=404, detail="User or hospital not found")
        hospital_id = res["hospital_id"]

        today = date.today()

        # Hospital name
        cur.execute("SELECT hospital_name FROM hospitals WHERE hospital_id = %s", (hospital_id,))
        hospital_name = cur.fetchone()
        hospital_name = hospital_name["hospital_name"] if hospital_name else None

        # Patients today (based on patients.created_at)
        cur.execute("""
            SELECT COUNT(*) as count FROM patients
            WHERE hospital_id = %s AND DATE(created_at) = %s
        """, (hospital_id, today))
        patients_today = cur.fetchone()["count"]

        # Reviewed by doctor (demographics.completed_by IS NOT NULL means reviewed)
        cur.execute("""
            SELECT COUNT(*) as count FROM demographics d
            JOIN patients p ON d.patient_id = p.patient_id
            WHERE p.hospital_id = %s AND d.completed_by IS NOT NULL
        """, (hospital_id,))
        reviewed = cur.fetchone()["count"]

        # Pending review (patients with status 'Pending Doctor Review')
        cur.execute("""
            SELECT COUNT(*) as count FROM patients
            WHERE hospital_id = %s AND status = 'Pending Doctor Review'
        """, (hospital_id,))
        pending = cur.fetchone()["count"]

        # Total completed patients (since we don't have prediction classification)
        cur.execute("""
            SELECT COUNT(*) as count FROM patients
            WHERE hospital_id = %s AND status = 'Completed'
        """, (hospital_id,))
        with_lesion = cur.fetchone()["count"]

        # Patients ready for prediction
        cur.execute("""
            SELECT COUNT(*) as count FROM patients
            WHERE hospital_id = %s AND status = 'Ready for Prediction'
        """, (hospital_id,))
        without_lesion = cur.fetchone()["count"]

        # Recent patients (limit 6, ordered by patients.created_at desc)
        cur.execute("""
            SELECT p.patient_id,
                   p.first_name || ' ' || p.last_name AS name,
                   p.created_at,
                   CASE WHEN d.completed_by IS NOT NULL THEN TRUE ELSE FALSE END AS reviewed_by_doctor,
                   p.status AS prediction,
                   (SELECT image_id FROM images WHERE patient_id = p.patient_id ORDER BY uploaded_at DESC LIMIT 1) AS image_id
            FROM patients p
            LEFT JOIN demographics d ON p.patient_id = d.patient_id
            WHERE p.hospital_id = %s
            ORDER BY p.created_at DESC
            LIMIT 6
        """, (hospital_id,))
        recent_patients_rows = cur.fetchall()

        # Format recent patients
        recent_patients = []
        for row in recent_patients_rows:
            recent_patients.append({
                "patient_id": row["patient_id"],
                "name": row["name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "reviewed_by_doctor": row["reviewed_by_doctor"],
                "prediction": row["prediction"],
                "image_id": row["image_id"],
            })

        return {
            "hospital_name": hospital_name,
            "patients_today": patients_today,
            "reviewed": reviewed,
            "pending": pending,
            "completed": with_lesion,  # renamed for clarity
            "ready_for_prediction": without_lesion,  # renamed for clarity
            "recent_patients": recent_patients
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard data")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
