#!/usr/bin/env bash
# Desinstala Motivate.   sudo ./uninstall.sh [--purge]
#   --purge  borra tambien la configuracion y los datos del usuario (sesiones, registros)
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Ejecute con sudo"; exit 1; }
PURGE=0; [ "${1:-}" = "--purge" ] && PURGE=1
USUARIO="${SUDO_USER:-root}"
HOME_U="$(getent passwd "$USUARIO" | cut -d: -f6)"

systemctl disable --now motivate 2>/dev/null || true
sudo -u "$USUARIO" /usr/local/bin/motivate --stop >/dev/null 2>&1 || true
rm -f /etc/systemd/system/motivate.service
systemctl daemon-reload || true

PUERTO="$(sed -n 's/^MOTIVATE_PORT=//p' "$HOME_U/.config/motivate/motivate.env" 2>/dev/null | tail -n1)"
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  firewall-cmd --quiet --permanent --remove-port="${PUERTO:-7878}/tcp" 2>/dev/null || true
  firewall-cmd --quiet --reload || true
fi

rm -f /usr/local/bin/motivate /usr/share/applications/motivate.desktop
rm -f /usr/share/icons/hicolor/*/apps/motivate.png /usr/share/icons/hicolor/scalable/apps/motivate.svg
gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor 2>/dev/null || true
rm -rf /opt/motivate

if [ "$PURGE" -eq 1 ]; then
  rm -rf "$HOME_U/.config/motivate" "$HOME_U/.local/share/motivate"
  echo "Motivate desinstalado, incluidos configuracion y datos."
else
  echo "Motivate desinstalado. Se conservan $HOME_U/.config/motivate y $HOME_U/.local/share/motivate"
fi
