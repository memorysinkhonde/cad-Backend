from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from app.Database import db_test
from app.auth import  all_hospital, sign_in, sign_up, token_refresh_router
from app.doctor_user import all_assigned_patients, doctor_dashboard, doctor_reports, doctor_settings, get_me_doctor
import numpy as np
from app.nurse_user import all_patients_lits, dashboard, get_all_doctors,  get_me, get_patients, patient_insertion, recient_patients, settings_api
import io

from app.modelAPI import classifier, metadata_api

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/",tags=["Root"])
def read_root():
    return {"message": "Welcome to the Image Classification API"}



# === database connection test ===
app.include_router(db_test.router)

# === auth routes ===
app.include_router(sign_up.router)
app.include_router(sign_in.router)
app.include_router(token_refresh_router.router)
app.include_router(settings_api.router)
app.include_router(all_hospital.router, tags=["Hospitals"], prefix="/auth")
# nurse user routes
app.include_router(get_me.router)
app.include_router(dashboard.router)
app.include_router(patient_insertion.router)
app.include_router(get_patients.router)
app.include_router(get_all_doctors.router)
app.include_router(recient_patients.router)
app.include_router(all_patients_lits.router)


# === modelAPI ===
app.include_router(classifier.router)
app.include_router(metadata_api.router)



# === doctor api
app.include_router(get_me_doctor.router, tags=["doctor_user"], prefix="/doctor")
app.include_router(doctor_dashboard.router, tags=["doctor_user"], prefix="/doctor")
app.include_router(all_assigned_patients.router, tags=["doctor_user"], prefix="/doctor")
app.include_router(doctor_settings.router, tags=["doctor_user"])
app.include_router(doctor_reports.router, tags=["doctor_user"])