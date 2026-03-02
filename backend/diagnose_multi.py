import sqlite3
import os
import json

DB_PATH = "/data/meetiq.db"

def check_db():
    if not os.path.exists(DB_PATH):
        print("DB file does NOT exist!")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Latest 3 recordings
        cursor.execute("SELECT id, name, status, transcript, duration_ms, summary FROM recordings ORDER BY started_at DESC LIMIT 3")
        rows = cursor.fetchall()
        for i, row in enumerate(rows):
            print(f"\n--- Recording {i+1} ---")
            print(f"ID: {row[0]}")
            print(f"Status: {row[2]}")
            tx = row[3] or ""
            print(f"Transcript length: {len(tx)}")
            print(f"Transcript snippet: {tx[:100]}...")
            print(f"Summary: {row[5]}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
