import asyncio
import aiosqlite
import os

DB_PATH = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////data/meetiq.db").replace("sqlite+aiosqlite:///", "")

async def check_db():
    print(f"Checking DB at: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("DB file does NOT exist!")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Check tables
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            tables = await cursor.fetchall()
            print(f"Tables: {[t[0] for t in tables]}")
            
        if "recordings" in [t[0] for t in tables]:
            async with db.execute("SELECT id, name, status, started_at FROM recordings ORDER BY started_at DESC LIMIT 5") as cursor:
                rows = await cursor.fetchall()
                print("--- Recent Recordings ---")
                for row in rows:
                    print(row)
            
            async with db.execute("SELECT recording_id, COUNT(*) FROM chunks GROUP BY recording_id") as cursor:
                counts = await cursor.fetchall()
                print("--- Chunks per Recording ---")
                for c in counts:
                    print(f"ID: {c[0]}, Chunks: {c[1]}")
        else:
            print("No recordings table found!")

if __name__ == "__main__":
    asyncio.run(check_db())
