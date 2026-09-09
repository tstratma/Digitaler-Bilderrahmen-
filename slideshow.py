#!/usr/bin/env python3
"""
Digitaler Bilderrahmen - Diashow
Vollbild-Diashow mit pygame, wechselt alle 5 Minuten das Bild.
"""

import os
import sys
import time
import json
import random
import logging
import subprocess
import pygame
import threading
from datetime import datetime
from pathlib import Path

# Pfad fuer lokale Imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [slideshow] %(levelname)s: %(message)s",
    handlers=config.build_log_handlers("slideshow"),
)
logger = logging.getLogger("slideshow")


def load_image_list(shuffle=False):
    """Laedt und sortiert die Liste der anzuzeigenden Bilder."""
    images_dir = Path(config.IMAGES_DIR)
    if not images_dir.exists():
        return []

    # Versteckte Bilder laden
    hidden = set()
    if os.path.exists(config.HIDDEN_IMAGES_FILE):
        try:
            with open(config.HIDDEN_IMAGES_FILE) as f:
                hidden_data = json.load(f)
                hidden = {k for k, v in hidden_data.items() if v}
        except Exception:
            pass

    # Benutzerdefinierte Reihenfolge laden
    custom_order = []
    if os.path.exists(config.ORDER_FILE):
        try:
            with open(config.ORDER_FILE) as f:
                custom_order = json.load(f)
        except Exception:
            pass

    # Alle Bilder einlesen
    all_images = []
    for ext in config.ALLOWED_EXTENSIONS:
        all_images.extend(images_dir.glob(f"*{ext}"))
        all_images.extend(images_dir.glob(f"*{ext.upper()}"))

    # Duplikate entfernen (glob auf case-insensitiven Systemen)
    seen = set()
    unique_images = []
    for img in all_images:
        if img.resolve() not in seen:
            seen.add(img.resolve())
            unique_images.append(img)
    all_images = unique_images

    # Nur Dateinamen (ohne Pfad) fuer Vergleiche
    image_names = {img.name: img for img in all_images}

    # Gefilterte und sortierte Liste erstellen
    result = []

    # Zuerst Bilder in benutzerdefinierter Reihenfolge
    for name in custom_order:
        if name in image_names and name not in hidden:
            result.append(image_names[name])

    # Dann alle restlichen Bilder alphabetisch
    result_paths = set(result)
    remaining = sorted(
        [img for name, img in image_names.items()
         if name not in hidden and img not in result_paths],
        key=lambda x: x.name.lower()
    )
    result.extend(remaining)

    if shuffle:
        random.shuffle(result)

    return result


def scale_image_to_screen(surface, screen_width, screen_height):
    """Skaliert ein Bild auf Bildschirmgroesse (letterbox/pillarbox)."""
    img_width, img_height = surface.get_size()
    img_ratio = img_width / img_height
    screen_ratio = screen_width / screen_height

    if img_ratio > screen_ratio:
        # Bild ist breiter -> an Breite anpassen
        new_width = screen_width
        new_height = int(screen_width / img_ratio)
    else:
        # Bild ist hoeher -> an Hoehe anpassen
        new_height = screen_height
        new_width = int(screen_height * img_ratio)

    scaled = pygame.transform.smoothscale(surface, (new_width, new_height))
    return scaled


class Slideshow:
    def __init__(self):
        os.environ.setdefault("DISPLAY", ":0")
        pygame.init()
        pygame.mouse.set_visible(False)

        # Bildschirm einrichten
        if config.FULLSCREEN:
            self.screen = pygame.display.set_mode(
                (0, 0), pygame.FULLSCREEN | pygame.NOFRAME
            )
        else:
            self.screen = pygame.display.set_mode(
                (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
            )

        self.screen_width, self.screen_height = self.screen.get_size()
        pygame.display.set_caption("Digitaler Bilderrahmen")

        # Schrift
        try:
            self.font_small = pygame.font.SysFont("DejaVu Sans", 24, bold=True)
        except Exception:
            self.font_small = pygame.font.Font(None, 28)

        # Zustand
        self.images = []
        self.current_index = 0
        self.current_surface = None
        self.interval = config.get_interval()
        settings = config.get_settings()
        self.shuffle = bool(settings.get("shuffle", config.DEFAULT_SHUFFLE))
        self.transition = bool(settings.get("transition", config.DEFAULT_TRANSITION))
        # Nachtruhe
        self.sleep_enabled = bool(settings.get("sleep_enabled", config.DEFAULT_SLEEP_ENABLED))
        self.sleep_start = settings.get("sleep_start", config.DEFAULT_SLEEP_START)
        self.sleep_end = settings.get("sleep_end", config.DEFAULT_SLEEP_END)
        self.is_sleeping = False
        self.running = True
        self.reload_requested = False
        self._last_signal_check = 0

        # Hintergrund schwarz
        self.screen.fill((0, 0, 0))
        pygame.display.flip()

        logger.info(
            "Diashow gestartet. Aufloesung: %dx%d, Intervall: %ds",
            self.screen_width, self.screen_height, self.interval
        )

    def check_reload_signal(self):
        """Prueft ob ein Neu-Laden angefordert wurde."""
        if os.path.exists(config.RELOAD_SIGNAL_FILE):
            try:
                os.remove(config.RELOAD_SIGNAL_FILE)
                self.reload_requested = True
                logger.info("Reload-Signal erkannt.")
            except Exception:
                pass

    def check_interval_change(self):
        """Prueft ob das Intervall geaendert wurde."""
        if os.path.exists(config.INTERVAL_FILE):
            try:
                with open(config.INTERVAL_FILE) as f:
                    new_interval = int(f.read().strip())
                if new_interval != self.interval and 5 <= new_interval <= 7200:
                    self.interval = new_interval
                    logger.info("Neues Intervall: %d Sekunden", new_interval)
            except Exception:
                pass

    def check_settings_change(self):
        """Prueft ob Einstellungen (Zufall, Ueberblendung) geaendert wurden."""
        try:
            settings = config.get_settings()
            new_shuffle = bool(settings.get("shuffle", config.DEFAULT_SHUFFLE))
            new_transition = bool(settings.get("transition", config.DEFAULT_TRANSITION))
            if new_transition != self.transition:
                self.transition = new_transition
                logger.info("Ueberblendung: %s", "an" if new_transition else "aus")
            if new_shuffle != self.shuffle:
                self.shuffle = new_shuffle
                logger.info("Zufaellige Reihenfolge: %s", "an" if new_shuffle else "aus")
                # Bilderliste neu aufbauen (mit/ohne Zufall)
                self.reload_requested = True
            # Nachtruhe-Einstellungen uebernehmen
            self.sleep_enabled = bool(settings.get("sleep_enabled", config.DEFAULT_SLEEP_ENABLED))
            self.sleep_start = settings.get("sleep_start", config.DEFAULT_SLEEP_START)
            self.sleep_end = settings.get("sleep_end", config.DEFAULT_SLEEP_END)
        except Exception:
            pass

    # ── Nachtruhe / Display-Steuerung ──────────────────────────────────────
    @staticmethod
    def _parse_hhmm(value):
        """'HH:MM' -> Minuten seit Mitternacht, oder None."""
        try:
            h, m = str(value).split(":")
            h, m = int(h), int(m)
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h * 60 + m
        except (ValueError, AttributeError):
            pass
        return None

    def _in_sleep_window(self, now=None):
        """True, wenn die aktuelle Uhrzeit im Nachtruhe-Fenster liegt."""
        if not self.sleep_enabled:
            return False
        start = self._parse_hhmm(self.sleep_start)
        end = self._parse_hhmm(self.sleep_end)
        if start is None or end is None or start == end:
            return False
        now = now or datetime.now()
        cur = now.hour * 60 + now.minute
        if start < end:
            return start <= cur < end
        # Fenster ueber Mitternacht (z. B. 22:00 -> 07:00)
        return cur >= start or cur < end

    def _set_display_power(self, on):
        """Schaltet das HDMI-Display an/aus (mehrere Methoden je nach System)."""
        state = "1" if on else "0"
        cmds = [
            ["vcgencmd", "display_power", state],            # Raspberry Pi (HDMI-Signal)
            ["wlopm", "--on" if on else "--off", "*"],       # Wayland (labwc/wayfire)
            ["xset", "dpms", "force", "on" if on else "off"],  # X11 (DPMS)
        ]
        for cmd in cmds:
            try:
                subprocess.run(
                    cmd, check=False, timeout=5,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def enter_sleep(self):
        """In den Nachtruhe-Modus wechseln: Display aus."""
        if self.is_sleeping:
            return
        self.is_sleeping = True
        logger.info("Nachtruhe: Display wird ausgeschaltet.")
        # Bildschirm schwarz (falls das Panel nicht komplett abschaltet)
        try:
            self.screen.fill((0, 0, 0))
            pygame.display.flip()
        except Exception:
            pass
        self._set_display_power(False)

    def wake_up(self):
        """Aus der Nachtruhe aufwachen: Display an, Bild neu zeichnen."""
        if not self.is_sleeping:
            return
        self.is_sleeping = False
        logger.info("Nachtruhe beendet: Display wird eingeschaltet.")
        self._set_display_power(True)
        # aktuelles Bild wieder anzeigen
        if self.current_surface is not None:
            x = (self.screen_width - self.current_surface.get_width()) // 2
            y = (self.screen_height - self.current_surface.get_height()) // 2
            self.screen.fill((0, 0, 0))
            self.screen.blit(self.current_surface, (x, y))
            pygame.display.flip()

    def load_pygame_image(self, path):
        """Laedt ein Bild und skaliert es auf den Bildschirm."""
        try:
            raw = pygame.image.load(str(path)).convert()
            scaled = scale_image_to_screen(raw, self.screen_width, self.screen_height)
            return scaled
        except Exception as e:
            logger.warning("Konnte Bild nicht laden: %s (%s)", path, e)
            return None

    def crossfade(self, old_surface, new_surface, duration=1.0):
        """Weicher Uebergang zwischen zwei Bildern."""
        clock = pygame.time.Clock()
        steps = max(int(duration * 60), 1)
        x_old = (self.screen_width - old_surface.get_width()) // 2 if old_surface else 0
        y_old = (self.screen_height - old_surface.get_height()) // 2 if old_surface else 0
        x_new = (self.screen_width - new_surface.get_width()) // 2
        y_new = (self.screen_height - new_surface.get_height()) // 2

        for i in range(steps + 1):
            alpha = int(255 * i / steps)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False
                    return

            self.screen.fill((0, 0, 0))
            if old_surface:
                old_copy = old_surface.copy()
                old_copy.set_alpha(255 - alpha)
                self.screen.blit(old_copy, (x_old, y_old))
            new_copy = new_surface.copy()
            new_copy.set_alpha(alpha)
            self.screen.blit(new_copy, (x_new, y_new))
            pygame.display.flip()
            clock.tick(60)

    def show_image(self, surface, filename=""):
        """Zeigt ein Bild auf dem Bildschirm an."""
        x = (self.screen_width - surface.get_width()) // 2
        y = (self.screen_height - surface.get_height()) // 2

        self.screen.fill((0, 0, 0))
        self.screen.blit(surface, (x, y))

        if config.SHOW_FILENAME and filename:
            text_surf = self.font_small.render(filename, True, (255, 255, 255))
            shadow_surf = self.font_small.render(filename, True, (0, 0, 0))
            tx = 15
            ty = self.screen_height - text_surf.get_height() - 15
            self.screen.blit(shadow_surf, (tx + 1, ty + 1))
            self.screen.blit(text_surf, (tx, ty))

        pygame.display.flip()

    def run(self):
        """Haupt-Loop der Diashow."""
        clock = pygame.time.Clock()
        self.images = load_image_list(self.shuffle)

        if not self.images:
            self._show_no_images_screen()

        # Sofort erstes Bild zeigen
        last_change = time.time() - self.interval

        while self.running:
            current_time = time.time()

            # Events verarbeiten
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key in (pygame.K_RIGHT, pygame.K_SPACE):
                        # Sofort naechstes Bild
                        last_change = current_time - self.interval
                    elif event.key == pygame.K_LEFT:
                        # Zwei zurueck (nach Erhoehung wird es eins zurueck)
                        self.current_index = (self.current_index - 2) % max(len(self.images), 1)
                        last_change = current_time - self.interval

            # Signal-Check alle 2 Sekunden
            if current_time - self._last_signal_check >= 2:
                self._last_signal_check = current_time
                self.check_reload_signal()
                self.check_interval_change()
                self.check_settings_change()

            # Nachtruhe: Display nachts aus / morgens wieder an
            if self._in_sleep_window():
                self.enter_sleep()
            else:
                self.wake_up()

            if self.is_sleeping:
                # Nichts anzeigen, kein Bildwechsel; Timer zuruecksetzen,
                # damit nach dem Aufwachen die volle Anzeigedauer gilt.
                last_change = current_time
                pygame.time.wait(500)
                continue

            # Reload verarbeiten
            if self.reload_requested:
                self.reload_requested = False
                new_images = load_image_list(self.shuffle)
                self.images = new_images
                if not self.images:
                    self._show_no_images_screen()
                    clock.tick(10)
                    continue

            # Zeit fuer naechstes Bild?
            if self.images and (current_time - last_change >= self.interval):
                self._advance_image()
                last_change = current_time

            clock.tick(30)

        pygame.quit()
        logger.info("Diashow beendet.")

    def _advance_image(self):
        """Wechselt zum naechsten Bild."""
        if not self.images:
            return

        next_index = (self.current_index + 1) % len(self.images)
        next_path = self.images[next_index]
        next_surf = self.load_pygame_image(next_path)

        if next_surf is None:
            self.current_index = next_index
            return

        if self.current_surface is not None and self.transition:
            self.crossfade(self.current_surface, next_surf, config.TRANSITION_DURATION)
        else:
            x = (self.screen_width - next_surf.get_width()) // 2
            y = (self.screen_height - next_surf.get_height()) // 2
            self.screen.fill((0, 0, 0))
            self.screen.blit(next_surf, (x, y))
            pygame.display.flip()

        self.current_surface = next_surf
        self.current_index = next_index

        filename = next_path.name
        logger.info(
            "Zeige Bild: %s (%d/%d)", filename, next_index + 1, len(self.images)
        )

        # Dateiname kurz einblenden
        if config.SHOW_FILENAME:
            self.show_image(next_surf, filename)
            pygame.time.wait(int(config.FILENAME_DISPLAY_DURATION * 1000))
            # Dateiname wieder ausblenden
            x = (self.screen_width - next_surf.get_width()) // 2
            y = (self.screen_height - next_surf.get_height()) // 2
            self.screen.fill((0, 0, 0))
            self.screen.blit(next_surf, (x, y))
            pygame.display.flip()

    def _show_no_images_screen(self):
        """Zeigt einen Hinweis wenn keine Bilder vorhanden sind."""
        self.screen.fill((20, 20, 20))
        try:
            font_big = pygame.font.SysFont("DejaVu Sans", 48, bold=True)
            font_small = pygame.font.SysFont("DejaVu Sans", 28)
        except Exception:
            font_big = pygame.font.Font(None, 56)
            font_small = pygame.font.Font(None, 32)

        text1 = font_big.render("Digitaler Bilderrahmen", True, (200, 200, 200))
        text2 = font_small.render("Keine Bilder vorhanden.", True, (150, 150, 150))
        text3 = font_small.render(
            "Bilder per AirDrop oder Web-Interface hinzufuegen.", True, (120, 120, 120)
        )
        text4 = font_small.render(
            "Web-Interface: http://<IP>:8080", True, (100, 100, 120)
        )

        cx = self.screen_width // 2
        cy = self.screen_height // 2

        self.screen.blit(text1, (cx - text1.get_width() // 2, cy - 100))
        self.screen.blit(text2, (cx - text2.get_width() // 2, cy - 20))
        self.screen.blit(text3, (cx - text3.get_width() // 2, cy + 30))
        self.screen.blit(text4, (cx - text4.get_width() // 2, cy + 75))
        pygame.display.flip()


def main():
    os.makedirs(config.IMAGES_DIR, exist_ok=True)

    slideshow = Slideshow()
    try:
        slideshow.run()
    except KeyboardInterrupt:
        logger.info("Diashow durch Benutzer unterbrochen.")
    except Exception as e:
        logger.exception("Unerwarteter Fehler: %s", e)
        raise


if __name__ == "__main__":
    main()
