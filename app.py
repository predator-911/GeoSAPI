import streamlit as st
import folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from streamlit_folium import st_folium
import requests
import subprocess
import spacy
import re
from folium.plugins import MarkerCluster

# Set page configuration (must be the first Streamlit command)
st.set_page_config(
    page_title="GeoGPT Pro",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Function to check and download spaCy model dynamically
def load_spacy_model(model_name="en_core_web_lg"):
    try:
        nlp = spacy.load(model_name)
        return nlp
    except OSError:
        with st.spinner(f"Downloading spaCy model '{model_name}'..."):
            subprocess.run(["python", "-m", "spacy", "download", model_name], check=True)
        nlp = spacy.load(model_name)
        return nlp

# Load spaCy model dynamically
nlp = load_spacy_model()

# Initialize session state for chat history and caching
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

if "geolocation_cache" not in st.session_state:
    st.session_state["geolocation_cache"] = {}

if "show_map" not in st.session_state:
    st.session_state["show_map"] = False

if "map_data" not in st.session_state:
    st.session_state["map_data"] = None

# Function to extract location from text using spaCy
def extract_location_from_text(text):
    doc = nlp(text)
    locations = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC", "FAC"]]
    
    # Try to extract specific neighborhood or district mentions
    neighborhoods = re.findall(r'in ([A-Za-z\s]+) neighborhood|in ([A-Za-z\s]+) district', text)
    if neighborhoods:
        for n in neighborhoods:
            for part in n:
                if part and part not in locations:
                    locations.append(part)
    
    return locations

# Function to get location info with caching
def get_location_info(location_name, detailed=False):
    if location_name in st.session_state["geolocation_cache"]:
        lat, lon = st.session_state["geolocation_cache"][location_name]
        if detailed:
            geolocator = Nominatim(user_agent="geo_gpt_pro")
            location = geolocator.geocode(location_name, exactly_one=True)
            return lat, lon, location.address if location else None
        return lat, lon
    
    geolocator = Nominatim(user_agent="geo_gpt_pro")
    try:
        location = geolocator.geocode(location_name, exactly_one=True)
        if location:
            st.session_state["geolocation_cache"][location_name] = (location.latitude, location.longitude)
            if detailed:
                return location.latitude, location.longitude, location.address
            return location.latitude, location.longitude
    except Exception:
        if detailed:
            return None, None, None
        return None, None

# Function to get nearby places using Overpass API
def get_nearby_places(lat, lon, place_type="restaurant", radius=5000, num_places=15):
    url = "https://overpass-api.de/api/interpreter"
    query = f"[out:json];node[amenity={place_type}](around:{radius},{lat},{lon});out;"
    
    try:
        response = requests.get(url, params={"data": query})
        if response.status_code == 200:
            return response.json().get("elements", [])[:num_places]
    except requests.RequestException:
        return []
    return []

# Function to get weather using Open-Meteo API
def get_weather(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code&timezone=auto"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            current = data.get('current', {})
            
            # Weather code interpretation
            weather_codes = {
                0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Fog", 48: "Depositing rime fog",
                51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
                61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                71: "Slight snow fall", 73: "Moderate snow fall", 75: "Heavy snow fall",
                95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail"
            }
            weather_code = current.get('weather_code')
            weather_description = weather_codes.get(weather_code, "Unknown")
            
            return {
                "Temperature": f"{current.get('temperature_2m')}°C",
                "Humidity": f"{current.get('relative_humidity_2m')}%",
                "Wind Speed": f"{current.get('wind_speed_10m')} km/h",
                "Description": weather_description
            }
    except requests.RequestException:
        return None

# Enhanced function to calculate distance between two locations
def get_distance(text):
    # Extract origin and destination
    match = re.search(r'(distance|far|how far) (?:from|between)? ([A-Za-z\s,]+) (?:to|and) ([A-Za-z\s,]+)', text, re.IGNORECASE)
    
    if not match:
        return "I couldn't understand the distance request. Please specify origin and destination clearly."
    
    origin = match.group(2).strip()
    destination = match.group(3).strip()
    
    lat1, lon1 = get_location_info(origin)
    lat2, lon2 = get_location_info(destination)
    
    if None not in (lat1, lon1, lat2, lon2):
        distance_km = geodesic((lat1, lon1), (lat2, lon2)).km
        
        # Estimate travel times (rough estimates)
        walking_time = distance_km / 5  # Assuming 5 km/h walking speed
        driving_time = distance_km / 60  # Assuming 60 km/h driving speed
        
        response = f"📏 **Distance from {origin} to {destination}:** {distance_km:.2f} km\n\n"
        response += "**Estimated Travel Times:**\n"
        
        # Format walking time
        if walking_time < 1:
            response += f"- Walking: {walking_time * 60:.0f} minutes\n"
        else:
            hours = int(walking_time)
            minutes = int((walking_time - hours) * 60)
            response += f"- Walking: {hours} hour{'s' if hours > 1 else ''}"
            if minutes > 0:
                response += f" {minutes} minute{'s' if minutes > 1 else ''}"
            response += "\n"
        
        # Format driving time
        if driving_time < 1:
            response += f"- Driving: {driving_time * 60:.0f} minutes\n"
        else:
            hours = int(driving_time)
            minutes = int((driving_time - hours) * 60)
            response += f"- Driving: {hours} hour{'s' if hours > 1 else ''}"
            if minutes > 0:
                response += f" {minutes} minute{'s' if minutes > 1 else ''}"
            response += "\n"
        
        # Create route map
        map_ = folium.Map()
        
        # Add markers for origin and destination
        folium.Marker([lat1, lon1], popup=origin, tooltip=origin,
                     icon=folium.Icon(color="green", icon="play")).add_to(map_)
        folium.Marker([lat2, lon2], popup=destination, tooltip=destination,
                     icon=folium.Icon(color="red", icon="flag")).add_to(map_)
        
        # Add a line connecting the two points
        folium.PolyLine(
            locations=[[lat1, lon1], [lat2, lon2]],
            color="blue",
            weight=3,
            opacity=0.7
        ).add_to(map_)
        
        # Fit the map to the bounds
        map_.fit_bounds([[lat1, lon1], [lat2, lon2]])
        
        # Store map in session state
        st.session_state["map_data"] = map_
        st.session_state["show_map"] = True
        
        return response
    else:
        return f"I couldn't find one or both locations: {origin} and {destination}."

# Function to get country information
def get_country_info(country_name):
    url = f"https://restcountries.com/v3.1/name/{country_name}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()[0]
            return {
                "Capital": data.get("capital", ["Unknown"])[0],
                "Population": f"{data.get('population', 0):,}",
                "Region": data.get("region", "Unknown"),
                "Languages": ", ".join(list(data.get("languages", {}).values())),
                "Currency": list(data.get("currencies", {}).values())[0].get("name", "Unknown") if data.get("currencies") else "Unknown"
            }
    except (requests.RequestException, IndexError, KeyError):
        return None

# Title and app intro
st.title("🌍 GeoGPT Pro - Advanced")
st.write("Your AI-powered location assistant with free and open-source data.")

# Sidebar with app information
with st.sidebar:
    st.header("About GeoGPT Pro")
    st.write("""
    GeoGPT Pro is an open-source location assistant that uses:
    - OpenStreetMap & Overpass API for location data
    - Open-Meteo for weather information
    - RestCountries for country information
    - spaCy for natural language processing
    
    All APIs used are completely free and don't require API keys.
    """)
    
    st.header("Available Commands")
    st.write("""
    - Ask about weather in any location
    - Find nearby places (restaurants, hospitals, etc.)
    - Calculate distances between locations
    - Get country information
    - Show coordinates of places
    """)

# Display chat history
for message in st.session_state["chat_history"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input field (GPT-style)
user_input = st.chat_input("Ask me anything about locations, weather, or distances...")

if user_input:
    st.session_state["chat_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # Reset map display flag
    st.session_state["show_map"] = False
    
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            # Check for distance query
            if re.search(r'(distance|far|how far)', user_input, re.IGNORECASE):
                response = get_distance(user_input)
            else:
                # Extract locations from user input
                locations = extract_location_from_text(user_input)
                
                # Check for coordinates query
                show_coordinates = "coordinates" in user_input.lower() or "coords" in user_input.lower() or "location of" in user_input.lower()
                
                # Check for place type query (e.g., "hospitals in Paris")
                place_type = None
                place_types = ["hospital", "restaurant", "school", "park", "hotel", "mall", 
                              "cafe", "pharmacy", "bank", "bar", "supermarket", "library"]
                
                for p in place_types:
                    if p in user_input.lower():
                        place_type = p
                        break
                
                if not locations:
                    response = "I couldn't find a location in your query. Try mentioning a city, country, or landmark!"
                else:
                    response = ""
                    for location_name in locations:
                        # Get detailed location info if coordinates are requested
                        if show_coordinates:
                            lat, lon, address = get_location_info(location_name, detailed=True)
                            if lat is None:
                                response += f"Sorry, I couldn't find the location: {location_name}.\n\n"
                            else:
                                response += f"📍 **Location Found:** {location_name}\n"
                                response += f"📌 **Full Address:** {address}\n"
                                response += f"🌐 **Coordinates:** {lat:.6f}, {lon:.6f}\n\n"
                                
                                # Create map for coordinates
                                map_ = folium.Map(location=[lat, lon], zoom_start=14)
                                folium.Marker([lat, lon], popup=location_name, tooltip=location_name,
                                             icon=folium.Icon(color="red", icon="info-sign")).add_to(map_)
                                st.session_state["map_data"] = map_
                                st.session_state["show_map"] = True
                        else:
                            lat, lon = get_location_info(location_name)
                            if lat is None:
                                response += f"Sorry, I couldn't find the location: {location_name}.\n\n"
                            else:
                                response += f"📍 **Location Found:** {location_name}\n\n"
                                
                                # Weather information
                                if "weather" in user_input.lower():
                                    weather_data = get_weather(lat, lon)
                                    if weather_data:
                                        response += (
                                            f"🌦️ **Weather:**\n"
                                            f"- Temperature: {weather_data['Temperature']}\n"
                                            f"- Humidity: {weather_data['Humidity']}\n"
                                            f"- Wind Speed: {weather_data['Wind Speed']}\n"
                                            f"- Conditions: {weather_data['Description']}\n\n"
                                        )
                                    
                                    # Create basic map for weather
                                    map_ = folium.Map(location=[lat, lon], zoom_start=12)
                                    folium.Marker([lat, lon], popup=location_name, tooltip=location_name,
                                                 icon=folium.Icon(color="red", icon="info-sign")).add_to(map_)
                                    st.session_state["map_data"] = map_
                                    st.session_state["show_map"] = True
                                
                                # Country information
                                if "country" in user_input.lower() or "information" in user_input.lower():
                                    country_data = get_country_info(location_name)
                                    if country_data:
                                        response += (
                                            f"🏛️ **Country Information:**\n"
                                            f"- Capital: {country_data['Capital']}\n"
                                            f"- Population: {country_data['Population']}\n"
                                            f"- Region: {country_data['Region']}\n"
                                            f"- Languages: {country_data['Languages']}\n"
                                            f"- Currency: {country_data['Currency']}\n\n"
                                        )
                                
                                # If place type specified, find and show places
                                if place_type:
                                    places = get_nearby_places(lat, lon, place_type, radius=10000, num_places=15)
                                    if places:
                                        response += f"🏥 **{place_type.capitalize()}s in {location_name}:**\n"
                                        for i, place in enumerate(places, 1):
                                            place_name = place.get('tags', {}).get('name', f"Unnamed {place_type}")
                                            response += f"{i}. {place_name}\n"
                                        response += "\n"
                                        
                                        # Create map with places
                                        map_ = folium.Map(location=[lat, lon], zoom_start=12)
                                        
                                        # Add main location marker
                                        folium.Marker([lat, lon], popup=location_name, tooltip=location_name,
                                                     icon=folium.Icon(color="red", icon="info-sign")).add_to(map_)
                                        
                                        # Add cluster for place markers
                                        marker_cluster = MarkerCluster().add_to(map_)
                                        
                                        # Add markers for places
                                        for place in places:
                                            try:
                                                place_lat = place.get("lat") / 1e7
                                                place_lon = place.get("lon") / 1e7
                                                place_name = place.get('tags', {}).get('name', f"Unnamed {place_type}")
                                                
                                                folium.Marker(
                                                    [place_lat, place_lon],
                                                    popup=place_name,
                                                    tooltip=place_name,
                                                    icon=folium.Icon(color="blue", icon="plus")
                                                ).add_to(marker_cluster)
                                            except (KeyError, TypeError):
                                                continue
                                        
                                        st.session_state["map_data"] = map_
                                        st.session_state["show_map"] = True
                                    else:
                                        response += f"⚠️ No {place_type}s found in {location_name}.\n\n"

            # Display assistant response
            st.markdown(response)
            st.session_state["chat_history"].append({"role": "assistant", "content": response})
            
            # Display map only if needed
            if st.session_state["show_map"] and st.session_state["map_data"]:
                st.subheader("🗺️ Interactive Map")
                st_folium(st.session_state["map_data"], width=800, height=500)
                

