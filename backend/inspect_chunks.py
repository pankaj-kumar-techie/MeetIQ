import sqlite3
import os
import base64

DB_PATH = "/data/meetiq.db"

def check_db():
    if not os.path.exists(DB_PATH):
        print("DB file does NOT exist!")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, status FROM recordings ORDER BY started_at DESC LIMIT 1")
        rec = cursor.fetchone()
        if not rec:
            print("No recordings found")
            return
            
        print(f"ID: {rec[0]}, Status: {rec[2]}")
        
        cursor.execute("SELECT sequence, LENGTH(data_b64) FROM chunks WHERE recording_id = ? ORDER BY sequence", (rec[0],))
        chunks = cursor.fetchall()
        print(f"Total chunks: {len(chunks)}")
        for seq, length in chunks:
            print(f"  Seq {seq}: {length} bytes (base64)")
            
        if chunks:
            # Check if first chunk has headers
            cursor.execute("SELECT data_b64 FROM chunks WHERE recording_id = ? AND sequence = 0", (rec[0],))
            first = cursor.fetchone()
            if first:
                raw = base64.b64decode(first[0])
                print(f"First chunk raw size: {len(raw)} bytes")
                print(f"First 16 bytes: {raw[:16].hex()}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
