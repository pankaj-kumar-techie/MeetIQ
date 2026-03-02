import os
import asyncio
from dotenv import load_dotenv

# Load real .env for keys
load_dotenv()

SAR_KEY = os.getenv("SARVAM_API_KEY")
SAR_MODEL = os.getenv("SARVAM_RECOGNITION_MODEL", "saaras:v3")

async def test_sarvam_call():
    from sarvamai import SarvamAI
    client = SarvamAI(api_subscription_key=SAR_KEY)
    
    # We don't need a real file if we just want to see the method's existence/structure
    # but we can try with a dummy if needed. 
    # Let's just inspect the client.
    print(f"Client: {client}")
    print(f"STT: {client.speech_to_text}")
    print(f"Transcribe method: {client.speech_to_text.transcribe}")

    # Let's try to see if it's a DICT or OBJECT
    # Usually SDKs like this are generated or use pydantic.
    # I'll just refine the transcription service to handle both.

if __name__ == "__main__":
    if not SAR_KEY:
        print("SARVAM_API_KEY missing from .env")
    else:
        asyncio.run(test_sarvam_call())
