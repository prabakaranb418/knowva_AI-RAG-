import os
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERROR: GEMINI_API_KEY was not found in .env")
else:
    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents="Say hello in one short sentence."
        )

        print("SUCCESS: Gemini API is working!")
        print("Gemini response:", response.text)

    except Exception as e:
        print("ERROR: Gemini API test failed.")
        print("Details:", str(e))