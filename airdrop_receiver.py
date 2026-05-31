#!/usr/bin/env python3
"""
Digitaler Bilderrahmen - AirDrop-Empfaenger
Empfaengt Bilder via AirDrop (opendrop) und speichert sie im Bilder-Verzeichnis.
"""

import os
import sys
import time
import shutil
import logging
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# Logging einrichten
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [airdrop] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("airdrop")


def signal_slideshow_reload():
    """Sendet ein Signal an die Diashow, die Bilderliste neu zu laden."""
    try:
        with open(config.RELOAD_SIGNAL_FILE, "w") as f:
            f.write(str(time.time()))
        logger.info("Reload-Signal an Diashow gesendet.")
    except Exception as e:
        logger.warning("Konnte Reload-Signal nicht senden: %s", e)


def is_allowed_extension(filename):
    """Prueft ob die Dateiendung erlaubt ist."""
    ext = Path(filename).suffix.lower()
    return ext in config.ALLOWED_EXTENSIONS


def save_received_file(source_path, original_name=None):
    """
    Speichert eine empfangene Datei ins Bilder-Verzeichnis.
    Gibt den Zielpfad zurueck oder None bei Fehler.
    """
    os.makedirs(config.IMAGES_DIR, exist_ok=True)

    if original_name is None:
        original_name = Path(source_path).name

    if not is_allowed_extension(original_name):
        logger.warning("Unerlaubte Dateiendung: %s", original_name)
        return None

    # Eindeutigen Dateinamen erstellen falls bereits vorhanden
    dest_path = Path(config.IMAGES_DIR) / original_name
    if dest_path.exists():
        stem = Path(original_name).stem
        suffix = Path(original_name).suffix
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = f"{stem}_{timestamp}{suffix}"
        dest_path = Path(config.IMAGES_DIR) / original_name

    try:
        shutil.copy2(str(source_path), str(dest_path))
        logger.info("Bild gespeichert: %s", dest_path)
        signal_slideshow_reload()
        return str(dest_path)
    except Exception as e:
        logger.error("Fehler beim Speichern: %s", e)
        return None


class OpenDropReceiver:
    """Wrapper fuer die opendrop-Bibliothek."""

    def __init__(self):
        self.running = False
        self.opendrop_available = self._check_opendrop()

    def _check_opendrop(self):
        """Prueft ob opendrop verfuegbar ist."""
        try:
            import opendrop  # noqa: F401
            logger.info("opendrop-Bibliothek gefunden.")
            return True
        except ImportError:
            logger.warning(
                "opendrop nicht gefunden. Installieren mit: pip3 install opendrop\n"
                "Fallback-Verzeichnis-Watcher wird verwendet."
            )
            return False

    def start(self):
        """Startet den AirDrop-Empfaenger."""
        if not self.opendrop_available:
            self._run_fallback_watcher()
            return

        self.running = True
        logger.info("Starte AirDrop-Empfaenger (opendrop)...")

        try:
            self._run_opendrop()
        except Exception as e:
            logger.error("AirDrop-Fehler: %s", e)
            logger.info("Starte Fallback-Datei-Watcher...")
            self._run_fallback_watcher()

    def _run_opendrop(self):
        """Startet den echten opendrop-Empfaenger."""
        # opendrop API kann je nach Version leicht abweichen
        # Unterstuetzt wird: opendrop >= 3.0
        try:
            import asyncio
            from opendrop.server import OpenDropServer

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def run_server():
                server = OpenDropServer()

                async def on_receive(request):
                    logger.info(
                        "AirDrop-Empfang: %d Datei(en)", len(request.files)
                    )
                    for file_info in request.files:
                        tmp_path = file_info.data
                        name = file_info.name or Path(tmp_path).name
                        result = save_received_file(tmp_path, name)
                        if result:
                            logger.info("Gespeichert: %s", result)

                server.on_receive = on_receive
                await server.start()
                logger.info("AirDrop-Server laeuft. Geraetename: Bilderrahmen")

                while self.running:
                    await asyncio.sleep(1)

                await server.stop()

            loop.run_until_complete(run_server())

        except (ImportError, AttributeError):
            # Aeltere opendrop-API (synchron)
            logger.info("Versuche aeltere opendrop-API...")
            from opendrop import OpenDrop

            od = OpenDrop(
                server_name="Bilderrahmen",
                server_model="Raspberry Pi",
            )

            def file_received(sender_name, file_path):
                logger.info("Empfangen von %s: %s", sender_name, file_path)
                save_received_file(file_path)

            od.run(callback=file_received)

    def _run_fallback_watcher(self):
        """
        Fallback: Ueberwacht ein Eingangsverzeichnis auf neue Dateien.
        Nuetzlich wenn opendrop nicht verfuegbar ist oder nicht funktioniert.
        """
        watch_dir = os.path.join(os.path.dirname(config.IMAGES_DIR), "incoming")
        os.makedirs(watch_dir, exist_ok=True)

        logger.info("Fallback-Watcher aktiv.")
        logger.info("Ueberwachtes Verzeichnis: %s", watch_dir)
        logger.info(
            "Dateien in dieses Verzeichnis kopieren, um sie hinzuzufuegen."
        )

        known_files = set(os.listdir(watch_dir))
        self.running = True

        while self.running:
            try:
                current_files = set(os.listdir(watch_dir))
                new_files = current_files - known_files

                for filename in sorted(new_files):
                    filepath = os.path.join(watch_dir, filename)
                    if os.path.isfile(filepath) and is_allowed_extension(filename):
                        logger.info("Neue Datei entdeckt: %s", filename)
                        # Kurz warten bis Datei vollstaendig geschrieben ist
                        time.sleep(2)
                        result = save_received_file(filepath, filename)
                        if result:
                            try:
                                os.remove(filepath)
                                logger.info("Quelldatei entfernt: %s", filepath)
                            except Exception:
                                pass

                known_files = set(os.listdir(watch_dir))
                time.sleep(3)

            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                logger.error("Fehler im Fallback-Watcher: %s", e)
                time.sleep(5)

    def stop(self):
        """Stoppt den AirDrop-Empfaenger."""
        self.running = False
        logger.info("AirDrop-Empfaenger gestoppt.")


def main():
    """Hauptfunktion."""
    os.makedirs(config.IMAGES_DIR, exist_ok=True)

    logger.info("=" * 55)
    logger.info("Digitaler Bilderrahmen - AirDrop-Empfaenger")
    logger.info("Bilder-Verzeichnis: %s", config.IMAGES_DIR)
    logger.info("=" * 55)

    receiver = OpenDropReceiver()

    try:
        receiver.start()
    except KeyboardInterrupt:
        logger.info("AirDrop-Empfaenger durch Benutzer gestoppt.")
        receiver.stop()
    except Exception as e:
        logger.exception("Schwerwiegender Fehler: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
