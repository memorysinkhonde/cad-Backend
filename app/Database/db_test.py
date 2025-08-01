# app/routes/db_test.py

from fastapi import APIRouter, HTTPException
from app.Database.db_connection import get_db_connection

router = APIRouter()

@router.get("/db-test", tags=["Database"])
def test_database_connection():
    """
    Test the PostgreSQL database connection.
    Returns a message if successful, raises error if failed.
    """
    try:
        conn, cur = get_db_connection()
        cur.execute("SELECT 1;")
        result = cur.fetchone()
        cur.close()
        conn.close()

        return {"status": "✅ Database connected successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")
