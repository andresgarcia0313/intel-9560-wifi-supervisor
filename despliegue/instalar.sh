#!/usr/bin/env bash
# instalar.sh [actuar|observar] - Instala el controlador en el Dell. Corre como root desde la carpeta
# del paquete desempacado (la que contiene src/ y despliegue/). Antes de tocar nada hace un respaldo
# nuevo; si la prueba de humo falla, no cambia ningun servicio. Lo deshace despliegue/restaurar.sh.
set -euo pipefail
MODO=${1:-actuar}
[[ "$MODO" == observar || "$MODO" == actuar ]] || { echo "modo invalido: $MODO" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "requiere root" >&2; exit 1; }
cd "$(dirname "$0")/.."
log() { echo "$(date '+%T') $*"; }

log "1. respaldo previo"
bash despliegue/respaldar.sh

log "2. codigo en /opt/controlador-radio (prueba de humo antes de activarlo)"
nuevo=$(mktemp -d /opt/.controlador-radio-XXXXXX)
trap 'rm -rf -- "${nuevo:?}" 2>/dev/null' EXIT   # si algo falla antes de activarlo, no queda basura
cp -r src/radio_dell "$nuevo/"
cp README.md "$nuevo/"
python3 -I -c "import sys; sys.path.insert(0, '$nuevo'); import radio_dell.demonio, radio_dell.__main__"
python3 -I -m compileall -q "$nuevo/radio_dell"
rm -rf -- /opt/controlador-radio.anterior
[[ -d /opt/controlador-radio ]] && mv /opt/controlador-radio /opt/controlador-radio.anterior
mv "$nuevo" /opt/controlador-radio && trap - EXIT
chmod -R go-w /opt/controlador-radio
install -m 0755 despliegue/controlador-radio /usr/local/bin/controlador-radio
install -m 0755 despliegue/respaldar.sh /usr/local/sbin/controlador-radio-respaldar
install -m 0755 despliegue/restaurar.sh /usr/local/sbin/controlador-radio-restaurar

log "3. configuracion (la existente se conserva) y unidades"
install -d -m 0755 /etc/controlador-radio
[[ -f /etc/controlador-radio/config.toml ]] || install -m 0644 despliegue/config.toml /etc/controlador-radio/
sed -i "s/^modo = .*/modo = \"$MODO\"/" /etc/controlador-radio/config.toml
install -m 0644 despliegue/controlador-radio.service despliegue/watchdog-itco.service /etc/systemd/system/
install -D -m 0644 despliegue/guardian-de-reserva.conf /etc/systemd/system/dell-net-guardian.service.d/reserva.conf
[[ -f despliegue/dell-net-guardian.sh ]] && install -m 0755 despliegue/dell-net-guardian.sh /usr/local/bin/

chmod -R go-rwx /var/lib/controlador-radio 2>/dev/null || true  # evidencia previa a UMask=0077
log "4. relevo: el escucha anterior se apaga (el demonio lo incluye); el guardian queda de reserva"
systemctl daemon-reload
systemctl disable --now dell-net-crash-listener.service 2>/dev/null || true
systemctl enable controlador-radio.service watchdog-itco.service
systemctl start watchdog-itco.service
systemctl reset-failed controlador-radio.service 2>/dev/null || true  # instalar es un arranque intencional
systemctl restart controlador-radio.service
sleep 8
systemctl is-active controlador-radio.service
controlador-radio diagnostico
log "instalado en modo $MODO"
