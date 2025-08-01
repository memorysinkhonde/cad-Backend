from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from jose import jwt, JWTError
from datetime import datetime, timedelta
from app.Database.db_connection import get_db_connection
import logging

router = APIRouter()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_CONFIG = {
    "secret_key": "memodzashe",
    "algorithm": "HS256"
}

class TokenRequest(BaseModel):
    token: str

@router.post(
    "/doctor/dashboard",
    status_code=status.HTTP_200_OK,
    tags=["doctor_user"],
    summary="Enhanced doctor dashboard summary",
    description="Returns extended patient and workload summary for the authenticated doctor"
)
async def enhanced_doctor_dashboard(token_req: TokenRequest):
    token = token_req.token

    # Decode JWT token
    try:
        payload = jwt.decode(token, APP_CONFIG["secret_key"], algorithms=[APP_CONFIG["algorithm"]])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not user_id or role != "doctor":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied or invalid token")
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    conn, cur = None, None
    try:
        conn, cur = get_db_connection()

        # Get doctor's name
        cur.execute("SELECT first_name, last_name FROM users WHERE user_id = %s", (user_id,))
        doctor_row = cur.fetchone()
        doctor_name = None
        if doctor_row:
            doctor_name = f"{doctor_row['first_name']} {doctor_row['last_name']}"

        # 6 most recent patients assigned
        cur.execute("""
            SELECT patient_id, first_name, last_name, age, sex, status,
                   prediction_label, prediction_confidence, created_at
            FROM patients
            WHERE assigned_doctor_id = %s
            ORDER BY created_at DESC
            LIMIT 6
        """, (user_id,))
        recent_patients_rows = cur.fetchall()
        # If rows are tuples, map to dict using column names
        if recent_patients_rows and isinstance(recent_patients_rows[0], tuple):
            patient_cols = [desc[0] for desc in cur.description]
            recent_patients = [dict(zip(patient_cols, row)) for row in recent_patients_rows]
        else:
            recent_patients = recent_patients_rows

        # Total patients assigned
        cur.execute("SELECT COUNT(*) as count FROM patients WHERE assigned_doctor_id = %s", (user_id,))
        total_patients = cur.fetchone()["count"]

        # Breakdown by status
        cur.execute("""
            SELECT status, COUNT(*) as count
            FROM patients
            WHERE assigned_doctor_id = %s
            GROUP BY status
        """, (user_id,))
        status_breakdown = {row["status"]: row["count"] for row in cur.fetchall()}

        # Prediction summary: lesion, nonlesion, not predicted
        cur.execute("""
            SELECT
                SUM(CASE WHEN prediction_label = 'lesion' THEN 1 ELSE 0 END) AS lesion_count,
                SUM(CASE WHEN prediction_label = 'nonlesion' THEN 1 ELSE 0 END) AS nonlesion_count,
                SUM(CASE WHEN prediction_label IS NULL THEN 1 ELSE 0 END) AS not_predicted_count,
                SUM(CASE WHEN prediction_label = 'lesion' AND prediction_confidence > 0.8 THEN 1 ELSE 0 END) AS high_risk_count
            FROM patients
            WHERE assigned_doctor_id = %s
        """, (user_id,))
        prediction_summary_row = cur.fetchone()
        prediction_summary = {
            "lesion": prediction_summary_row["lesion_count"] or 0,
            "nonlesion": prediction_summary_row["nonlesion_count"] or 0,
            "not_predicted": prediction_summary_row["not_predicted_count"] or 0,
            "high_risk": prediction_summary_row["high_risk_count"] or 0
        }

        # Alerts for high-risk patients (top 3 by confidence)
        cur.execute("""
            SELECT patient_id, first_name, last_name, prediction_confidence, created_at
            FROM patients
            WHERE assigned_doctor_id = %s
              AND prediction_label = 'lesion'
              AND prediction_confidence > 0.8
            ORDER BY prediction_confidence DESC
            LIMIT 3
        """, (user_id,))
        alert_rows = cur.fetchall()
        if alert_rows and len(alert_rows) > 0:
            if isinstance(alert_rows[0], tuple):
                alert_cols = [desc[0] for desc in cur.description]
                alerts = [dict(zip(alert_cols, row)) for row in alert_rows]
            else:
                alerts = alert_rows
        else:
            alerts = []

        # Demographics: age groups and sex counts
        cur.execute("""
            SELECT
                SUM(CASE WHEN age < 30 THEN 1 ELSE 0 END) AS under_30,
                SUM(CASE WHEN age BETWEEN 30 AND 50 THEN 1 ELSE 0 END) AS between_30_50,
                SUM(CASE WHEN age > 50 THEN 1 ELSE 0 END) AS over_50
            FROM patients
            WHERE assigned_doctor_id = %s
        """, (user_id,))
        age_groups_row = cur.fetchone()
        age_groups = {
            "<30": age_groups_row["under_30"] or 0,
            "30-50": age_groups_row["between_30_50"] or 0,
            "50+": age_groups_row["over_50"] or 0
        }

        cur.execute("""
            SELECT sex, COUNT(*) as count
            FROM patients
            WHERE assigned_doctor_id = %s
            GROUP BY sex
        """, (user_id,))
        sex_counts = {row["sex"]: row["count"] for row in cur.fetchall()}
        # Map sex integers to strings for clarity
        sex_mapping = {0: "female", 1: "male"}
        demographics_sex = {sex_mapping.get(k, "unknown"): v for k, v in sex_counts.items()}

        # Workload stats: average days to prediction & patients added last 7 days
        cur.execute("""
            SELECT AVG(EXTRACT(EPOCH FROM (predicted_at - created_at))/86400) AS avg_days_to_prediction
            FROM patients
            WHERE assigned_doctor_id = %s
              AND predicted_at IS NOT NULL
        """, (user_id,))
        avg_days_row = cur.fetchone()
        avg_days_to_prediction = round(avg_days_row["avg_days_to_prediction"], 2) if avg_days_row["avg_days_to_prediction"] else None

        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        cur.execute("""
            SELECT COUNT(*)
            FROM patients
            WHERE assigned_doctor_id = %s
              AND created_at >= %s
        """, (user_id, seven_days_ago))
        patients_added_last_week = cur.fetchone()["count"]

        return {
            "doctor_id": user_id,
            "doctor_name": doctor_name,
            "total_assigned_patients": total_patients,
            "status_breakdown": status_breakdown,
            "prediction_summary": prediction_summary,
            "alerts": alerts,
            "demographics": {
                "age_groups": age_groups,
                "sex": demographics_sex
            },
            "workload_stats": {
                "avg_days_to_prediction": avg_days_to_prediction,
                "patients_added_last_week": patients_added_last_week
            },
            "recent_patients": recent_patients
        }

    except Exception as e:
        logger.error(f"Error fetching doctor dashboard data: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch dashboard data")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
