import firebase_admin
from firebase_admin import credentials, db

# 1. Setup the "Key"
cred = credentials.Certificate("serviceAccountKey.json")

# 2. Open the "Bridge"
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://adams-system-a1998-default-rtdb.asia-southeast1.firebasedatabase.app/'

# 3. Send a test message
ref = db.reference('/test_connection')
ref.set({
    "message": "Hello from Raspberry Pi!",
    "status": "Online"
})

print("✅ Data sent! Check your Firebase browser tab.")