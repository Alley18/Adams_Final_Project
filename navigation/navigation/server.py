import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
# Kakao API is optional. If not provided, the system falls back to OSRM (Free).
KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY", "")

# --- OSRM ROUTING LOGIC (FREE/NO KEY) ---
def get_osrm_route(origin, destination, profile="driving"):
    """
    Fetches route from Open Source Routing Machine (OSRM).
    origin/destination: "longitude,latitude"
    """
    # OSRM expects: longitude,latitude;longitude,latitude
    url = f"https://router.project-osrm.org/route/v1/{profile}/{origin};{destination}?overview=full&geometries=geojson"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 'Ok':
                # Convert OSRM GeoJSON to a simple coordinate list [lat, lon]
                # OSRM returns [lon, lat], we swap for the frontend
                raw_coords = data['routes'][0]['geometry']['coordinates']
                swapped_coords = [[c[1], c[0]] for c in raw_coords]
                
                return {
                    "status": "success",
                    "source": "OSRM",
                    "duration_sec": data['routes'][0]['duration'],
                    "distance_m": data['routes'][0]['distance'],
                    "coordinates": swapped_coords
                }
        return {"error": "OSRM Routing Failed", "details": response.text}
    except Exception as e:
        return {"error": str(e)}

# --- KAKAOMAP ROUTING LOGIC (PREMIUM OPTION) ---
def get_kakao_route(origin, destination, priority="RECOMMEND"):
    """
    Fetches route from Kakao Mobility API.
    """
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {
        "Authorization": f"KakaoAK {KAKAO_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {
        "origin": origin,
        "destination": destination,
        "priority": priority
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            # Extract coordinates from Kakao structure
            coords = []
            for section in data['routes'][0]['sections']:
                for road in section['roads']:
                    for i in range(0, len(road['vertexes']), 2):
                        coords.append([road['vertexes'][i+1], road['vertexes'][i]])
            
            return {
                "status": "success",
                "source": "KakaoMap",
                "duration_sec": data['routes'][0]['summary']['duration'],
                "coordinates": coords
            }
        return None
    except:
        return None

# --- API ENDPOINTS ---

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "service": "ADAMS Navigation Backend"})

@app.route("/route", methods=["POST"])
def get_route():
    data = request.json
    origin = data.get("origin")
    destination = data.get("destination")
    emotion = data.get("emotion", "calm")
    
    # Logic to adjust profile/priority based on emotion
    profile_map = {
        "calm": "driving",      # standard
        "stressed": "driving",  # fastest (OSRM default)
        "sleepy": "driving",    # safest
        "angry": "driving"      # fastest
    }
    
    # 1. Try Kakao if Key exists
    if KAKAO_API_KEY:
        priority_map = {"calm": "RECOMMEND", "stressed": "TIME", "sleepy": "DISTANCE"}
        kakao_result = get_kakao_route(origin, destination, priority_map.get(emotion, "RECOMMEND"))
        if kakao_result:
            return jsonify(kakao_result)

    # 2. Fallback to OSRM (Works out of the box for the Professor)
    osrm_result = get_osrm_route(origin, destination, profile_map.get(emotion, "driving"))
    return jsonify(osrm_result)

if __name__ == "__main__":
    print("🚗 ADAMS Backend Running (OSRM Default, Kakao-Ready)")
    app.run(debug=True, host="0.0.0.0", port=5000)
