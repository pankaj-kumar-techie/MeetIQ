import sqlite3
import os

# Updated to use the internal docker path
DB_PATH = "/data/meetiq.db"

def check_db():
    print(f"Checking DB at: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("DB file does NOT exist!")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        table_names = [t[0] for t in tables]
        print(f"Tables: {table_names}")
        
        if "recordings" in table_names:
            cursor.execute("SELECT id, name, status, transcript, duration_ms, summary FROM recordings ORDER BY started_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                print(f"--- Latest Recording ---")
                print(f"ID: {row[0]}")
                print(f"Name: {row[1]}")
                print(f"Status: {row[2]}")
                print(f"Transcript length: {len(row[3]) if row[3] else 0}")
                print(f"Duration: {row[4]} ms")
                print(f"Summary: {row[5]}")
                if row[3]:
                    print(f"Transcript Snippet: {row[3][:250]}...")
            
            cursor.execute("SELECT recording_id, COUNT(*) FROM chunks GROUP BY recording_id")
            counts = cursor.fetchall()
            print("--- Chunks per Recording ---")
            for c in counts:
                print(f"ID: {c[0]}, Chunks: {c[1]}")

        else:
            print("No recordings table found!")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
