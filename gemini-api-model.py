# list_gemini_models.py
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def list_models():
    try:
        models = genai.list_models()  # returns list/dict depending on SDK version
        print("Models available to this API key:")
        for m in models:
            # support older/newer SDK shapes
            name = m.get("name") if isinstance(m, dict) else getattr(m, "name", str(m))
            print(" -", name)
    except Exception as e:
        print("Error listing models:", e)

if __name__ == "__main__":
    list_models()
