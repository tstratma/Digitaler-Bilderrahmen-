"""
Zentrale Konfiguration fuer den Digitalen Bilderrahmen
"""
import os
import sys
import logging

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

# Bildformate, die die Diashow (pygame) direkt anzeigen kann.
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}

# Formate, die beim Upload/Empfang zusaetzlich akzeptiert werden.
# iPhone-Fotos sind standardmaessig HEIC/HEIF und werden nach dem
# Empfang automatisch in JPEG umgewandelt (siehe image_utils.py).
UPLOAD_EXTENSIONS = ALLOWED_EXTENSIONS | {".heic", ".heif"}

# Maximale Upload-Groesse (in Bytes): 50 MB
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

# Reload-Signal-Datei (slideshow prueft diese Datei)
RELOAD_SIGNAL_FILE = os.path.join(BASE_DIR, ".reload_signal")

# Log-Datei
LOG_FILE = os.path.join(BASE_DIR, "bilderrahmen.log")

# Einstellungs-Datei (Zufall, Ueberblendung ...)
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

# Standard-Einstellungen
DEFAULT_SHUFFLE = False      # Bilder in zufaelliger Reihenfolge zeigen
DEFAULT_TRANSITION = True    # Weiche Ueberblendung beim Wechsel

# Nachtruhe: Display nachts abschalten (Strom sparen)
DEFAULT_SLEEP_ENABLED = False
DEFAULT_SLEEP_START = "22:00"   # ab dieser Uhrzeit Display aus
DEFAULT_SLEEP_END = "07:00"     # ab dieser Uhrzeit Display wieder an

# Display-Einstellungen
DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 1080
FULLSCREEN = True
SHOW_FILENAME = False  # Dateiname im Bild einblenden (fuer Bilderrahmen meist unerwuenscht)
FILENAME_DISPLAY_DURATION = 3  # Sekunden


def build_log_handlers(tag=""):
    """
    Erstellt Logging-Handler. Schreibt nach Moeglichkeit in die Log-Datei,
    faellt aber robust auf reines Konsolen-Logging zurueck, wenn die Datei
    nicht beschreibbar ist (z. B. falsche Dateirechte) - die App soll
    deswegen NICHT abstuerzen.
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        d = os.path.dirname(LOG_FILE)
        if d:
            os.makedirs(d, exist_ok=True)
        handlers.insert(0, logging.FileHandler(LOG_FILE))
    except OSError as e:
        sys.stderr.write(
            f"[WARN]{(' ' + tag) if tag else ''} Log-Datei nicht beschreibbar "
            f"({LOG_FILE}): {e}. Logge nur auf die Konsole.\n"
        )
    return handlers


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


def get_settings():
    """Alle Einstellungen als dict lesen (mit Standardwerten)."""
    import json
    settings = {
        "shuffle": DEFAULT_SHUFFLE,
        "transition": DEFAULT_TRANSITION,
        "sleep_enabled": DEFAULT_SLEEP_ENABLED,
        "sleep_start": DEFAULT_SLEEP_START,
        "sleep_end": DEFAULT_SLEEP_END,
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                settings.update({k: data[k] for k in settings if k in data})
    except (ValueError, IOError):
        pass
    return settings


def set_setting(key: str, value):
    """Eine Einstellung setzen und speichern."""
    import json
    settings = get_settings()
    settings[key] = value
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
    return settings
