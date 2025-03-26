# Install necessary libraries
import re
import json
import folium
import spacy
import whisper
import httpx
import h3
from geopy.distance import geodesic
from geopy.point import Point
from cachetools import TTLCache
from pymongo import MongoClient, GEOSPHERE
from pydantic import BaseModel
import certifi
import asyncio
from fastapi import FastAPI

# Load spaCy model and add an entity ruler for geospatial relations
from spacy.pipeline import EntityRuler

# Initialize FastAPI app
app = FastAPI()

# Load NLP model
nlp = spacy.load("en_core_web_sm")
ruler = nlp.add_pipe("entity_ruler")

# Define patterns for geospatial relations
patterns = [
    {
        "label": "GEO_RELATION",
        "pattern": [{"LOWER": {"IN": ["within", "near", "adjacent"]}}, {"OP": "*"}, {"ENT_TYPE": "QUANTITY"}]
    }
]
ruler.add_patterns(patterns)

# Load Whisper model for voice transcription
whisper_model = whisper.load_model("base")

# In-memory cache
cache = TTLCache(maxsize=100, ttl=600)

# MongoDB setup
username = "DRM_1"
password = "JKfMSCgDzfaUC3bZ"
uri = f"mongodb+srv://{username}:{password}@cluster0.38cb2.mongodb.net/?retryWrites=true&w=majority"

try:
    mongo_client = MongoClient(uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    db = mongo_client["geospatialDB"]
    custom_locations = db["locations"]
    custom_locations.create_index([("location", GEOSPHERE)])
    print("MongoDB connected successfully!")
except Exception as e:
    custom_locations = None
    print("MongoDB connection failed:", str(e))

# API Endpoints
OSM_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
OSRM_ROUTE_URL = "http://router.project-osrm.org/route/v1/driving/"

# ---------------------------
# Helper Functions
# ---------------------------

def advanced_parse_query(query: str):
    """Parses a natural language query for geospatial relations."""
    doc = nlp(query)
    entities = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]
    primary_location = entities[0] if entities else None

    distance_match = re.search(r"(\d+(?:.\d+)?)\s*km", query, re.IGNORECASE)
    distance = float(distance_match.group(1)) if distance_match else None

    direction_match = re.search(r"(north|south|east|west)\s+of", query, re.IGNORECASE)
    direction = direction_match.group(1).lower() if direction_match else None

    poi_keywords = ["restaurant", "hospital", "park", "school", "forest", "museum", "airport"]
    category = next((token.lemma_.lower() for token in doc if token.lemma_.lower() in poi_keywords), None)

    return {"entity": primary_location, "distance": distance, "direction": direction, "category": category}

async def geocode_location(location: str):
    """Geocodes a location using OpenStreetMap."""
    if location in cache:
        return cache[location]

    async with httpx.AsyncClient() as client:
        response = await client.get(OSM_NOMINATIM_URL, params={"q": location, "format": "json"})
        if response.status_code == 200 and response.json():
            coords = {"lat": float(response.json()[0]['lat']), "lon": float(response.json()[0]['lon'])}
            cache[location] = coords
            return coords
    return None

def adjust_coordinates(coords, direction, distance_km):
    """Adjusts coordinates based on direction and distance."""
    origin = Point(coords["lat"], coords["lon"])
    directions = {"north": 0, "east": 90, "south": 180, "west": 270}
    bearing = directions.get(direction.lower(), 0)
    adjusted = geodesic(kilometers=distance_km).destination(origin, bearing=bearing)
    return {"lat": adjusted.latitude, "lon": adjusted.longitude}

def compute_h3_index(coords, resolution: int = 8):
    """Computes the H3 index for a given location."""
    return h3.latlng_to_cell(coords["lat"], coords["lon"], resolution)

# ---------------------------
# FastAPI Endpoints
# ---------------------------

@app.get("/")
async def root():
    return {"message": "Geospatial API is running!"}

@app.get("/parse_query/")
async def parse_query(query: str):
    """Parses a natural language query."""
    return advanced_parse_query(query)

@app.get("/geocode/")
async def get_geocode(location: str):
    """Returns geocoded coordinates of a location."""
    coords = await geocode_location(location)
    return {"location": location, "coordinates": coords} if coords else {"error": "Location not found"}

@app.get("/adjust_coordinates/")
async def get_adjusted_coordinates(location: str, direction: str, distance: float):
    """Adjusts coordinates based on distance and direction."""
    coords = await geocode_location(location)
    if coords:
        adjusted = adjust_coordinates(coords, direction, distance)
        return {"original": coords, "adjusted": adjusted}
    return {"error": "Location not found"}

@app.get("/h3_index/")
async def get_h3_index(location: str):
    """Returns the H3 index for a given location."""
    coords = await geocode_location(location)
    if coords:
        h3_index = compute_h3_index(coords)
        return {"location": location, "h3_index": h3_index}
    return {"error": "Location not found"}

# ---------------------------
# Run the FastAPI App
# ---------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
