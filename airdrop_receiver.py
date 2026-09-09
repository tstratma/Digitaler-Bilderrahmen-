#!/usr/bin/env python3
"""
Digitaler Bilderrahmen - Empfaenger fuer neue Bilder ("Eingangs-Watcher")

WICHTIG - ehrliche Einordnung zu AirDrop:
---------------------------------------------------------------------------
Echtes Apple-AirDrop ist ein proprietaeres Protokoll (AWDL) und laeuft NICHT
einfach auf einem Raspberry Pi. Es benoetigt:
  * einen WLAN-Adapter im Monitor-Mode mit Frame-Injection (die interne
    Pi-4-WLAN-Karte nur mit Nexmon-Firmware-Patches),
  * den 'owl'-Daemon (Open Wireless Link) als root fuer das awdl0-Interface,
  * das reverse-engineerte 'opendrop'-Tool von seemoo-lab.
Das ist fragil, blockiert waehrenddessen das normale WLAN und ist fuer einen
Bilderrahmen im Alltag nicht praktikabel.

DESHALB ist der zuverlaessige Weg vom iPhone: das Web-Interface
(http://<Pi>:8080) - dort Bilder direkt aus der Fotos-App hochladen.
Tipp: Im Safari "Zum Home-Bildschirm" hinzufuegen -> fuehlt sich an wie eine App.

Dieses Skript ueberwacht zusaetzlich ein Eingangs-Verzeichnis ("incoming/").
Alles, was dort landet (per SMB/Dateien-App, scp, USB-Stick, ...), wird
automatisch in die Diashow uebernommen - inkl. HEIC->JPEG-Umwandlung.
---------------------------------------------------------------------------
"""

import os
import sys
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import image_utils

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [receiver] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("receiver")


def signal_slideshow_reload():
    """Sendet ein Signal an die Diashow, die Bilderliste neu zu laden."""
    try:
        with open(config.RELOAD_SIGNAL_FILE, "w") as f:
            f.write(str(time.time()))
        logger.info("Reload-Signal an Diashow gesendet.")
    except Exception as e:
        logger.warning("Konnte Reload-Signal nicht senden: %s", e)


def is_supported_upload(filename) -> bool:
    """Prueft ob die Dateiendung akzeptiert wird (inkl. HEIC)."""
    return Path(filename).suffix.lower() in config.UPLOAD_EXTENSIONS


def unique_dest(name: str) -> Path:
    """Erzeugt einen kollisionsfreien Zielpfad im Bilder-Verzeichnis."""
    dest = Path(config.IMAGES_DIR) / name
    if dest.exists():
        stem, suffix = Path(name).stem, Path(name).suffix
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = Path(config.IMAGES_DIR) / f"{stem}_{ts}{suffix}"
    return dest


def import_file(source_path, original_name=None):
    """
    Uebernimmt eine Datei ins Bilder-Verzeichnis (mit HEIC-Umwandlung).
    Gibt den Zielpfad zurueck oder None bei Fehler/nicht unterstuetzt.
    """
    os.makedirs(config.IMAGES_DIR, exist_ok=True)
    source_path = Path(source_path)
    original_name = original_name or source_path.name

    if not is_supported_upload(original_name):
        logger.warning("Unerlaubte Dateiendung: %s", original_name)
        return None

    dest = unique_dest(original_name)
    try:
        shutil.copy2(str(source_path), str(dest))
    except Exception as e:
        logger.error("Fehler beim Kopieren von %s: %s", original_name, e)
        return None

    # iPhone-HEIC/HEIF -> JPEG (sonst kann die Diashow es nicht anzeigen)
    if image_utils.is_heic(dest):
        converted = image_utils.normalize_image(dest)
        if converted is None:
            logger.warning(
                "HEIC nicht umgewandelt (pillow-heif fehlt?): %s", dest.name
            )
            return None
        dest = Path(converted)

    logger.info("Bild uebernommen: %s", dest.name)
    signal_slideshow_reload()
    return str(dest)


def _wait_until_stable(filepath, checks=2, delay=1.0):
    """Wartet, bis die Dateigroesse stabil ist (Upload abgeschlossen)."""
    last = -1
    stable = 0
    for _ in range(30):  # max. ~30s
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return False
        if size == last and size > 0:
            stable += 1
            if stable >= checks:
                return True
        else:
            stable = 0
            last = size
        time.sleep(delay)
    return True  # Timeout: trotzdem versuchen


def run_incoming_watcher():
    """
    Ueberwacht das Eingangs-Verzeichnis 'incoming/' und uebernimmt neue
    Bilder automatisch in die Diashow.
    """
    watch_dir = os.path.join(os.path.dirname(config.IMAGES_DIR), "incoming")
    os.makedirs(watch_dir, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Eingangs-Watcher aktiv.")
    logger.info("Ueberwachtes Verzeichnis: %s", watch_dir)
    logger.info("Dateien hierher kopieren (SMB/Dateien-App, scp, ...) ->")
    logger.info("werden automatisch in die Diashow uebernommen.")
    if not image_utils.heic_supported():
        logger.warning(
            "HEIC-Unterstuetzung fehlt (pillow-heif nicht installiert). "
            "iPhone-Fotos ggf. als JPEG senden oder pillow-heif installieren."
        )
    logger.info("=" * 60)

    known = set(os.listdir(watch_dir))
    running = True

    while running:
        try:
            current = set(os.listdir(watch_dir))
            new_files = current - known

            for filename in sorted(new_files):
                filepath = os.path.join(watch_dir, filename)
                if not os.path.isfile(filepath):
                    continue
                if not is_supported_upload(filename):
                    logger.info("Ignoriere (Format): %s", filename)
                    continue

                logger.info("Neue Datei entdeckt: %s", filename)
                if not _wait_until_stable(filepath):
                    continue

                if import_file(filepath, filename):
                    try:
                        os.remove(filepath)
                        logger.info("Quelldatei entfernt: %s", filename)
                    except OSError:
                        pass

            known = set(os.listdir(watch_dir))
            time.sleep(3)

        except KeyboardInterrupt:
            running = False
        except Exception as e:
            logger.error("Fehler im Eingangs-Watcher: %s", e)
            time.sleep(5)


def main():
    os.makedirs(config.IMAGES_DIR, exist_ok=True)

    logger.info("Digitaler Bilderrahmen - Eingangs-Watcher")
    logger.info("Bilder-Verzeichnis: %s", config.IMAGES_DIR)

    try:
        run_incoming_watcher()
    except KeyboardInterrupt:
        logger.info("Watcher durch Benutzer gestoppt.")
    except Exception as e:
        logger.exception("Schwerwiegender Fehler: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
