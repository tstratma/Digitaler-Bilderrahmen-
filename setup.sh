#!/usr/bin/env bash
# =============================================================================
# Digitaler Bilderrahmen - Setup-Skript fuer Raspberry Pi 4
# =============================================================================
# Ausfuehren mit: sudo bash setup.sh
# =============================================================================

set -euo pipefail

# ── Farben ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Konfiguration ──
PI_USER="${SUDO_USER:-pi}"
PI_HOME="/home/${PI_USER}"
INSTALL_DIR="${PI_HOME}/Digitaler-Bilderrahmen"
IMAGES_DIR="${INSTALL_DIR}/images"
INCOMING_DIR="${INSTALL_DIR}/incoming"
SERVICES_DIR="${INSTALL_DIR}/services"
SYSTEMD_DIR="/etc/systemd/system"

log()    { echo -e "${GREEN}[OK]${NC}  $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()  { echo -e "${RED}[ERR]${NC}  $*" >&2; }
header() { echo -e "\n${BOLD}${BLUE}==> $*${NC}"; }

# ── Root-Check ──
if [[ $EUID -ne 0 ]]; then
  error "Dieses Skript muss als root ausgefuehrt werden: sudo bash setup.sh"
  exit 1
fi

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════╗"
echo "║     Digitaler Bilderrahmen - Setup               ║"
echo "║     Raspberry Pi 4                               ║"
echo "╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Quell-Verzeichnis ermitteln ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
log "Skript-Verzeichnis: ${SCRIPT_DIR}"
log "Installations-Verzeichnis: ${INSTALL_DIR}"
log "Benutzer: ${PI_USER}"

# ── System aktualisieren ──
header "System-Pakete aktualisieren"
apt-get update -y
apt-get upgrade -y

# ── System-Pakete installieren ──
header "Pakete installieren"

PACKAGES=(
  python3
  python3-pip
  python3-venv
  python3-pygame
  python3-flask
  python3-pil
  python3-dev
  libssl-dev
  libffi-dev
  build-essential
  git
  # HEIC/HEIF (iPhone-Fotos) -> JPEG
  libheif1
  libde265-0
  # Avahi / mDNS (Geraet im Netz per Namen findbar: bilderrahmen.local)
  avahi-daemon
  avahi-utils
  # Samba: Ordnerfreigabe fuer die iPhone "Dateien"-App (SMB)
  samba
  samba-common-bin
  # Sonstige Tools
  feh
  imagemagick
  curl
  unzip
)

apt-get install -y "${PACKAGES[@]}" || {
  warn "Einige Pakete konnten nicht installiert werden. Fortfahren..."
}
log "System-Pakete installiert."

# ── Python-Pakete ──
header "Python-Abhaengigkeiten pruefen"

# Auf Raspberry Pi OS Bookworm ist die System-Python-Umgebung
# "externally managed" -> 'pip install' schlaegt fehl. Deshalb kommt das
# Meiste ueber apt (oben: python3-flask, python3-pygame, python3-pil).
# Kein pip-Upgrade noetig.
#
# Nur pillow-heif (HEIC/HEIF von iPhone-Fotos) ist ggf. nicht als apt-Paket
# vorhanden und wird robust nachinstalliert.

HEIF_OK=0

# 1) Bevorzugt via apt (falls paketiert)
if apt-get install -y python3-pillow-heif >/dev/null 2>&1; then
  HEIF_OK=1
  log "pillow-heif via apt installiert (HEIC-Unterstuetzung aktiv)."
fi

# 2) Sonst via pip mit --break-system-packages (Bookworm-konform)
if [[ "${HEIF_OK}" -ne 1 ]]; then
  if pip3 install --break-system-packages pillow-heif >/dev/null 2>&1; then
    HEIF_OK=1
    log "pillow-heif via pip installiert (HEIC-Unterstuetzung aktiv)."
  fi
fi

if [[ "${HEIF_OK}" -ne 1 ]]; then
  warn "pillow-heif konnte nicht installiert werden."
  warn "  -> iPhone-HEIC-Fotos werden dann nicht automatisch umgewandelt."
  warn "  -> Alternative am iPhone: Einstellungen -> Kamera -> Formate"
  warn "     -> 'Maximale Kompatibilitaet' (nimmt Fotos direkt als JPEG auf)."
fi

# Hinweis: 'opendrop' (echtes AirDrop) wird bewusst NICHT installiert.
# Es benoetigt den 'owl'-Daemon + passende WLAN-Hardware und ist fuer den
# Alltag nicht praktikabel. Siehe README.md.

log "Python-Abhaengigkeiten bereit (Flask/pygame/Pillow via apt)."

# ── Verzeichnisse erstellen ──
header "Verzeichnisse erstellen"

# Installations-Verzeichnis anlegen oder aktualisieren
if [[ "${SCRIPT_DIR}" != "${INSTALL_DIR}" ]]; then
  if [[ -d "${INSTALL_DIR}" ]]; then
    warn "Zielverzeichnis existiert bereits: ${INSTALL_DIR}"
    read -r -p "Vorhandene Dateien ueberschreiben? [j/N] " answer
    if [[ "${answer,,}" != "j" ]]; then
      log "Bestehende Installation wird beibehalten."
    else
      cp -r "${SCRIPT_DIR}/." "${INSTALL_DIR}/"
      log "Dateien kopiert nach: ${INSTALL_DIR}"
    fi
  else
    mkdir -p "${INSTALL_DIR}"
    cp -r "${SCRIPT_DIR}/." "${INSTALL_DIR}/"
    log "Projekt kopiert nach: ${INSTALL_DIR}"
  fi
else
  log "Skript laeuft bereits im Zielverzeichnis."
fi

mkdir -p "${IMAGES_DIR}"
mkdir -p "${INCOMING_DIR}"
log "Bilder-Verzeichnisse erstellt."

# Log-Datei vorab anlegen (damit sie dem Benutzer gehoert, nicht root)
touch "${INSTALL_DIR}/bilderrahmen.log" 2>/dev/null || true

# Berechtigungen setzen
chown -R "${PI_USER}:${PI_USER}" "${INSTALL_DIR}"
chmod -R u+rw "${INSTALL_DIR}"
chmod +x "${INSTALL_DIR}/slideshow.py" 2>/dev/null || true
chmod +x "${INSTALL_DIR}/airdrop_receiver.py" 2>/dev/null || true
chmod +x "${INSTALL_DIR}/web_manager/app.py" 2>/dev/null || true

log "Berechtigungen gesetzt."

# ── Konfiguration anpassen ──
header "Konfiguration anpassen"

CONFIG_FILE="${INSTALL_DIR}/config.py"
if [[ -f "${CONFIG_FILE}" ]]; then
  # BASE_DIR auf den aktuellen Benutzer anpassen
  sed -i "s|/home/pi/Digitaler-Bilderrahmen|${INSTALL_DIR}|g" "${CONFIG_FILE}"
  log "config.py angepasst: BASE_DIR = ${INSTALL_DIR}"
fi

# Service-Dateien anpassen
for svc_file in "${SERVICES_DIR}"/*.service; do
  if [[ -f "${svc_file}" ]]; then
    sed -i "s|/home/pi|${PI_HOME}|g" "${svc_file}"
    sed -i "s|User=pi|User=${PI_USER}|g" "${svc_file}"
    sed -i "s|Group=pi|Group=${PI_USER}|g" "${svc_file}"
    log "Service-Datei angepasst: $(basename "${svc_file}")"
  fi
done

# ── Avahi / mDNS konfigurieren ──
header "Avahi (mDNS) konfigurieren"

AVAHI_CONF="/etc/avahi/avahi-daemon.conf"
if [[ -f "${AVAHI_CONF}" ]]; then
  # allow-interfaces = wlan0 (falls nicht schon gesetzt)
  if ! grep -q "allow-interfaces" "${AVAHI_CONF}"; then
    sed -i '/\[server\]/a allow-interfaces=wlan0,eth0' "${AVAHI_CONF}"
  fi
  log "Avahi konfiguriert."
fi

systemctl enable avahi-daemon
systemctl start avahi-daemon || warn "Avahi konnte nicht gestartet werden."
log "Avahi aktiviert."

# ── Samba-Freigabe (iPhone "Dateien"-App) ──
header "Samba-Freigabe fuer den 'incoming'-Ordner einrichten"

SMB_CONF="/etc/samba/smb.conf"
if [[ -f "${SMB_CONF}" ]] && ! grep -q "\[Bilderrahmen\]" "${SMB_CONF}"; then
  cat >> "${SMB_CONF}" <<EOF

[Bilderrahmen]
   comment = Digitaler Bilderrahmen - Bilder hierher kopieren
   path = ${INCOMING_DIR}
   browseable = yes
   read only = no
   guest ok = yes
   create mask = 0664
   directory mask = 0775
   force user = ${PI_USER}
EOF
  log "Samba-Freigabe 'Bilderrahmen' hinzugefuegt (Ziel: ${INCOMING_DIR})."
else
  warn "Samba-Freigabe schon vorhanden oder smb.conf fehlt - uebersprungen."
fi

# 'incoming' fuer Gast-Schreibzugriff vorbereiten
mkdir -p "${INCOMING_DIR}"
chmod 0775 "${INCOMING_DIR}" 2>/dev/null || true

systemctl enable smbd 2>/dev/null || warn "smbd-Dienst nicht gefunden."
systemctl restart smbd 2>/dev/null || warn "smbd konnte nicht gestartet werden."
log "Samba konfiguriert. iPhone: Dateien-App -> Verbinden -> smb://$(hostname).local"

# ── Autostart fuer Desktop (LXDE/openbox) ──
header "Desktop-Autostart konfigurieren"

AUTOSTART_DIR="${PI_HOME}/.config/autostart"
mkdir -p "${AUTOSTART_DIR}"

cat > "${AUTOSTART_DIR}/bilderrahmen-slideshow.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Digitaler Bilderrahmen - Diashow
Comment=Vollbild-Diashow beim Login starten
Exec=/usr/bin/python3 ${INSTALL_DIR}/slideshow.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

chown "${PI_USER}:${PI_USER}" "${AUTOSTART_DIR}/bilderrahmen-slideshow.desktop"
log "Desktop-Autostart eingerichtet."

# ── Systemd Services installieren ──
header "Systemd-Dienste installieren"

SERVICES=(
  "bilderrahmen-web.service"
  "bilderrahmen-airdrop.service"
)

for svc in "${SERVICES[@]}"; do
  src="${SERVICES_DIR}/${svc}"
  dst="${SYSTEMD_DIR}/${svc}"

  if [[ -f "${src}" ]]; then
    cp "${src}" "${dst}"
    chmod 644 "${dst}"
    systemctl daemon-reload
    systemctl enable "${svc}"
    log "Service installiert und aktiviert: ${svc}"
  else
    warn "Service-Datei nicht gefunden: ${src}"
  fi
done

# Slideshow-Service nur installieren, nicht als System-Service aktivieren
# (laeuft besser als Desktop-Autostart, da Display-Zugriff benoetigt wird)
SLIDESHOW_SVC="bilderrahmen-slideshow.service"
if [[ -f "${SERVICES_DIR}/${SLIDESHOW_SVC}" ]]; then
  cp "${SERVICES_DIR}/${SLIDESHOW_SVC}" "${SYSTEMD_DIR}/${SLIDESHOW_SVC}"
  chmod 644 "${SYSTEMD_DIR}/${SLIDESHOW_SVC}"
  systemctl daemon-reload
  # Als User-Service einrichten
  USER_SYSTEMD="${PI_HOME}/.config/systemd/user"
  mkdir -p "${USER_SYSTEMD}"
  cp "${SERVICES_DIR}/${SLIDESHOW_SVC}" "${USER_SYSTEMD}/${SLIDESHOW_SVC}"
  chown -R "${PI_USER}:${PI_USER}" "${PI_HOME}/.config/systemd"
  log "Slideshow-Service als User-Service eingerichtet."
  warn "Slideshow laeuft via Desktop-Autostart (DISPLAY erforderlich)."
fi

# ── Dienste starten ──
header "Dienste starten"

systemctl daemon-reload

for svc in "${SERVICES[@]}"; do
  if systemctl is-enabled "${svc}" &>/dev/null; then
    systemctl restart "${svc}" || warn "${svc} konnte nicht gestartet werden."
    log "${svc} gestartet."
  fi
done

# ── Firewall (falls ufw aktiv) ──
if command -v ufw &>/dev/null && ufw status | grep -q "Status: active"; then
  header "Firewall-Regeln"
  ufw allow 8080/tcp comment "Bilderrahmen Web-Manager" 2>/dev/null || true
  log "Port 8080 in Firewall freigegeben."
fi

# ── Beispielbild herunterladen (optional) ──
header "Beispiel-Bild erstellen"
SAMPLE_IMAGE="${IMAGES_DIR}/willkommen.jpg"
if [[ ! -f "${SAMPLE_IMAGE}" ]]; then
  # Erstelle ein einfaches Platzhalterbild mit ImageMagick
  if command -v convert &>/dev/null; then
    convert -size 1920x1080 \
      gradient:'#1a1a22-#22224e' \
      -gravity Center \
      -fill white \
      -font DejaVu-Sans-Bold \
      -pointsize 72 \
      -annotate 0 "Willkommen\nDigitaler Bilderrahmen" \
      "${SAMPLE_IMAGE}" 2>/dev/null && \
    chown "${PI_USER}:${PI_USER}" "${SAMPLE_IMAGE}" && \
    log "Beispielbild erstellt: ${SAMPLE_IMAGE}" || \
    warn "Konnte Beispielbild nicht erstellen."
  fi
fi

# ── Abschluss ──
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║     Setup erfolgreich abgeschlossen!             ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}Naechste Schritte:${NC}"
echo ""
echo -e "  1. ${YELLOW}Raspberry Pi neu starten:${NC}"
echo -e "     sudo reboot"
echo ""
echo -e "  2. ${YELLOW}Web-Interface aufrufen:${NC}"
echo -e "     http://$(hostname -I | awk '{print $1}' 2>/dev/null || echo '<IP-Adresse>'):8080"
echo ""
echo -e "  3. ${YELLOW}Bilder vom iPhone senden (2 Wege):${NC}"
echo -e "     a) Web: http://$(hostname).local:8080  (Fotos-App -> Hochladen)"
echo -e "        Tipp: Safari -> Teilen -> 'Zum Home-Bildschirm'"
echo -e "     b) Dateien-App -> Verbinden mit Server -> smb://$(hostname).local"
echo -e "        -> Ordner 'Bilderrahmen' -> Fotos hineinkopieren"
echo -e "     Hinweis: Echtes AirDrop wird NICHT unterstuetzt (siehe README.md)."
echo ""
echo -e "  4. ${YELLOW}Dienste pruefen:${NC}"
echo -e "     sudo systemctl status bilderrahmen-web"
echo -e "     sudo systemctl status bilderrahmen-airdrop"
echo ""
echo -e "  5. ${YELLOW}Logs anzeigen:${NC}"
echo -e "     tail -f ${INSTALL_DIR}/bilderrahmen.log"
echo ""
echo -e "  6. ${YELLOW}Bilder manuell hinzufuegen:${NC}"
echo -e "     Bilder in ${IMAGES_DIR} kopieren"
echo -e "     Oder in ${INCOMING_DIR} fuer Auto-Import"
echo ""
log "Fertig! Bitte Raspberry Pi neu starten."
