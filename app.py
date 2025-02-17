from flask import Flask, request, jsonify
from flask_cors import CORS
from transformers import pipeline
import requests
from geopy.distance import geodesic

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Load NLP model for location extraction
ner_pipeline = pipeline("ner", model="dslim/bert-base-NER")

def extract_location(text):
    """Extracts location names from text using NLP"""
    results = ner_pipeline(text)
    locations = [r['word'] for r in results if 'LOC' in r['entity']]
    return locations

def get_location_coordinates(place):
    """Fetches latitude & longitude using OpenStreetMap API"""
    url = f"https://nominatim.openstreetmap.org/search?q={place}&format=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200 and response.text.strip():
        data = response.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    return None, None

def get_nearby_places(place, category, radius=5):
    """Finds nearby places of a given category and filters them by distance"""
    lat, lon = get_location_coordinates(place)
    if not lat or not lon:
        return []

    search_query = f"{category} in {place}"
    url = f"https://nominatim.openstreetmap.org/search?q={search_query}&format=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        nearby_places = [
            {
                "name": p["display_name"],
                "lat": float(p["lat"]),
                "lon": float(p["lon"]),
                "maps_link": f"https://www.google.com/maps/search/?api=1&query={p['lat']},{p['lon']}"
            }
            for p in data
        ]

        # Filter places by distance
        filtered_places = [
            p for p in nearby_places
            if geodesic((lat, lon), (p["lat"], p["lon"])).km <= radius
        ]
        return filtered_places[:10]
    
    return []

@app.route('/')
def home():
    return "Flask server is running! Use /query and /nearby endpoints."

@app.route('/query', methods=['POST'])
def query_location():
    """API Endpoint: Extracts location & finds coordinates"""
    data = request.json
    text = data.get('text', '')

    locations = extract_location(text)
    if not locations:
        return jsonify({"error": "No location found"}), 400

    place = locations[0]
    lat, lon = get_location_coordinates(place)

    return jsonify({"place": place, "latitude": lat, "longitude": lon})

@app.route('/nearby', methods=['POST'])
def query_nearby():
    """API Endpoint: Finds nearby places"""
    data = request.json
    place = data.get('place', '')
    category = data.get('category', '')
    radius = data.get('radius', 5)  # Default radius: 5 km

    places = get_nearby_places(place, category, radius)
    return jsonify({"nearby_places": places})

# Run the app using Gunicorn for production
if __name__ == '__main__':
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000)
