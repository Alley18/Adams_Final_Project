import os
from google import genai
from dotenv import load_dotenv

# Path logic to find .env in the parent folder
basedir = os.path.abspath(os.path.dirname(__file__))
dotenv_path = os.path.join(basedir, "..", ".env")
load_dotenv(dotenv_path)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("--- Checking Available Models ---")
try:
    # Just print the model names
    for model in client.models.list():
        print(f"Model ID: {model.name}")
except Exception as e:
    print(f"Error: {e}")