import sqlite3
import os

DB_PATH = "d:/workspace/MeetIQ/backend/meetiq.db"

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
        print(f"Tables: {[t[0] for t in tables]}")
        
        table_names = [t[0] for t in tables]
        
        if "recordings" in table_names:
            cursor.execute("SELECT id, name, status, started_at FROM recordings ORDER BY started_at DESC LIMIT 5")
            rows = cursor.fetchall()
            print("--- Recent Recordings ---")
            for row in rows:
                print(row)
            
            if "chunks" in table_names:
                cursor.execute("SELECT recording_id, COUNT(*) FROM chunks GROUP BY recording_id")
                counts = cursor.fetchall()
                print("--- Chunks per Recording ---")
                for c in counts:
                    print(f"ID: {c[0]}, Chunks: {c[1]}")
            else:
                print("No chunks table found!")
                
            if "analysis" in table_names:
                cursor.execute("SELECT recording_id, key, value FROM analysis")
                analysis = cursor.fetchall()
                print("--- Analysis Results ---")
                for a in analysis:
                    val_str = str(a[2])
                    print(f"Rec ID: {a[0]}, Key: {a[1]}, Value: {val_str[:100]}...")
            else:
                print("No analysis table found!")

        else:
            print("No recordings table found!")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
