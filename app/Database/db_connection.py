import psycopg2
import psycopg2.extras
import logging

logger = logging.getLogger(__name__)

def get_db_connection(): 
    try:
        conn = psycopg2.connect(
            dbname="neondb",
            user="neondb_owner",
            password="npg_ZwQX5EM3gTAe",
            host="ep-ancient-sun-adaahfv0-pooler.c-2.us-east-1.aws.neon.tech",
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        logger.info("✅ Database connection established")
        cur = conn.cursor()
        return conn, cur
    except Exception as e:
        logger.error(f"❌ Failed to connect to the database: {e}", exc_info=True)
        raise
