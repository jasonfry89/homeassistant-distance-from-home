"""Constants for the Distance from Home integration."""

from datetime import timedelta

DOMAIN = "distance_from_home"

SUBENTRY_TYPE_LOCATION = "location"

CONF_PLACE_ID = "place_id"

MODE_DRIVING = "driving"
MODE_WALKING = "walking"
MODE_BICYCLING = "biking"
MODE_TRANSIT = "transit"

TRAVEL_MODES = [MODE_DRIVING, MODE_WALKING, MODE_BICYCLING, MODE_TRANSIT]

TRAVEL_MODE_TO_API = {
    MODE_DRIVING: "DRIVE",
    MODE_WALKING: "WALK",
    MODE_BICYCLING: "BICYCLE",
    MODE_TRANSIT: "TRANSIT",
}

UPDATE_INTERVAL = timedelta(days=7)
