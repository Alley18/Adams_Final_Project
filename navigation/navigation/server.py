import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
# In a real app, use environment variables for keys
KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY", "YOUR_KAKAO_REST_API_KEY")

# --- KAKAOMAP ROUTING LOGIC ---
def get_kakao_route(origin, destination, priority="RECOMMEND"):
    """
    Fetches route from Kakao Mobility API.
    origin/destination: "longitude,latitude"
    priority: RECOMMEND, TIME, DISTANCE
    """
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {
        "Authorization": f"KakaoAK {KAKAO_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {
        "origin": origin,
        "destination": destination,
        "priority": priority,
        "car_type": 1,
        "car_fuel": "GASOLINE"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Kakao API Error: {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}

# --- API ENDPOINTS ---

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "service": "ADAMS Navigation Backend"})

@app.route("/route", methods=["POST"])
def get_route():
    """
    Expected JSON:
    {
        "origin": "127.0276,37.4979",
        "destination": "126.9779,37.5670",
        "emotion": "calm"
    }
    """
    data = request.json
    origin = data.get("origin")
    destination = data.get("destination")
    emotion = data.get("emotion", "calm")
    
    # Logic to adjust priority based on emotion
    # calm -> RECOMMEND (scenic/balanced)
    # stressed -> TIME (fastest)
    # sleepy -> DISTANCE (shortest/simplest)
    # angry -> TIME (get there fast)
    
    priority_map = {
        "calm": "RECOMMEND",
        "stressed": "TIME",
        "sleepy": "DISTANCE",
        "angry": "TIME"
    }
    
    priority = priority_map.get(emotion, "RECOMMEND")
    
    # If API key is not set, return mock data for testing
    if KAKAO_API_KEY == "YOUR_KAKAO_REST_API_KEY":
        return jsonify({
            "status": "mock",
            "emotion": emotion,
            "priority": priority,
            "coordinates": [
                [37.5670, 126.9779],
                [37.5690, 126.9790],
                [37.5750, 126.9820],
                [37.4979, 127.0276]
            ]
        })

    route_result = get_kakao_route(origin, destination, priority)
    return jsonify(route_result)

if __name__ == "__main__":
    print("🚗 ADAMS Enhanced Navigation Server Running on http://0.0.0.0:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
