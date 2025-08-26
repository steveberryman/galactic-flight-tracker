# SECRETS.py - Configuration file for Galactic Unicorn Plane Tracker
# Keep this file secure and don't commit it to version control!

# WiFi Configuration
WIFI_SSID = ""
WIFI_PASSWORD = ""

# Location Configuration
# Find your coordinates using Google Maps (right-click and select coordinates)
# or use a GPS app on your phone
HOME_LAT = 0.0000 # Your latitude (example: London)
HOME_LON = 0.0000  # Your longitude (example: London)

# Search Configuration
SEARCH_RADIUS_KM = 15  # Radius in km to search for planes

# OpenSky API Configuration (Optional)
# Create free account at https://opensky-network.org/ for increased limits
OPENSKY_USERNAME = ""  # Your OpenSky username (optional)
OPENSKY_PASSWORD = ""  # Your OpenSky password (optional)

# Option 2: OAuth Client Credentials (Recommended)
OPENSKY_CLIENT_ID = ""     # Your OAuth client ID
OPENSKY_CLIENT_SECRET = "" # Your OAuth client secret

# Display Configuration
API_UPDATE_INTERVAL = 15    # Seconds between API calls
DISPLAY_UPDATE_INTERVAL = 0.1  # Seconds between display updates

# Advanced Configuration
ALTITUDE_FILTER_MIN = 0     # Minimum altitude in meters (0 = no filter)
ALTITUDE_FILTER_MAX = 15000 # Maximum altitude in meters (15000m ≈ 50,000ft)
SHOW_GROUND_AIRCRAFT = False # Show aircraft on the ground
GITHUB_LOGOS_RAW_BASE = "https://raw.githubusercontent.com/steveberryman/galactic-flight-tracker/main/logos"
GITHUB_LOGOS_API_URL = "https://api.github.com/repos/steveberryman/galactic-flight-tracker/contents/logos"
GITHUB_TOKEN = ""
LOGOS_SYNC_INTERVAL = 3600
