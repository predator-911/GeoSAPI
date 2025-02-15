from flask import Flask, request, jsonify
from transformers import pipeline
import requests

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Load NLP model
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
            return data[0]["lat"], data[0]["lon"]
    return None, None

def get_nearby_places(place, category):
    """Finds nearby places (hospitals, schools, etc.)"""
    url = f"https://nominatim.openstreetmap.org/search?q={category}+in+{place}&format=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return [{"name": p["display_name"], "lat": p["lat"], "lon": p["lon"]} for p in data[:5]]
    
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

    places = get_nearby_places(place, category)
    return jsonify({"nearby_places": places})

# Run the app using Gunicorn for production
if __name__ == '__main__':
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000)
