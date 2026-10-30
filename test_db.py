import os
import psycopg
from dotenv import load_dotenv

# Load settings from the .env file
load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    print("ERROR: DATABASE_URL was not found in .env")
else:
    try:
        with psycopg.connect(database_url, connect_timeout=10) as conn:
            result = conn.execute("SELECT version()").fetchone()
            print("SUCCESS: Connected to PostgreSQL!")
            print("Database connection is working.")
    except Exception as e:
        print("ERROR: Database connection failed.")
        print("Details:", e)