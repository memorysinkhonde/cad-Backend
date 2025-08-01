from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import joblib
import os

router = APIRouter()

# Set model paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "../../modelFiles")

MODEL_PATH = os.path.join(MODEL_DIR, "rf_metadata_balanced_model.pkl")
FEATURES_PATH = os.path.join(MODEL_DIR, "rf_feature_columns.pkl")

try:
    model = joblib.load(MODEL_PATH)
    feature_columns = joblib.load(FEATURES_PATH)
except Exception as e:
    raise RuntimeError(f"Model loading failed: {e}")

class ClinicalData(BaseModel):
    age: int
    sex: int
    bmi: float
    diabetes_mellitus: int
    evolution_diabetes: float
    dyslipidemia: int
    smoker: int
    high_blood_pressure: int
    kidney_failure: int
    heart_failure: int
    atrial_fibrillation: int
    left_ventricular_ejection_fraction: float
    clinical_indication_for_angiogrphy: int
    number_of_vessels_affected: int
    maximum_degree_of_the_coronary_artery_involvement: float

@router.post("/predict-cad", tags=["MACHINE-LEARNING-MODELS"])
def predict_lesion(data: ClinicalData):
    try:
        input_data = {
            'age_(years)': data.age,
            'sex': data.sex,
            'bmi': data.bmi,
            'diabetes_mellitus': data.diabetes_mellitus,
            'evolution_diabetes_(years)': data.evolution_diabetes,
            'dyslipidemia': data.dyslipidemia,
            'smoker': data.smoker,
            'high_blood_pressure': data.high_blood_pressure,
            'kidney_failure': data.kidney_failure,
            'heart_failure': data.heart_failure,
            'atrial_fibrillation': data.atrial_fibrillation,
            'left_ventricular_ejection_fraction': data.left_ventricular_ejection_fraction,
            'clinical_indication_for_angiogrphy': data.clinical_indication_for_angiogrphy,
            'number_of_vessels_affected': data.number_of_vessels_affected,
            'maximum_degree_of_the_coronary_artery_involvement': data.maximum_degree_of_the_coronary_artery_involvement
        }

        df = pd.DataFrame([input_data])[feature_columns]
        prediction = model.predict(df)[0]
        label = "lesion" if prediction == 1 else "nonlesion"

        return {"prediction": int(prediction), "label": label}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Prediction failed: {e}")
