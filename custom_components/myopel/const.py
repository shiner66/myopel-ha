"""Constants for MyOpel integration."""

DOMAIN = "myopel"

# File polling
DEFAULT_SCAN_INTERVAL = 300  # seconds

# Config keys
CONF_FILE_PATH = "file_path"
CONF_SCAN_INTERVAL = "scan_interval"

# IMAP keys
CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_IMAP_USERNAME = "imap_username"
CONF_IMAP_PASSWORD = "imap_password"
CONF_IMAP_FOLDER = "imap_folder"
CONF_IMAP_SENDER = "imap_sender"
CONF_IMAP_INTERVAL = "imap_interval"
CONF_IMAP_DISABLED = "imap_disabled"

DEFAULT_IMAP_PORT = 993
DEFAULT_IMAP_FOLDER = "INBOX"
DEFAULT_IMAP_INTERVAL = 300  # seconds

# Min distance filter
CONF_MIN_TRIP_DISTANCE = "min_trip_distance"
CONF_MIN_TRIP_DISTANCE_ENABLED = "min_trip_distance_enabled"
DEFAULT_MIN_TRIP_DISTANCE = 1.0  # km
