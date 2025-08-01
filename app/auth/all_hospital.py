from fastapi import APIRouter, HTTPException
from bs4 import BeautifulSoup
import os

router = APIRouter()

# Match path strategy used in your ML router
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "../../modelFiles/facilities.html")

@router.get("/hospitals/names", tags=["Hospitals"])
def get_all_hospital_names():
    try:
        # Debug: print the HTML_PATH being used
        print(f"[DEBUG] facilities.html path: {HTML_PATH}")
        if not os.path.exists(HTML_PATH):
            print(f"[ERROR] File not found: {HTML_PATH}")
            raise HTTPException(status_code=404, detail="facilities.html not found")

        with open(HTML_PATH, "r", encoding="utf-8") as file:
            html_content = file.read()
            print(f"[DEBUG] Read {len(html_content)} characters from facilities.html")
            soup = BeautifulSoup(html_content, "html.parser")

        table = soup.find("table")
        if not table:
            print("[ERROR] No <table> found in facilities.html")
            raise HTTPException(status_code=500, detail="No table found in the HTML file")

        rows = table.find_all("tr")
        print(f"[DEBUG] Found {len(rows)} rows in table")
        if len(rows) <= 1:
            print("[ERROR] Table has no data rows (only header or empty)")
        hospital_names = []

        for i, row in enumerate(rows[1:]):  # Skip header row
            cols = row.find_all("td")
            print(f"[DEBUG] Row {i+1}: found {len(cols)} columns")
            if len(cols) >= 2:
                name = cols[1].get_text(strip=True)
                print(f"[DEBUG] Extracted hospital name: {name}")
                if name:
                    hospital_names.append(name)
            else:
                print(f"[WARNING] Row {i+1} does not have at least 2 columns")

        print(f"[DEBUG] Extracted {len(hospital_names)} hospital names")
        return {"hospital_names": hospital_names}

    except Exception as e:
        print(f"[EXCEPTION] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to extract hospital names: {str(e)}")
