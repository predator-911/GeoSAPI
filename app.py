import os
import logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
import spacy
import re
from functools import lru_cache
from typing import List, Optional

app = FastAPI(title="GeoGPT Enhanced API", version="2.0")

# CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GeoGPT")

# Load spaCy model once
nlp = spacy.load("en_core_web_md")

# Initialize geolocator
geolocator = Nominatim(user_agent="geo_gpt_pro_fastapi", timeout=10)

# Environment API keys
ORS_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY")
TIMEZONEDB_API_KEY = os.getenv("TIMEZONEDB_API_KEY")

# Weather code to icon mapping (example icons URLs, replace with your hosted icons)
WEATHER_CODE_MAP = {
    0: {"desc": "Clear sky", "icon": "https://cdn-icons-png.flaticon.com/512/869/869869.png"},
    1: {"desc": "Mainly clear", "icon": "https://cdn-icons-png.flaticon.com/512/1163/1163661.png"},
    2: {"desc": "Partly cloudy", "icon": "https://cdn-icons-png.flaticon.com/512/1163/1163624.png"},
    3: {"desc": "Overcast", "icon": "https://cdn-icons-png.flaticon.com/512/414/414825.png"},
    45: {"desc": "Fog", "icon": "https://cdn-icons-png.flaticon.com/512/4005/4005909.png"},
    48: {"desc": "Depositing rime fog", "icon": "https://cdn-icons-png.flaticon.com/512/4005/4005909.png"},
    51: {"desc": "Light drizzle", "icon": "https://cdn-icons-png.flaticon.com/512/1163/1163620.png"},
    53: {"desc": "Moderate drizzle", "icon": "https://cdn-icons-png.flaticon.com/512/1163/1163620.png"},
    55: {"desc": "Dense drizzle", "icon": "https://cdn-icons-png.flaticon.com/512/1163/1163620.png"},
    61: {"desc": "Slight rain", "icon": "https://cdn-icons-png.flaticon.com/512/1163/1163615.png"},
    63: {"desc": "Moderate rain", "icon": "https://cdn-icons-png.flaticon.com/512/1163/1163615.png"},
    65: {"desc": "Heavy rain", "icon": "https://cdn-icons-png.flaticon.com/512/1163/1163615.png"},
    71: {"desc": "Slight snow fall", "icon": "https://cdn-icons-png.flaticon.com/512/642/642102.png"},
    73: {"desc": "Moderate snow fall", "icon": "https://cdn-icons-png.flaticon.com/512/642/642102.png"},
    75: {"desc": "Heavy snow fall", "icon": "https://cdn-icons-png.flaticon.com/512/642/642102.png"},
    95: {"desc": "Thunderstorm", "icon": "https://cdn-icons-png.flaticon.com/512/1146/1146869.png"},
    96: {"desc": "Thunderstorm with slight hail", "icon": "https://cdn-icons-png.flaticon.com/512/1146/1146869.png"},
    99: {"desc": "Thunderstorm with heavy hail", "icon": "https://cdn-icons-png.flaticon.com/512/1146/1146869.png"},
}

# Models

class LocationResponse(BaseModel):
    location: str
    latitude: float
    longitude: float
    address: str

class WeatherCurrentResponse(BaseModel):
    temperature: float
    humidity: float
    wind_speed: float
    description: str
    icon_url: Optional[str]

class WeatherDailyItem(BaseModel):
    date: str
    temp_min: float
    temp_max: float
    precipitation_sum: float
    windspeed_max: float
    weather_code: int
    description: str
    icon_url: Optional[str]

class WeatherDailyResponse(BaseModel):
    location: str
    daily: List[WeatherDailyItem]

class WeatherHourlyItem(BaseModel):
    time: str
    temperature: float
    precipitation: float
    windspeed: float
    weather_code: int
    description: str
    icon_url: Optional[str]

class WeatherHourlyResponse(BaseModel):
    location: str
    hourly: List[WeatherHourlyItem]

class AirQualityResponse(BaseModel):
    location: str
    pm10: Optional[float]
    pm2_5: Optional[float]
    ozone: Optional[float]
    nitrogen_dioxide: Optional[float]
    sulfur_dioxide: Optional[float]
    carbon_monoxide: Optional[float]

class PlaceResponse(BaseModel):
    name: str
    latitude: float
    longitude: float
    type: Optional[str]
    opening_hours: Optional[str]
    website: Optional[str]
    phone: Optional[str]

class DistanceResponse(BaseModel):
    origin: str
    destination: str
    distance_km: float
    walking_time: str
    driving_time: str

class TimeZoneResponse(BaseModel):
    location: str
    timezone: str
    local_time: str
    gmt_offset: int

# Utility functions

@lru_cache(maxsize=1000)
def geocode(location: str):
    try:
        loc = geolocator.geocode(location)
        if loc:
            return loc.latitude, loc.longitude, loc.address
        else:
            return None, None, None
    except Exception as e:
        logger.error(f"Geocoding error for '{location}': {e}")
        return None, None, None

def map_weather_code(code: int):
    info = WEATHER_CODE_MAP.get(code, {"desc": "Unknown", "icon": None})
    return info["desc"], info["icon"]

def format_duration(hours: float) -> str:
    h = int(hours)
    m = int((hours - h) * 60)
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    return " ".join(parts) if parts else "0m"

# API Endpoints

@app.get("/geocode/{location}", response_model=LocationResponse)
def api_geocode(location: str):
    lat, lon, address = geocode(location)
    if lat is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return LocationResponse(location=location, latitude=lat, longitude=lon, address=address)

@app.get("/weather/current/{location}", response_model=WeatherCurrentResponse)
def api_weather_current(location: str):
    lat, lon, _ = geocode(location)
    if lat is None:
        raise HTTPException(status_code=404, detail="Location not found")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        cw = data.get("current_weather", {})
        desc, icon = map_weather_code(cw.get("weathercode", -1))
        return WeatherCurrentResponse(
            temperature=cw.get("temperature"),
            humidity=None,  # Open-Meteo current_weather does not provide humidity directly
            wind_speed=cw.get("windspeed"),
            description=desc,
            icon_url=icon,
        )
    except Exception as e:
        logger.error(f"Open-Meteo current weather error: {e}")
        raise HTTPException(status_code=503, detail="Weather service unavailable")

@app.get("/weather/daily/{location}", response_model=WeatherDailyResponse)
def api_weather_daily(location: str):
    lat, lon, _ = geocode(location)
    if lat is None:
        raise HTTPException(status_code=404, detail="Location not found")
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,weathercode"
        f"&timezone=auto"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        daily = []
        for i in range(len(data["daily"]["time"])):
            code = data["daily"]["weathercode"][i]
            desc, icon = map_weather_code(code)
            daily.append(
                WeatherDailyItem(
                    date=data["daily"]["time"][i],
                    temp_min=data["daily"]["temperature_2m_min"][i],
                    temp_max=data["daily"]["temperature_2m_max"][i],
                    precipitation_sum=data["daily"]["precipitation_sum"][i],
                    windspeed_max=data["daily"]["windspeed_10m_max"][i],
                    weather_code=code,
                    description=desc,
                    icon_url=icon,
                )
            )
        return WeatherDailyResponse(location=location, daily=daily)
    except Exception as e:
        logger.error(f"Open-Meteo daily weather error: {e}")
        raise HTTPException(status_code=503, detail="Weather service unavailable")

@app.get("/weather/hourly/{location}", response_model=WeatherHourlyResponse)
def api_weather_hourly(location: str):
    lat, lon, _ = geocode(location)
    if lat is None:
        raise HTTPException(status_code=404, detail="Location not found")
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,precipitation,windspeed_10m,weathercode"
        f"&timezone=auto"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        hourly = []
        for i in range(len(data["hourly"]["time"])):
            code = data["hourly"]["weathercode"][i]
            desc, icon = map_weather_code(code)
            hourly.append(
                WeatherHourlyItem(
                    time=data["hourly"]["time"][i],
                    temperature=data["hourly"]["temperature_2m"][i],
                    precipitation=data["hourly"]["precipitation"][i],
                    windspeed=data["hourly"]["windspeed_10m"][i],
                    weather_code=code,
                    description=desc,
                    icon_url=icon,
                )
            )
        return WeatherHourlyResponse(location=location, hourly=hourly)
    except Exception as e:
        logger.error(f"Open-Meteo hourly weather error: {e}")
        raise HTTPException(status_code=503, detail="Weather service unavailable")

@app.get("/air-quality/{location}", response_model=AirQualityResponse)
def api_air_quality(location: str):
    lat, lon, _ = geocode(location)
    if lat is None:
        raise HTTPException(status_code=404, detail="Location not found")
    url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}"
        f"&hourly=pm10,pm2_5,ozone,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        # Take latest hourly data if available
        hourly = data.get("hourly", {})
        if not hourly or not hourly.get("time"):
            raise HTTPException(status_code=503, detail="Air quality data unavailable")
        idx = -1  # latest data index
        return AirQualityResponse(
            location=location,
            pm10=hourly.get("pm10", [None])[idx],
            pm2_5=hourly.get("pm2_5", [None])[idx],
            ozone=hourly.get("ozone", [None])[idx],
            nitrogen_dioxide=hourly.get("nitrogen_dioxide", [None])[idx],
            sulfur_dioxide=hourly.get("sulphur_dioxide", [None])[idx],
            carbon_monoxide=hourly.get("carbon_monoxide", [None])[idx],
        )
    except Exception as e:
        logger.error(f"Open-Meteo air quality error: {e}")
        raise HTTPException(status_code=503, detail="Air quality service unavailable")

@app.get("/nearby-places/{location}", response_model=List[PlaceResponse])
def api_nearby_places(
    location: str,
    place_type: str = Query("restaurant", description="OSM amenity type"),
    radius: int = Query(5000, ge=100, le=50000, description="Search radius in meters"),
    max_results: int = Query(15, ge=1, le=50, description="Max number of places"),
):
    lat, lon, _ = geocode(location)
    if lat is None:
        raise HTTPException(status_code=404, detail="Location not found")
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="{place_type}"](around:{radius},{lat},{lon});
      way["amenity"="{place_type}"](around:{radius},{lat},{lon});
      relation["amenity"="{place_type}"](around:{radius},{lat},{lon});
    );
    out center {max_results};
    """
    try:
        r = requests.post(overpass_url, data=query, timeout=30)
        r.raise_for_status()
        elements = r.json().get("elements", [])[:max_results]
        places = []
        for el in elements:
            if el.get("tags") is None:
                continue
            name = el["tags"].get("name", f"Unnamed {place_type}")
            lat_ = el.get("lat") or el.get("center", {}).get("lat")
            lon_ = el.get("lon") or el.get("center", {}).get("lon")
            if lat_ is None or lon_ is None:
                continue
            places.append(
                PlaceResponse(
                    name=name,
                    latitude=lat_,
                    longitude=lon_,
                    type=el["tags"].get("amenity"),
                    opening_hours=el["tags"].get("opening_hours"),
                    website=el["tags"].get("website"),
                    phone=el["tags"].get("phone"),
                )
            )
        return places
    except Exception as e:
        logger.error(f"Overpass API error: {e}")
        raise HTTPException(status_code=503, detail="Places service unavailable")

@app.get("/search-places/{location}", response_model=List[PlaceResponse])
def api_search_places(
    location: str,
    query: str = Query(..., description="Search query for place name"),
    radius: int = Query(10000, ge=100, le=50000, description="Search radius in meters"),
    max_results: int = Query(15, ge=1, le=50, description="Max number of places"),
):
    lat, lon, _ = geocode(location)
    if lat is None:
        raise HTTPException(status_code=404, detail="Location not found")
    overpass_url = "https://overpass-api.de/api/interpreter"
    # Search by name (case-insensitive)
    query_escaped = query.replace('"', '\\"')
    overpass_query = f"""
    [out:json][timeout:25];
    (
      node["name"~"{query_escaped}",i](around:{radius},{lat},{lon});
      way["name"~"{query_escaped}",i](around:{radius},{lat},{lon});
      relation["name"~"{query_escaped}",i](around:{radius},{lat},{lon});
    );
    out center {max_results};
    """
    try:
        r = requests.post(overpass_url, data=overpass_query, timeout=30)
        r.raise_for_status()
        elements = r.json().get("elements", [])[:max_results]
        places = []
        for el in elements:
            if el.get("tags") is None:
                continue
            name = el["tags"].get("name", "Unnamed place")
            lat_ = el.get("lat") or el.get("center", {}).get("lat")
            lon_ = el.get("lon") or el.get("center", {}).get("lon")
            if lat_ is None or lon_ is None:
                continue
            places.append(
                PlaceResponse(
                    name=name,
                    latitude=lat_,
                    longitude=lon_,
                    type=el["tags"].get("amenity"),
                    opening_hours=el["tags"].get("opening_hours"),
                    website=el["tags"].get("website"),
                    phone=el["tags"].get("phone"),
                )
            )
        return places
    except Exception as e:
        logger.error(f"Overpass API search error: {e}")
        raise HTTPException(status_code=503, detail="Places search service unavailable")

@app.get("/distance/{origin}/{destination}", response_model=DistanceResponse)
def api_distance(origin: str, destination: str):
    lat1, lon1, _ = geocode(origin)
    lat2, lon2, _ = geocode(destination)
    if None in [lat1, lon1, lat2, lon2]:
        raise HTTPException(status_code=404, detail="One or both locations not found")

    # Calculate geodesic distance
    dist_km = geodesic((lat1, lon1), (lat2, lon2)).kilometers

    # Use OpenRouteService for realistic travel times if API key is set
    walking_time = None
    driving_time = None
    if ORS_API_KEY:
        headers = {"Authorization": ORS_API_KEY}
        try:
            # Walking route
            walking_resp = requests.post(
                "https://api.openrouteservice.org/v2/directions/foot-walking",
                json={"coordinates": [[lon1, lat1], [lon2, lat2]]},
                headers=headers,
                timeout=10,
            )
            walking_resp.raise_for_status()
            walking_data = walking_resp.json()
            walking_seconds = walking_data["features"][0]["properties"]["segments"][0]["duration"]
            walking_time = format_duration(walking_seconds / 3600)

            # Driving route
            driving_resp = requests.post(
                "https://api.openrouteservice.org/v2/directions/driving-car",
                json={"coordinates": [[lon1, lat1], [lon2, lat2]]},
                headers=headers,
                timeout=10,
            )
            driving_resp.raise_for_status()
            driving_data = driving_resp.json()
            driving_seconds = driving_data["features"][0]["properties"]["segments"][0]["duration"]
            driving_time = format_duration(driving_seconds / 3600)
        except Exception as e:
            logger.warning(f"OpenRouteService routing error: {e}")

    # Fallback to simple estimates if ORS fails or no API key
    if walking_time is None:
        walking_time = format_duration(dist_km / 5)
    if driving_time is None:
        driving_time = format_duration(dist_km / 60)

    return DistanceResponse(
        origin=origin,
        destination=destination,
        distance_km=round(dist_km, 2),
        walking_time=walking_time,
        driving_time=driving_time,
    )

@app.get("/timezone/{location}", response_model=TimeZoneResponse)
def api_timezone(location: str):
    lat, lon, _ = geocode(location)
    if lat is None:
        raise HTTPException(status_code=404, detail="Location not found")
    if not TIMEZONEDB_API_KEY:
        raise HTTPException(status_code=503, detail="TimeZoneDB API key not configured")
    url = (
        f"http://api.timezonedb.com/v2.1/get-time-zone?key={TIMEZONEDB_API_KEY}"
        f"&format=json&by=position&lat={lat}&lng={lon}"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data["status"] != "OK":
            raise HTTPException(status_code=503, detail="Time zone service error")
        return TimeZoneResponse(
            location=location,
            timezone=data["zoneName"],
            local_time=data["formatted"],
            gmt_offset=data["gmtOffset"],
        )
    except Exception as e:
        logger.error(f"TimeZoneDB API error: {e}")
        raise HTTPException(status_code=503, detail="Time zone service unavailable")
    
