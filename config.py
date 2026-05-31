"""
Zentrale Konfiguration fuer den Digitalen Bilderrahmen
"""
import os

# Basis-Verzeichnis
BASE_DIR = "/home/pi/Digitaler-Bilderrahmen"

# Bilder-Verzeichnis
IMAGES_DIR = os.path.join(BASE_DIR, "images")

# Versteckte Bilder (Dateiname -> True/False)
HIDDEN_IMAGES_FILE = os.path.join(BASE_DIR, "hidden_images.json")

# Reihenfolge-Datei
ORDER_FILE = os.path.join(BASE_DIR, "image_order.json")

# Intervall-Datei (fuer dynamische Aenderung)
INTERVAL_FILE = os.path.join(BASE_DIR, ".interval")

# Diashow-Einstellungen
DEFAULT_INTERVAL = 300   # Sekunden (5 Minuten)
SLIDESHOW_INTERVAL = DEFAULT_INTERVAL
TRANSITION_DURATION = 1.0  # Sekunden fuer Ueberblendung

# Web-Interface
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080
WEB_SECRET_KEY = "bilderrahmen-secret-2024"

# AirDrop
AIRDROP_SAVE_DIR = IMAGES_DIR

# Erlaubte Bildformate
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}

# Maximale Upload-Groesse (in Bytes): 50 MB
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

# Reload-Signal-Datei (slideshow prueft diese Datei)
RELOAD_SIGNAL_FILE = os.path.join(BASE_DIR, ".reload_signal")

# Log-Datei
LOG_FILE = os.path.join(BASE_DIR, "bilderrahmen.log")

# Display-Einstellungen
DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080
FULLSCREEN = True
SHOW_FILENAME = True
FILENAME_DISPLAY_DURATION = 3  # Sekunden


def get_interval():
    """Aktuelles Intervall aus Datei lesen."""
    try:
        if os.path.exists(INTERVAL_FILE):
            with open(INTERVAL_FILE, "r") as f:
                val = int(f.read().strip())
                if val > 0:
                    return val
    except (ValueError, IOError):
        pass
    return DEFAULT_INTERVAL


def set_interval(seconds: int):
    """Intervall in Datei speichern."""
    with open(INTERVAL_FILE, "w") as f:
        f.write(str(int(seconds)))
