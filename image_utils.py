#!/usr/bin/env python3
"""
Bild-Hilfsfunktionen fuer den Digitalen Bilderrahmen.

Wichtigster Zweck: iPhone-Fotos sind standardmaessig im HEIC/HEIF-Format.
pygame (Diashow) kann HEIC NICHT anzeigen. Deshalb wandeln wir HEIC/HEIF
direkt beim Empfang/Upload in JPEG um, sofern die dafuer noetigen
Bibliotheken (Pillow + pillow-heif) installiert sind.
"""

import logging
from pathlib import Path

logger = logging.getLogger("image_utils")

HEIC_EXTENSIONS = {".heic", ".heif"}

# Pillow ist optional, aber fuer die HEIC-Umwandlung noetig.
try:
    from PIL import Image, ImageOps
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PIL_AVAILABLE = False

# pillow-heif registriert den HEIC-Decoder in Pillow.
try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
    _HEIF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _HEIF_AVAILABLE = False


def is_heic(path) -> bool:
    """True, wenn die Datei eine HEIC/HEIF-Endung hat."""
    return Path(path).suffix.lower() in HEIC_EXTENSIONS


def heic_supported() -> bool:
    """True, wenn HEIC->JPEG-Umwandlung moeglich ist."""
    return _PIL_AVAILABLE and _HEIF_AVAILABLE


def convert_heic_to_jpeg(src_path, delete_original: bool = True):
    """
    Wandelt eine HEIC/HEIF-Datei in JPEG um.

    Rueckgabe: Pfad (str) zur neuen JPEG-Datei bei Erfolg,
               sonst None (dann bleibt das Original erhalten).
    """
    src = Path(src_path)
    if not is_heic(src):
        return str(src)

    if not heic_supported():
        logger.warning(
            "HEIC-Datei %s kann nicht umgewandelt werden "
            "(pillow / pillow-heif fehlt). Datei wird uebersprungen.",
            src.name,
        )
        return None

    dest = src.with_suffix(".jpg")
    # Namenskonflikt vermeiden
    counter = 1
    while dest.exists():
        dest = src.with_name(f"{src.stem}_{counter}.jpg")
        counter += 1

    try:
        with Image.open(src) as img:
            # EXIF-Ausrichtung anwenden (iPhone-Hochformat korrekt drehen)
            img = ImageOps.exif_transpose(img)
            rgb = img.convert("RGB")
            rgb.save(dest, "JPEG", quality=90, optimize=True)
        logger.info("HEIC umgewandelt: %s -> %s", src.name, dest.name)
        if delete_original:
            try:
                src.unlink()
            except OSError:
                pass
        return str(dest)
    except Exception as e:  # pragma: no cover
        logger.error("Fehler bei HEIC-Umwandlung von %s: %s", src.name, e)
        return None


def normalize_image(path, delete_original: bool = True):
    """
    Bereitet eine empfangene/hochgeladene Bilddatei fuer die Diashow vor.
    Aktuell: HEIC/HEIF -> JPEG. Andere Formate bleiben unveraendert.

    Rueckgabe: Pfad zur nutzbaren Datei oder None, wenn nicht verwendbar.
    """
    if is_heic(path):
        return convert_heic_to_jpeg(path, delete_original=delete_original)
    return str(path)
