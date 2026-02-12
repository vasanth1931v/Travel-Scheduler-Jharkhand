import urllib.parse
import webbrowser
import requests
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim, ArcGIS
from geopy.extra.rate_limiter import RateLimiter

# --- Config ---
USER_AGENT = "trip-planner-example"

# --- Cities and places ---
cities = {
    "1": ("Ranchi", ["Hundru Falls", "Dassam Falls", "Ranchi Lake and Rock Garden", "Tagore Hill"]),
    "2": ("Jamshedpur", ["Jubilee Park", "Tata Steel Zoological Park", "HUDCO Lake"]),
    "3": ("Deoghar",
          ["Satsang Ashram", "Harila Jori", "Trikut Parvat", "Shree Baba Baidyanath Jyotirlinga Mandir Deoghar"]),
    "4": ("Dhanbad",
          ["Birsa Munda Park", "Topchanchi Lake", "Panchet Dam", "Indian Institute of Technology(IIT)Dhanbad - ISM"])
}

# --- Best time to visit mapping (manual tourism knowledge) ---
best_time_dict = {
    "Hundru Falls": "July – September (monsoon for waterfall view)",
    "Dassam Falls": "July – September",
    "Ranchi Lake and Rock Garden": "October – February",
    "Tagore Hill": "October – March",
    "Jubilee Park": "October – March (pleasant weather)",
    "Tata Steel Zoological Park": "November – February",
    "HUDCO Lake": "October – February",
    "Satsang Ashram": "October – March",
    "Harila Jori": "October – March",
    "Trikut Parvat": "October – March",
    "Shree Baba Baidyanath Jyotirlinga Mandir Deoghar": "July (Shravani Mela) or October – March",
    "Birsa Munda Park": "October – February",
    "Topchanchi Lake": "October – March",
    "Panchet Dam": "November – February",
    "Indian Institute of Technology(IIT)Dhanbad - ISM": "October – February"
}


# --- Helpers ---
def geocode_address(address):
    """Geocode address with fallback (Nominatim → ArcGIS)."""
    nom = Nominatim(user_agent=USER_AGENT, timeout=10)
    nom_geocode = RateLimiter(nom.geocode, min_delay_seconds=1, max_retries=2)
    arcgis = ArcGIS(timeout=10)

    try:
        r = nom_geocode(address)
        if r:
            return (r.latitude, r.longitude, r.address)
    except:
        pass

    try:
        r2 = arcgis.geocode(address)
        if r2:
            return (r2.latitude, r2.longitude, r2.address)
    except:
        pass

    return None


def geocode_city(city_name):
    """Get city bounding box from Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1, "addressdetails": 1}
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, params=params, headers=headers).json()
    if not r:
        return None
    item = r[0]
    bbox = [float(x) for x in item["boundingbox"]]  # [south, north, west, east]
    return {"lat": float(item["lat"]), "lon": float(item["lon"]), "bbox": bbox}


def inside_city(lat, lon, bbox):
    """Check if lat/lon is inside city bounding box."""
    south, north, west, east = bbox
    return south <= lat <= north and west <= lon <= east


def get_valid_location(prompt, city_name, city_bbox):
    """Ask user for location, ensure it's inside the city bounding box (strict)."""
    address = input(prompt).strip()
    loc = geocode_address(f"{address}, {city_name}, India")
    if not loc:
        print("Please enter correct start and end position")
        exit()
    lat, lon, full = loc
    if not inside_city(lat, lon, city_bbox):
        print("Please enter correct start and end position")
        exit()
    return (lat, lon, full)


def get_travel_time_minutes(origin, destination):
    """Fetch driving travel time in minutes using OSRM (OpenStreetMap routing)."""
    url = f"http://router.project-osrm.org/route/v1/driving/{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    params = {"overview": "false"}
    try:
        response = requests.get(url, params=params).json()
        if "routes" in response and response["routes"]:
            duration_sec = response["routes"][0]["duration"]
            return int(duration_sec // 60)  # seconds → minutes
    except Exception as e:
        print("⚠️ Error fetching OSRM travel time, defaulting to 25 min:", e)
    return 25


def build_maps_url(start, ordered_places, return_place=None):
    """Build one Google Maps URL following strict order (no API needed)."""
    origin = f"{start[0]},{start[1]}"
    dest = f"{return_place[0]},{return_place[1]}" if return_place else f"{ordered_places[-1][0]},{ordered_places[-1][1]}"
    waypoints = "|".join(f"{lat},{lon}" for lat, lon in ordered_places)
    params = {
        "api": "1",
        "origin": origin,
        "destination": dest,
        "travelmode": "driving",
        "waypoints": waypoints if waypoints else ""
    }
    qs = "&".join(f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in params.items() if v)
    return f"https://www.google.com/maps/dir/?{qs}"


# --- Weather Fetch ---
def get_weather(lat, lon):
    """Fetch current weather using Open-Meteo API (no key required)."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true"
    }
    try:
        r = requests.get(url, params=params).json()
        if "current_weather" in r:
            return r["current_weather"]
    except Exception as e:
        print("⚠️ Weather fetch error:", e)
    return None


def get_suggestion(weather):
    if not weather:
        return "No weather data available."

    temp = weather["temperature"]
    code = weather["weathercode"]

    if code in [61, 63, 65, 80, 81, 82]:  # rainy codes
        return "🌧️ It's rainy — carry an umbrella or raincoat."
    elif temp > 30:
        return "☀️ It's warm — carry sunscreen, sunglasses, and a water bottle."
    elif temp < 15:
        return "🧥 It's cool — carry a light jacket."
    else:
        return "😊 Weather looks pleasant — enjoy your trip!"


def get_best_time(place_name):
    """Get best time to visit a place from dictionary."""
    for key in best_time_dict:
        if key.lower() in place_name.lower():
            return best_time_dict[key]
    return "Information not available."


# --- Main ---
def main():
    print("=== The Jharkhand Guide 🚗 ===\n")

    # Choose city
    for k, (name, _) in cities.items():
        print(f"{k}. {name}")
    city_choice = input("Enter city number (1-4): ").strip()
    if city_choice not in cities:
        print("Invalid choice. Exiting.")
        return
    city_name, place_list = cities[city_choice]

    # Get city bounding box
    city_info = geocode_city(f"{city_name}, India")
    if not city_info:
        print("Could not verify city. Exiting.")
        return
    city_bbox = city_info["bbox"]

    # Select places
    print(f"\nPlaces in {city_name}:")
    for idx, p in enumerate(place_list, start=1):
        print(f"{idx}. {p}")
    raw = input("\nEnter place numbers (comma-separated): ").strip()
    selected_idxs = [int(t) - 1 for t in raw.split(",") if t.strip().isdigit() and 1 <= int(t) <= len(place_list)]
    if not selected_idxs:
        print("No valid places. Exiting.")
        return
    selected_places = [f"{place_list[i]}, {city_name}, Jharkhand, India" for i in sorted(set(selected_idxs))]

    # Start address
    user_lat, user_lon, user_full = get_valid_location(
        f"\nEnter your starting address in {city_name}: ",
        city_name,
        city_bbox
    )

    # Times
    start_time_str = input("\nEnter trip start time (HH:MM - 24 hr format): ").strip()
    current_time = datetime.strptime(start_time_str, "%H:%M")
    end_time_str = input("Enter desired finish time (HH:MM - 24 hr format):  ").strip()
    desired_end_time = datetime.strptime(end_time_str, "%H:%M").time()

    # Return address
    return_lat, return_lon, return_full = get_valid_location(
        f"\nEnter your return location in {city_name}: ",
        city_name,
        city_bbox
    )

    # Geocode selected places
    resolved_places, place_labels, stay_times = [], [], []
    for place in selected_places:
        coords = geocode_address(place)
        if coords:  # ✅ accept outskirts too
            resolved_places.append((coords[0], coords[1]))
            place_labels.append(place)
            mins = int(input(f"Minutes to stay at {place}: "))
            stay_times.append(mins)
        else:
            print(f"Error: Could not find {place}. Exiting.")
            return

    if not resolved_places:
        print("No valid places. Exiting.")
        return

    # Track totals
    total_travel_time = 0
    total_stay_time = 0

    # Trip schedule
    print("\n--- Trip Schedule ---")
    print(f"Start from {user_full} at {current_time.strftime('%H:%M')}")

    last_point = (user_lat, user_lon)
    for i, (coords, label, stay) in enumerate(zip(resolved_places, place_labels, stay_times), 1):
        travel_time = get_travel_time_minutes(last_point, coords)
        total_travel_time += travel_time
        total_stay_time += stay

        current_time += timedelta(minutes=travel_time)
        arrival = current_time.strftime("%H:%M")
        leave = (current_time + timedelta(minutes=stay)).strftime("%H:%M")

        print(f"\n{i}. {label}")
        print(f"   → Travel {travel_time} min, arrive at {arrival}")
        print(f"   → Stay {stay} min")
        print(f"   → Leave by {leave}")

        current_time += timedelta(minutes=stay)
        last_point = coords

    # Return
    travel_back = get_travel_time_minutes(last_point, (return_lat, return_lon))

    total_travel_time += travel_back
    current_time += timedelta(minutes=travel_back)

    print(f"\nReturn to {return_full} at {current_time.strftime('%H:%M')} (travel {travel_back} min)")

    if current_time.time() > desired_end_time:
        print("\n❌ Please limit the places or the time to stay, in order to reach your final destination in time.")
        return

    # ✅ If within time, continue
    print("\n✅ You will return before your desired finish time.")

    # Show totals
    total_time_spent = total_travel_time + total_stay_time
    print(f"\n📊 Trip Summary:")
    print(f"   • Total travel time: {total_travel_time} min")
    print(f"   • Total stay time:   {total_stay_time} min")
    print(f"   • Total time spent:  {total_time_spent} min")

    # --- Weather & Suggestions ---
    print("\n🌦️ Weather and Suggestions:")
    for coords, label in zip(resolved_places, place_labels):
        weather = get_weather(coords[0], coords[1])
        best_time = get_best_time(label)
        if weather:
            temp = weather['temperature']
            wind = weather['windspeed']
            desc = get_suggestion(weather)
            print(f"\n{label}:")
            print(f"   • Temperature: {temp}°C")
            print(f"   • Windspeed:   {wind} km/h")
            print(f"   • Suggestion:  {desc}")
            print(f"   • Best time to visit: {best_time}")
        else:
            print(f"\n{label}: Weather data not available.")
            print(f"   • Best time to visit: {best_time}")

    # Open Google Maps
    if input("\nOpen route in Google Maps? (y/n): ").strip().lower() == "y":
        url = build_maps_url((user_lat, user_lon), resolved_places, (return_lat, return_lon))
        webbrowser.open(url, new=2)

    print("\n✅ Trip finished. Enjoy your journey!")


if __name__ == "__main__":
    main()
