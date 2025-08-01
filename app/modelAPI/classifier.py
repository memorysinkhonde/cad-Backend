from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
from tensorflow.keras.applications.inception_v3 import preprocess_input
from PIL import Image
import numpy as np
import io
import time
import logging
import cv2
import base64
import os
import gdown
from typing import Dict, Any
from datetime import datetime

# Import database connection
from app.Database.db_connection import get_db_connection

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Constants ===
MODEL_PATH = "./modelFiles/inception_finetuned.h5"
GOOGLE_DRIVE_FILE_ID = "1tWWt2sf6sE7E83edI27mlpn81ewRKflM"
ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png")
IMAGE_SIZE = (299, 299)
CLASS_NAMES = ["lesion", "nonlesion"]
NUM_CLASSES = len(CLASS_NAMES)

# === Thresholds ===
MIN_CONFIDENCE = 0.6
STRONG_CONFIDENCE = 0.75
OOD_ENTROPY_THRESHOLD = 0.75

# === Model Loading ===
def load_prediction_model():
    """Load the ML model with proper error handling"""
    try:
        # Download model if not exists
        if not os.path.exists(MODEL_PATH):
            os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
            logger.info(f"Downloading model from Google Drive to {MODEL_PATH}")
            gdown.download(f"https://drive.google.com/uc?id={GOOGLE_DRIVE_FILE_ID}", 
                          MODEL_PATH, quiet=False)
        
        # Load model
        model = load_model(MODEL_PATH)
        logger.info("✅ Model loaded successfully")
        return model
    except Exception as e:
        logger.error(f"❌ Failed to load model: {str(e)}", exc_info=True)
        raise RuntimeError(f"Model loading failed: {str(e)}")

# Load model at startup
model = load_prediction_model()

# === Database Operations ===
def get_patient_data(patient_id: int) -> Dict[str, Any]:
    """Retrieve patient data from database without strict status validation"""
    conn, cur = None, None
    try:
        conn, cur = get_db_connection()
        logger.info(f"Fetching data for patient_id: {patient_id}")
        
        cur.execute("""
            SELECT i.image_id, i.base64_image, p.status, p.patient_id
            FROM images i
            JOIN patients p ON i.patient_id = p.patient_id
            WHERE p.patient_id = %s
            ORDER BY i.uploaded_at DESC
            LIMIT 1
        """, (patient_id,))
        
        result = cur.fetchone()
        if not result:
            logger.error(f"No data found for patient_id: {patient_id}")
            raise HTTPException(status_code=404, detail="Patient record not found")
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve patient data")
    finally:
        if cur: cur.close()
        if conn: conn.close()

def update_patient_workflow(
    patient_id: int,
    prediction_result: int,
    prediction_label: str,
    confidence: float,
    circled_image: str
) -> None:
    """Update database with prediction results and complete workflow"""
    conn, cur = None, None
    try:
        conn, cur = get_db_connection()
        
        # Update patient record - complete the workflow regardless of previous status
        cur.execute("""
            UPDATE patients
            SET prediction_result = %s,
                prediction_label = %s,
                prediction_confidence = %s,
                predicted_at = NOW(),
                status = 'Completed'
            WHERE patient_id = %s
        """, (prediction_result, prediction_label, confidence, patient_id))

        conn.commit()
        logger.info(f"Successfully completed workflow for patient {patient_id} (original image preserved)")
        
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"Failed to update workflow: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to complete patient workflow")
    finally:
        if cur: cur.close()
        if conn: conn.close()

# === Image Processing ===
def prepare_image(file_bytes: bytes) -> np.ndarray:
    """Prepare image for model prediction"""
    try:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        
        if img.size[0] < 100 or img.size[1] < 100:
            raise ValueError("Image resolution too small (min 100x100 pixels)")
            
        img = img.resize(IMAGE_SIZE)
        img_array = image.img_to_array(img)
        img_array = np.expand_dims(img_array, axis=0)
        return preprocess_input(img_array)
        
    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}", exc_info=True)
        raise ValueError(f"Invalid image data: {str(e)}")

def compute_entropy(prob_vector: np.ndarray) -> float:
    """Calculate prediction entropy for OOD detection"""
    prob_vector = np.clip(prob_vector, 1e-10, 1.0)
    return -np.sum(prob_vector * np.log(prob_vector)) / np.log(len(prob_vector))

def process_black_regions(image: Image.Image) -> str:
    """Detect and circle dark regions in image"""
    try:
        image_np = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        
        # Detect dark areas
        _, thresh = cv2.threshold(gray, 40, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Draw circles around dark regions
        for contour in contours:
            if cv2.contourArea(contour) > 50:
                (x, y), radius = cv2.minEnclosingCircle(contour)
                cv2.circle(image_np, (int(x), int(y)), int(radius), (0, 0, 0), 3)
                
        # Convert back to base64
        buffered = io.BytesIO()
        Image.fromarray(image_np).save(buffered, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
        
    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}", exc_info=True)
        raise ValueError("Failed to process image regions")

# === Prediction Endpoint ===
@router.post("/predict/{patient_id}", tags=["MACHINE-LEARNING-MODELS"])
async def complete_patient_workflow(patient_id: int):
    """Endpoint to process image and complete patient workflow in one step"""
    start_time = time.time()
    logger.info(f"Starting complete workflow for patient {patient_id}")
    
    try:
        # 1. Get patient data (regardless of current status)
        db_record = get_patient_data(patient_id)
        image_data = db_record['base64_image']
        current_status = db_record['status']
        
        logger.info(f"Patient {patient_id} current status: {current_status}")
        
        # 2. Decode image
        try:
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            file_bytes = base64.b64decode(image_data)
            original_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        except Exception as e:
            logger.error(f"Image decoding failed: {str(e)}", exc_info=True)
            raise HTTPException(status_code=400, detail="Invalid image data format")

        # 3. Prepare image and predict
        img_array = prepare_image(file_bytes)
        preds = model.predict(img_array)
        
        if preds.shape[1] != NUM_CLASSES:
            logger.error(f"Invalid model output shape: {preds.shape}")
            raise HTTPException(status_code=500, detail="Model output format error")

        pred_probs = preds[0]
        entropy = compute_entropy(pred_probs)
        
        # 4. Validate prediction quality
        if entropy > OOD_ENTROPY_THRESHOLD:
            logger.warning(f"High entropy prediction: {entropy:.4f}")
            return JSONResponse(
                status_code=422,
                content={
                    "status": "rejected",
                    "message": "Prediction rejected (high entropy)",
                    "entropy_score": round(entropy, 4),
                    "threshold": OOD_ENTROPY_THRESHOLD,
                    "patient_id": patient_id
                }
            )

        pred_index = int(np.argmax(pred_probs))
        confidence = float(np.max(pred_probs))
        predicted_class = CLASS_NAMES[pred_index]
        
        if predicted_class not in CLASS_NAMES:
            logger.error(f"Invalid class prediction: {predicted_class}")
            raise HTTPException(status_code=500, detail="Invalid model prediction")

        # 5. Process results
        elapsed = round(time.time() - start_time, 3)
        prediction_result = 1 if predicted_class == "lesion" else 0
        
        if confidence < MIN_CONFIDENCE:
            logger.warning(f"Low confidence prediction: {confidence:.4f}")
            return JSONResponse(
                status_code=422,
                content={
                    "status": "rejected",
                    "message": "Low confidence prediction",
                    "confidence": round(confidence, 4),
                    "threshold": MIN_CONFIDENCE,
                    "time_sec": elapsed,
                    "patient_id": patient_id
                }
            )

        # 6. Process image and complete workflow
        circled_image = process_black_regions(original_img)
        update_patient_workflow(
            patient_id=patient_id,
            prediction_result=prediction_result,
            prediction_label=predicted_class,
            confidence=confidence,
            circled_image=circled_image
        )

        # 7. Return response
        response = {
            "status": "confident" if confidence >= STRONG_CONFIDENCE else "borderline",
            "predicted_class": predicted_class,
            "confidence_score": round(confidence, 4),
            "prediction_time_sec": elapsed,
            "patient_id": patient_id,
            "circled_image": circled_image,
            "workflow_status": "completed",
            "previous_status": current_status,
            "note": "High confidence prediction" if confidence >= STRONG_CONFIDENCE 
                   else "Consider manual verification"
        }
        
        logger.info(f"Successfully completed workflow for patient {patient_id}")
        return response

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Workflow completion failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Patient workflow processing failed")