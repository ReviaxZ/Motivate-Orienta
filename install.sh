#!/usr/bin/env bash
# =====================================================================
#  Instalador de Motivate para Rocky Linux 8 / 9 / 10 (tambien RHEL, Alma)
#
#  Uso:   sudo ./install.sh [--service] [--user NOMBRE] [--no-firewall] [--port N]
#
#   --service      ademas habilita motivate.service (arranca sin ventana al encender)
#   --user NOMBRE  usuario dueno de la configuracion y los datos (por defecto quien usa sudo)
#   --no-firewall  no abre el puerto en firewalld
#   --port N       puerto de la web principal (por defecto 7878)
# =====================================================================
set -euo pipefail

PREFIX=/opt/motivate
BIN=/usr/local/bin/motivate
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USUARIO="${SUDO_USER:-root}"
SERVICIO=0
FIREWALL=1
PUERTO=7878

while [ $# -gt 0 ]; do
  case "$1" in
    --service) SERVICIO=1 ;;
    --user) USUARIO="$2"; shift ;;
    --no-firewall) FIREWALL=0 ;;
    --port) PUERTO="$2"; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Opcion desconocida: $1"; exit 1 ;;
  esac
  shift
done

paso() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
aviso() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Ejecute con sudo:  sudo ./install.sh"; exit 1; }
id "$USUARIO" >/dev/null 2>&1 || { echo "El usuario '$USUARIO' no existe"; exit 1; }
HOME_U="$(getent passwd "$USUARIO" | cut -d: -f6)"
GRUPO_U="$(id -gn "$USUARIO")"

if [ -r /etc/os-release ]; then . /etc/os-release; fi
paso "Instalando Motivate en ${PRETTY_NAME:-Linux} para el usuario $USUARIO"

# ------------------------------------------------------------ 1. paquetes del sistema
paso "Paquetes del sistema (Python 3.12/3.11 + Tk)"
python_ok() {  # python con version >= 3.10 y tkinter
  "$1" -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}
PY=""
for c in python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && python_ok "$(command -v "$c")"; then PY="$(command -v "$c")"; break; fi
done
if [ -z "$PY" ]; then
  dnf -y install xdg-utils >/dev/null 2>&1 || true
  for v in 3.12 3.11; do
    if dnf -y install "python$v" "python$v-pip" "python$v-tkinter"; then
      if python_ok "$(command -v "python$v" 2>/dev/null || echo /nonexistent)"; then PY="$(command -v "python$v")"; break; fi
    fi
  done
fi
if [ -z "$PY" ]; then
  # Rocky 10: python3 ya es 3.12
  dnf -y install python3 python3-pip python3-tkinter || true
  python_ok "$(command -v python3)" && PY="$(command -v python3)"
fi
[ -n "$PY" ] || { echo "No se encontro Python >= 3.10 con Tkinter. Instale python3.12 y python3.12-tkinter."; exit 1; }
dnf -y install xdg-utils >/dev/null 2>&1 || true
echo "Python: $PY ($("$PY" --version 2>&1))"

# ------------------------------------------------------------ 2. archivos de la app
paso "Copiando la aplicacion a $PREFIX"
if systemctl is-active --quiet motivate 2>/dev/null; then systemctl stop motivate; fi
mkdir -p "$PREFIX"
rm -rf "$PREFIX/app" "$PREFIX/proyecto" "$PREFIX/assets" "$PREFIX/config" "$PREFIX/packaging"
cp -r "$SRC/app" "$SRC/proyecto" "$SRC/assets" "$SRC/packaging" "$PREFIX/"
mkdir -p "$PREFIX/config"
cp "$SRC/config/motivate.env.example" "$PREFIX/config/"     # plantilla sin claves
cp "$SRC/requirements-all.txt" "$SRC/README_ROCKY.md" "$SRC/uninstall.sh" "$PREFIX/"
find "$PREFIX" -name '__pycache__' -prune -exec rm -rf {} +
chmod 755 "$PREFIX/app/motivate_app.py" "$PREFIX/uninstall.sh"

# ------------------------------------------------------------ 3. entorno virtual
paso "Entorno virtual de Python y dependencias (puede tardar unos minutos)"
if [ ! -x "$PREFIX/venv/bin/python" ] || ! python_ok "$PREFIX/venv/bin/python"; then
  rm -rf "$PREFIX/venv"
  "$PY" -m venv "$PREFIX/venv"
fi
"$PREFIX/venv/bin/python" -m pip install --upgrade pip wheel >/dev/null
"$PREFIX/venv/bin/python" -m pip install -r "$PREFIX/requirements-all.txt"
"$PREFIX/venv/bin/python" -m compileall -q "$PREFIX/app" "$PREFIX/proyecto" >/dev/null || true

# ------------------------------------------------------------ 4. lanzador, icono y menu
paso "Lanzador, icono y entrada en el menu de aplicaciones"
cat > "$BIN" <<EOF
#!/bin/sh
exec "$PREFIX/venv/bin/python" "$PREFIX/app/motivate_app.py" "\$@"
EOF
chmod 755 "$BIN"
for s in 16 24 32 48 64 128 256 512; do
  install -Dm644 "$PREFIX/assets/motivate-$s.png" "/usr/share/icons/hicolor/${s}x${s}/apps/motivate.png"
done
install -Dm644 "$PREFIX/assets/motivate.svg" /usr/share/icons/hicolor/scalable/apps/motivate.svg
install -Dm644 "$PREFIX/packaging/motivate.desktop" /usr/share/applications/motivate.desktop
gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q /usr/share/applications 2>/dev/null || true

# ------------------------------------------------------------ 5. configuracion del usuario
paso "Configuracion de $USUARIO"
CFG_DIR="$HOME_U/.config/motivate"
CFG="$CFG_DIR/motivate.env"
install -d -o "$USUARIO" -g "$GRUPO_U" -m 700 "$CFG_DIR"
install -d -o "$USUARIO" -g "$GRUPO_U" -m 755 "$HOME_U/.local/share/motivate"
if [ -f "$CFG" ]; then
  echo "Se conserva la configuracion existente: $CFG"
else
  ORIGEN="$SRC/config/motivate.env"
  [ -f "$ORIGEN" ] || ORIGEN="$SRC/config/motivate.env.example"
  install -o "$USUARIO" -g "$GRUPO_U" -m 600 "$ORIGEN" "$CFG"
  echo "Configuracion creada: $CFG (permisos 600)"
fi
if [ "$PUERTO" != "7878" ]; then
  sed -i "s/^MOTIVATE_PORT=.*/MOTIVATE_PORT=$PUERTO/" "$CFG"
else
  PUERTO="$(sed -n 's/^MOTIVATE_PORT=//p' "$CFG" | tail -n1)"; PUERTO="${PUERTO:-7878}"
fi

# ------------------------------------------------------------ 6. firewall
if [ "$FIREWALL" -eq 1 ] && command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  paso "Abriendo el puerto $PUERTO/tcp en firewalld"
  firewall-cmd --quiet --permanent --add-port="$PUERTO/tcp"
  firewall-cmd --quiet --reload
fi

# ------------------------------------------------------------ 7. servicio systemd (opcional)
sed -e "s#__USUARIO__#$USUARIO#g" -e "s#__GRUPO__#$GRUPO_U#g" -e "s#__HOME__#$HOME_U#g" \
  "$PREFIX/packaging/motivate.service" > /etc/systemd/system/motivate.service
systemctl daemon-reload
if command -v restorecon >/dev/null 2>&1; then restorecon -R "$PREFIX" "$BIN" /etc/systemd/system/motivate.service 2>/dev/null || true; fi
if [ "$SERVICIO" -eq 1 ]; then
  paso "Habilitando motivate.service (sin ventana)"
  systemctl enable --now motivate
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
paso "Listo"
cat <<EOF
  Abrir la app:      busque "Motivate" en Actividades, o ejecute:  motivate
  Web principal:     http://${IP:-localhost}:$PUERTO/
  Panel psicologo:   http://${IP:-localhost}:$PUERTO/panel/   (usuario: panel)
  Configuracion:     $CFG
  Sin ventana:       sudo systemctl enable --now motivate
  Estado (terminal): motivate --status
EOF
