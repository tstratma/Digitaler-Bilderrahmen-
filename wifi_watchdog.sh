#!/usr/bin/env bash
# =============================================================================
# Digitaler Bilderrahmen - WLAN-Waechter
# =============================================================================
# Wird per systemd-Timer alle 2 Minuten gestartet
# (services/bilderrahmen-wifi-watchdog.timer).
#
# Warum? Bricht das WLAN kurz ab (Funkstoerung, Router erneuert seinen
# Schluessel, schwaches Signal hinter dem Display ...), haelt NetworkManager
# das manchmal fuer ein falsches Passwort: Es zeigt den Dialog
# "WLAN-Authentifizierung" und versucht danach NICHT mehr selbst neu zu
# verbinden - bis zum Neustart.
#
# Dieses Skript aktiviert in dem Fall die gespeicherte Verbindung neu.
# Dabei verschwindet auch der Passwort-Dialog wieder.
#
# Protokoll ansehen:  journalctl -t bilderrahmen-wlan
# =============================================================================

set -u
export LC_ALL=C   # nmcli-Ausgaben immer englisch -> zuverlaessig auswertbar

IFACE="${WIFI_IFACE:-wlan0}"
TAG="bilderrahmen-wlan"

log() {
  logger -t "${TAG}" -- "$*" 2>/dev/null
  echo "$*"
}

# Numerischer NetworkManager-Status des Geraets (100 = verbunden)
device_state() {
  local s
  s="$(nmcli -g GENERAL.STATE device show "${IFACE}" 2>/dev/null)"
  echo "${s%% *}"
}

command -v nmcli >/dev/null 2>&1 || exit 0                       # kein NetworkManager
[[ -e "/sys/class/net/${IFACE}" ]] || exit 0                     # kein WLAN-Geraet
[[ "$(nmcli radio wifi 2>/dev/null)" == "enabled" ]] || exit 0   # WLAN bewusst aus

# Bis zu 30 s abwarten, falls NetworkManager gerade selbst neu verbindet
state=""
for _ in 1 2 3; do
  state="$(device_state)"
  [[ "${state}" == "100" ]] && exit 0                    # verbunden - alles gut
  [[ -z "${state}" || "${state}" == "10" ]] && exit 0    # nicht von NM verwaltet
  sleep 10
done

# Zuletzt erfolgreich genutzte WLAN-Verbindung suchen (hoechster Zeitstempel)
uuid="$(nmcli -t -f TIMESTAMP,UUID,TYPE connection show 2>/dev/null \
  | awk -F: '$3 == "802-11-wireless" && $1 > 0 {print $1, $2}' \
  | sort -rn | head -n 1 | cut -d' ' -f2)"

if [[ -z "${uuid}" ]]; then
  log "WLAN getrennt (Status ${state}), aber keine gespeicherte WLAN-Verbindung gefunden."
  exit 0
fi

name="$(nmcli -g connection.id connection show uuid "${uuid}" 2>/dev/null)"
log "WLAN getrennt (Status ${state}) - verbinde '${name:-${uuid}}' neu ..."

if nmcli --wait 60 connection up uuid "${uuid}" ifname "${IFACE}" >/dev/null 2>&1; then
  log "WLAN wieder verbunden."
else
  log "Neuverbindung fehlgeschlagen - naechster Versuch in 2 Minuten."
fi
exit 0
