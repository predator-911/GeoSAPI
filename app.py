from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from transformers import pipeline
import requests
from geopy.distance import geodesic
import pymongo
import certifi
import os

# Initialize FastAPI app
app = FastAPI()

# Enable CORS (For frontend communication)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load NLP model for location extraction
ner_pipeline = pipeline("ner", model="dslim/bert-base-NER")

# Connect to MongoDB Atlas
MONGO_URI = os.getenv("MONGO_URI", f"mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}@cluster0.38cb2.mongodb.net/{MONGO_DB}?retryWrites=true&w=majority")
client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client["Fashin_db"]  # Database Name
crime_collection = db["CrimeData"]

# Function to extract locations from text
def extract_location(text: str):
    results = ner_pipeline(text)
    locations = [r["word"] for r in results if "LOC" in r["entity"]]
    return locations

# Function to get coordinates from OpenStreetMap
def get_location_coordinates(place: str):
    url = f"https://nominatim.openstreetmap.org/search?q={place}&format=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200 and response.text.strip():
        data = response.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    return None, None

# Function to get nearby places using Overpass API
def get_nearby_places(place: str, category: str, radius: int = 5):
    lat, lon = get_location_coordinates(place)
    if not lat or not lon:
        return []

    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    node
      ["amenity"="{category}"]
      (around:{radius * 1000},{lat},{lon});
    out;
    """
    
    response = requests.get(overpass_url, params={"data": query})
    
    if response.status_code == 200:
        data = response.json()
        nearby_places = [
            {
                "name": f"Place {i+1}",
                "lat": p["lat"],
                "lon": p["lon"],
                "maps_link": f"https://www.openstreetmap.org/?mlat={p['lat']}&mlon={p['lon']}"
            }
            for i, p in enumerate(data.get("elements", []))
        ]
        return nearby_places[:10]
    
    return []

# Function to get crime data for a location
def get_crime_data(place: str):
    lat, lon = get_location_coordinates(place)
    if not lat or not lon:
        return {"error": "Invalid location"}

    crime_entry = crime_collection.find_one({"place": place})
    if crime_entry:
        return {"place": place, "crime_level": crime_entry["crime_level"]}

    return {"place": place, "crime_level": "Unknown"}

# Root Endpoint
@app.get("/")
def home():
    return {"message": "FastAPI server is running on Render! Use /query, /nearby, and /crime endpoints."}

# Endpoint to extract location and find coordinates
@app.post("/query")
def query_location(text: str):
    locations = extract_location(text)
    if not locations:
        raise HTTPException(status_code=400, detail="No location found")

    place = locations[0]
    lat, lon = get_location_coordinates(place)

    return {"place": place, "latitude": lat, "longitude": lon}

# Endpoint to find nearby places
@app.post("/nearby")
def query_nearby(place: str, category: str, radius: int = 5):
    places = get_nearby_places(place, category, radius)
    return {"nearby_places": places}

# Endpoint to get crime data for a location
@app.post("/crime")
def query_crime(place: str):
    crime_info = get_crime_data(place)
    return crime_info
