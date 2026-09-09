# 🖼 Digitaler Bilderrahmen (Raspberry Pi 4)

Digitaler Bilderrahmen für Raspberry Pi 4 mit HDMI-Display (z. B. altes
Notebook-Panel). Zeigt Fotos als Vollbild-Diashow, wechselt standardmäßig
alle **5 Minuten** und lässt sich komfortabel **vom iPhone aus verwalten**.

---

## ⚠️ Wichtig zuerst: Funktioniert das? Und was ist mit AirDrop?

**Kurz:** Ja, das Projekt funktioniert – mit *einer* ehrlichen Einschränkung
beim Ursprungswunsch „AirDrop".

| Funktion | Status |
|---|---|
| Vollbild-Diashow, Wechsel alle 5 Min, weiche Überblendung | ✅ funktioniert |
| Verwaltung vom iPhone (hochladen, löschen, sortieren, Intervall) | ✅ funktioniert (Web-Interface) |
| iPhone-Fotos im HEIC-Format | ✅ werden automatisch in JPEG umgewandelt |
| Bilder per SMB (Dateien-App) senden | ✅ funktioniert |
| **Echtes Apple-AirDrop** | ❌ **nicht praktikabel** – siehe unten |

### Warum AirDrop nicht (sinnvoll) geht

AirDrop nutzt Apples proprietäres Funkprotokoll **AWDL**. Ein Raspberry Pi
kann das nicht ab Werk. Man bräuchte:

- einen WLAN-Adapter im **Monitor-Mode mit Frame-Injection** (die interne
  Pi-4-Karte nur mit gepatchter *Nexmon*-Firmware),
- den **`owl`-Daemon** (Open Wireless Link), laufend als root,
- das reverse-engineerte Tool **`opendrop`** von seemoo-lab.

Das ist fragil, **blockiert währenddessen das normale WLAN** und ist für
einen Dauerbetrieb als Bilderrahmen im Alltag ungeeignet. Der frühere Code
hierfür rief außerdem eine `opendrop`-API auf (`OpenDropServer`), die es im
echten Paket gar nicht gibt – er hätte also nie echtes AirDrop empfangen.

### Was du stattdessen bekommst (genauso bequem)

Zwei zuverlässige Wege, Fotos vom iPhone auf den Rahmen zu bringen:

1. **Web-Interface (empfohlen).** Im Safari `http://bilderrahmen.local:8080`
   öffnen → Fotos direkt aus der Fotos-App hochladen, verwalten, sortieren.
   **Tipp:** Safari → Teilen → *„Zum Home-Bildschirm"* – dann liegt ein
   App-Icon auf dem iPhone und es fühlt sich an wie AirDrop.
2. **SMB / Dateien-App.** In der *Dateien*-App → *Verbinden mit Server* →
   `smb://bilderrahmen.local` → Ordner **Bilderrahmen** → Fotos hineinkopieren.
   Sie landen automatisch in der Diashow.

---

## 🧩 Bestandteile

| Datei | Zweck |
|---|---|
| `slideshow.py` | Vollbild-Diashow (pygame), Bildwechsel + Überblendung |
| `web_manager/app.py` | Flask-Web-Interface zur Verwaltung vom iPhone |
| `web_manager/templates/index.html` | Mobile Oberfläche (Upload, Sortieren, Intervall) |
| `airdrop_receiver.py` | Eingangs-Watcher: `incoming/` → Diashow (inkl. HEIC→JPEG) |
| `image_utils.py` | HEIC/HEIF-Umwandlung für iPhone-Fotos |
| `config.py` | Zentrale Konfiguration (Intervall, Pfade, Formate …) |
| `setup.sh` | Automatische Installation auf dem Raspberry Pi |
| `services/*.service` | systemd-Dienste (Autostart) |

---

## 🚀 Installation

Auf dem Raspberry Pi (Raspberry Pi OS **mit Desktop**):

```bash
git clone <REPO-URL> ~/Digitaler-Bilderrahmen
cd ~/Digitaler-Bilderrahmen
sudo bash setup.sh
sudo reboot
```

Nach dem Neustart:

- Diashow startet automatisch im Vollbild (Desktop-Autostart).
- Web-Interface: `http://bilderrahmen.local:8080` (oder `http://<IP>:8080`).

> **Hinweis Raspberry Pi OS *Bookworm* (Wayland):** Die Diashow wird als
> **Desktop-Autostart** gestartet und erbt dadurch die richtige Anzeige-
> Umgebung (X11 *oder* Wayland). Deshalb **nicht** den Slideshow-Dienst als
> System-Dienst per `systemctl` erzwingen – der Autostart ist der robuste Weg.
> Für einen reinen Kiosk ohne Desktop siehe „Ohne Desktop" weiter unten.

---

## ⚙️ Einstellungen im Web-Interface

Direkt vom iPhone im Web-Interface (`http://bilderrahmen.local:8080`) einstellbar –
Änderungen wirken **live**, ohne Neustart:

- **Wie oft das Bild wechselt** – in Minuten + Sekunden, plus Schnellwahl
  (30 Sek. / 1 / 5 / 10 / 30 Min.)
- **Zufällige Reihenfolge** an/aus
- **Weiche Überblendung** an/aus
- **Nachtruhe** – Display zu festen Uhrzeiten aus/an (Strom sparen)

### 🌙 Nachtruhe (nachts Display aus)

Stell im Web-Interface „Aus ab" und „Wieder an" ein (z. B. 22:00 → 07:00,
auch über Mitternacht). In diesem Zeitfenster schaltet die Diashow das
**HDMI-Display in Standby** – das spart den Löwenanteil des Stroms (das Panel
ist der größte Verbraucher). Der Raspberry Pi selbst läuft weiter (er kann
sich aus einem echten Shutdown nicht selbst wieder einschalten), verbraucht
aber nur wenige Watt; morgens geht das Display automatisch wieder an.

Das Abschalten nutzt je nach System automatisch `vcgencmd display_power`
(Raspberry Pi), `wlopm` (Wayland) oder `xset dpms` (X11).

- Der Benutzer sollte in der Gruppe `video` sein (Standard beim `pi`-User):
  `sudo usermod -aG video $USER`
- **Raspberry Pi OS Bookworm/Wayland:** Schaltet das Panel nicht ab, hilft
  `sudo apt install wlopm`.

### Weitere Werte in `config.py`

- `DEFAULT_INTERVAL = 300` → Start-Intervall (5 Min)
- `SHOW_FILENAME = False` → Dateiname nicht einblenden (typisch für Rahmen)
- `TRANSITION_DURATION` → Dauer der Überblendung
- `WEB_PORT = 8080` → Port des Web-Interfaces

---

## 📱 iPhone-Fotos & HEIC

iPhones speichern Fotos standardmäßig als **HEIC**. pygame kann HEIC nicht
anzeigen, deshalb werden HEIC/HEIF-Dateien beim Upload/Empfang automatisch in
JPEG umgewandelt (`image_utils.py`, benötigt `pillow-heif` – wird von
`setup.sh` installiert).

Alternativ am iPhone: *Einstellungen → Kamera → Formate → „Maximale
Kompatibilität"* → neue Fotos werden direkt als JPEG aufgenommen.

---

## 🔧 Dienste & Logs

```bash
sudo systemctl status bilderrahmen-web       # Web-Interface
sudo systemctl status bilderrahmen-airdrop   # Eingangs-Watcher (incoming/)
tail -f ~/Digitaler-Bilderrahmen/bilderrahmen.log
```

Diashow-Steuerung per Tastatur (falls Tastatur angeschlossen):
`→`/`Leertaste` weiter, `←` zurück, `Esc` beenden.

---

## 🖥 Ohne Desktop (optionaler Kiosk-Modus)

Wer Raspberry Pi OS **Lite** ohne Desktop nutzt, startet die Diashow z. B.
per X aus der Konsole (`startx`) oder richtet den mitgelieferten
`services/bilderrahmen-slideshow.service` passend zur eigenen Anzeige-
Umgebung ein (`DISPLAY`/`XAUTHORITY` bzw. `WAYLAND_DISPLAY` korrekt setzen).
Der Autostart-Weg auf der Desktop-Version ist deutlich einfacher.

---

## 🧪 Lokaler Test (auch am PC)

Nur das Web-Interface testen (ohne Display):

```bash
pip install flask pillow pillow-heif werkzeug
python3 web_manager/app.py
# -> http://localhost:8080
```
