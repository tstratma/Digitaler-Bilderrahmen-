#!/usr/bin/env python3
"""
Digitaler Bilderrahmen - Web-Manager
Flask-App fuer die Verwaltung der Bilder vom iPhone aus.
"""

import os
import re
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_from_directory,
    flash,
    abort,
)
from werkzeug.utils import secure_filename

# Pfad fuer lokale Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import image_utils

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [web] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("web")

app = Flask(__name__)
app.secret_key = config.WEB_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_SIZE


# ─── Hilfsfunktionen ────────────────────────────────────────────────────────

def get_images():
    """Gibt alle Bilder in der richtigen Reihenfolge zurueck."""
    images_dir = Path(config.IMAGES_DIR)
    if not images_dir.exists():
        return []

    hidden = load_hidden()
    order = load_order()

    # Alle Bilder finden
    all_images = []
    for ext in config.ALLOWED_EXTENSIONS:
        all_images.extend(images_dir.glob(f"*{ext}"))
        all_images.extend(images_dir.glob(f"*{ext.upper()}"))

    # Duplikate entfernen
    seen = set()
    unique = []
    for img in all_images:
        r = img.resolve()
        if r not in seen:
            seen.add(r)
            unique.append(img)
    all_images = unique

    image_names = {img.name: img for img in all_images}

    result = []
    # Zuerst in benutzerdefinierter Reihenfolge
    for name in order:
        if name in image_names:
            result.append(name)

    # Dann alphabetisch restliche
    ordered_set = set(result)
    remaining = sorted(
        [name for name in image_names if name not in ordered_set],
        key=str.lower
    )
    result.extend(remaining)

    # Mit Metadaten anreichern
    output = []
    for name in result:
        path = image_names.get(name)
        if path:
            try:
                stat = path.stat()
                size_kb = stat.st_size // 1024
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M")
            except Exception:
                size_kb = 0
                mtime = ""
            output.append({
                "name": name,
                "hidden": hidden.get(name, False),
                "size_kb": size_kb,
                "modified": mtime,
            })

    return output


def load_hidden():
    """Laedt die Liste der versteckten Bilder."""
    if os.path.exists(config.HIDDEN_IMAGES_FILE):
        try:
            with open(config.HIDDEN_IMAGES_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_hidden(hidden: dict):
    """Speichert die Liste der versteckten Bilder."""
    with open(config.HIDDEN_IMAGES_FILE, "w") as f:
        json.dump(hidden, f, indent=2)


def load_order():
    """Laedt die benutzerdefinierte Reihenfolge."""
    if os.path.exists(config.ORDER_FILE):
        try:
            with open(config.ORDER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_order(order: list):
    """Speichert die benutzerdefinierte Reihenfolge."""
    with open(config.ORDER_FILE, "w") as f:
        json.dump(order, f, indent=2)


def signal_reload():
    """Signalisiert der Diashow, die Bilder neu zu laden."""
    try:
        with open(config.RELOAD_SIGNAL_FILE, "w") as f:
            f.write(str(time.time()))
    except Exception as e:
        logger.warning("Konnte Reload-Signal nicht senden: %s", e)


def allowed_file(filename: str) -> bool:
    """Prueft ob die Dateiendung fuer den Upload erlaubt ist (inkl. HEIC)."""
    return Path(filename).suffix.lower() in config.UPLOAD_EXTENSIONS


# ─── Routen ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Hauptseite mit Bildergalerie."""
    images = get_images()
    current_interval = config.get_interval()
    settings = config.get_settings()
    return render_template(
        "index.html",
        images=images,
        interval=current_interval,
        settings=settings,
        images_dir=config.IMAGES_DIR,
    )


@app.route("/upload", methods=["POST"])
def upload():
    """Bild hochladen."""
    os.makedirs(config.IMAGES_DIR, exist_ok=True)

    files = request.files.getlist("images")
    if not files or all(f.filename == "" for f in files):
        flash("Keine Dateien ausgewaehlt.", "error")
        return redirect(url_for("index"))

    uploaded = 0
    errors = 0

    for file in files:
        if file.filename == "":
            continue

        filename = secure_filename(file.filename)
        if not allowed_file(filename):
            flash(f"Dateiformat nicht erlaubt: {filename}", "error")
            errors += 1
            continue

        dest = Path(config.IMAGES_DIR) / filename
        # Bei Namenskonflikt umbenennen
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{stem}_{ts}{suffix}"
            dest = Path(config.IMAGES_DIR) / filename

        try:
            file.save(str(dest))
            # iPhone-HEIC/HEIF direkt in JPEG umwandeln (fuer die Diashow)
            if image_utils.is_heic(dest):
                converted = image_utils.normalize_image(dest)
                if converted is None:
                    logger.warning("HEIC konnte nicht umgewandelt werden: %s", filename)
                    try:
                        dest.unlink()  # nicht anzeigbare HEIC-Datei nicht liegen lassen
                    except OSError:
                        pass
                    flash(
                        f"'{filename}' ist HEIC und konnte nicht umgewandelt werden. "
                        "Bitte pillow-heif installieren oder JPEG hochladen.",
                        "error",
                    )
                    errors += 1
                    continue
                filename = Path(converted).name
            logger.info("Bild hochgeladen: %s", filename)
            uploaded += 1
        except Exception as e:
            logger.error("Upload-Fehler fuer %s: %s", filename, e)
            errors += 1

    if uploaded > 0:
        signal_reload()
        flash(
            f"{uploaded} Bild(er) erfolgreich hochgeladen." +
            (f" {errors} Fehler." if errors else ""),
            "success"
        )
    elif errors > 0:
        flash(f"Fehler beim Hochladen ({errors} Datei(en)).", "error")

    return redirect(url_for("index"))


@app.route("/delete/<filename>", methods=["POST"])
def delete(filename):
    """Bild loeschen."""
    filename = secure_filename(filename)
    filepath = Path(config.IMAGES_DIR) / filename

    if not filepath.exists():
        flash(f"Bild nicht gefunden: {filename}", "error")
        return redirect(url_for("index"))

    # Sicherstellen dass wir nur im Images-Verzeichnis loeschen
    try:
        filepath.resolve().relative_to(Path(config.IMAGES_DIR).resolve())
    except ValueError:
        abort(403)

    try:
        filepath.unlink()
        logger.info("Bild geloescht: %s", filename)

        # Aus hidden und order entfernen
        hidden = load_hidden()
        hidden.pop(filename, None)
        save_hidden(hidden)

        order = load_order()
        if filename in order:
            order.remove(filename)
            save_order(order)

        signal_reload()
        flash(f"'{filename}' wurde geloescht.", "success")
    except Exception as e:
        logger.error("Fehler beim Loeschen von %s: %s", filename, e)
        flash(f"Fehler beim Loeschen: {e}", "error")

    return redirect(url_for("index"))


@app.route("/toggle_hidden/<filename>", methods=["POST"])
def toggle_hidden(filename):
    """Bild ein-/ausblenden."""
    filename = secure_filename(filename)
    hidden = load_hidden()
    hidden[filename] = not hidden.get(filename, False)
    save_hidden(hidden)
    signal_reload()

    state = "versteckt" if hidden[filename] else "sichtbar"
    flash(f"'{filename}' ist jetzt {state}.", "success")
    return redirect(url_for("index"))


@app.route("/set_settings", methods=["POST"])
def set_settings():
    """Wiedergabe-Einstellungen (Zufall, Ueberblendung) speichern."""
    # Checkboxen: vorhanden = an, fehlend = aus
    config.set_setting("shuffle", request.form.get("shuffle") == "on")
    config.set_setting("transition", request.form.get("transition") == "on")
    signal_reload()
    flash("Einstellungen gespeichert.", "success")
    return redirect(url_for("index"))


@app.route("/set_sleep", methods=["POST"])
def set_sleep():
    """Nachtruhe speichern: Display nachts aus (Strom sparen)."""
    config.set_setting("sleep_enabled", request.form.get("sleep_enabled") == "on")
    for key in ("sleep_start", "sleep_end"):
        val = (request.form.get(key) or "").strip()
        if re.match(r"^\d{1,2}:\d{2}$", val):
            h, m = (int(x) for x in val.split(":"))
            if 0 <= h <= 23 and 0 <= m <= 59:
                config.set_setting(key, f"{h:02d}:{m:02d}")
    signal_reload()
    flash("Nachtruhe gespeichert.", "success")
    return redirect(url_for("index"))


@app.route("/set_interval", methods=["POST"])
def set_interval():
    """Diashow-Intervall setzen. Akzeptiert Minuten + Sekunden oder Sekunden."""
    try:
        # Bevorzugt Minuten/Sekunden-Felder, sonst das reine Sekundenfeld
        if request.form.get("minutes") is not None or request.form.get("seconds") is not None:
            minutes = int(request.form.get("minutes") or 0)
            secs = int(request.form.get("seconds") or 0)
            seconds = minutes * 60 + secs
        else:
            seconds = int(request.form.get("interval", 300))
        if not (5 <= seconds <= 7200):
            flash("Intervall muss zwischen 5 und 7200 Sekunden liegen.", "error")
            return redirect(url_for("index"))
        config.set_interval(seconds)
        signal_reload()
        minutes = seconds // 60
        rest = seconds % 60
        if minutes > 0:
            time_str = f"{minutes} Min. {rest} Sek." if rest else f"{minutes} Min."
        else:
            time_str = f"{seconds} Sek."
        flash(f"Intervall auf {time_str} gesetzt.", "success")
    except (ValueError, TypeError):
        flash("Ungueltige Eingabe.", "error")

    return redirect(url_for("index"))


@app.route("/reorder", methods=["POST"])
def reorder():
    """Reihenfolge der Bilder speichern (AJAX)."""
    data = request.get_json()
    if not data or "order" not in data:
        return jsonify({"error": "Keine Reihenfolge angegeben."}), 400

    new_order = [secure_filename(name) for name in data["order"]]
    save_order(new_order)
    signal_reload()
    logger.info("Reihenfolge aktualisiert: %d Bilder", len(new_order))
    return jsonify({"status": "ok", "count": len(new_order)})


@app.route("/images/<filename>")
def serve_image(filename):
    """Bild ausliefern (fuer Vorschau)."""
    filename = secure_filename(filename)
    return send_from_directory(config.IMAGES_DIR, filename)


@app.route("/api/status")
def api_status():
    """API-Endpunkt: Status."""
    images = get_images()
    return jsonify({
        "images_total": len(images),
        "images_visible": sum(1 for i in images if not i["hidden"]),
        "interval": config.get_interval(),
        "images_dir": config.IMAGES_DIR,
    })


@app.errorhandler(413)
def too_large(e):
    flash(
        f"Datei zu gross. Maximale Groesse: {config.MAX_UPLOAD_SIZE // (1024*1024)} MB.",
        "error"
    )
    return redirect(url_for("index"))


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(config.IMAGES_DIR, exist_ok=True)
    logger.info(
        "Web-Manager gestartet auf http://%s:%d", config.WEB_HOST, config.WEB_PORT
    )
    app.run(
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        debug=False,
        threaded=True,
    )
