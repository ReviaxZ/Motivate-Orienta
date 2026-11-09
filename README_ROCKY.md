# Motivate para Rocky Linux (app Tcl/Tk)

App de escritorio que reemplaza `docker compose`. Corre como procesos nativos:

| Servicio | Que es | Puerto |
|---|---|---|
| Web principal | Pagina de Lucia (`/`), panel del psicologo (`/panel/`), Fabiola cobros (`/fabiola/`), API | **7878** (0.0.0.0) |
| Orientadoras Lucia y Fabiola | Agente de voz `orientador` en LiveKit | 8082 (salud interna) |
| Agente Fabiola (cobros) | Agente de voz `fabiola` en LiveKit | 8081 (salud interna) |
| Tunel ngrok | Opcional, URL publica https hacia el 7878 | 4040 (local) |

## Instalar

```bash
tar xzf motivate-rocky-1.0.0.tar.gz
cd motivate
sudo ./install.sh              # app + icono + menu + firewall 7878
sudo ./install.sh --service    # igual, y ademas arranca sin ventana al encender (systemd)
```

El instalador:
1. Instala Python 3.12 (o 3.11) con Tkinter desde los repos de Rocky (`python3.12-tkinter`).
2. Copia la app a `/opt/motivate` y crea el venv con todas las dependencias.
3. Crea el comando `motivate`, el icono y la entrada "Motivate" en Actividades.
4. Copia tu configuracion (con tus claves) a `~/.config/motivate/motivate.env` con permisos 600.
5. Abre `7878/tcp` en firewalld.
6. Deja instalado `motivate.service` (se habilita solo con `--service`).

Pensado para Rocky Linux 9 (Python 3.12). En Rocky 8 usa python3.11 si no hay 3.12; en Rocky 10 usa el python3 del sistema.

## Usar

- **Ventana:** Actividades -> Motivate, o `motivate` en una terminal.
  - *Servicios:* iniciar, detener y reiniciar cada servicio; reinicio automatico si uno se cae; enlaces a la web, al panel y a Fabiola; URL en la red y URL publica de ngrok.
  - *Registros:* salida en vivo de cada servicio.
  - *Sesiones y exportacion:* todas las entrevistas de la base SQLite; exportar a CSV o JSON, respaldar la base, importar la base de Docker y abrir los resultados de una sesion.
  - *Configuracion:* edita `motivate.env` con validacion de claves; "Guardar y reiniciar servicios" aplica los cambios.
- **Al cerrar la ventana** puedes detener los servicios o dejarlos corriendo; la web sigue en el 7878.
- **Terminal:**
  ```bash
  motivate --status            # estado
  motivate --start             # iniciar en segundo plano
  motivate --stop              # detener
  motivate --export-csv s.csv  # exportar sesiones
  ```
- **Servidor sin escritorio:** `sudo systemctl enable --now motivate` y `journalctl -u motivate -f`.

## Microfono desde otras computadoras

Los navegadores solo permiten el microfono en `https://` o en `localhost`. En el mismo equipo usa
`http://localhost:7878/`. Para que entren estudiantes desde otras computadoras usa ngrok (https), como antes,
o pon un proxy https (por ejemplo nginx con certificado) delante del 7878.

## Traer las sesiones de Docker

```bash
docker cp fabiola-web:/app/datos/orientador.db ~/orientador.db
docker compose down        # libera el puerto 7878
```
Despues, en la app: *Sesiones y exportacion -> Importar base (Docker)*. La base actual se respalda antes.

## Archivos

| Ruta | Contenido |
|---|---|
| `/opt/motivate/app` | App Tk (`motivate_app.py`) y gestor de servicios (`servicios.py`) |
| `/opt/motivate/proyecto` | Codigo original de Motivate (web, orientador, agent.py) |
| `~/.config/motivate/motivate.env` | Configuracion unica: LiveKit, Soniox, Cerebras, Fish Audio, Graph, correo, panel |
| `~/.local/share/motivate/datos/orientador.db` | Base SQLite con las entrevistas |
| `~/.local/share/motivate/logs/` | Registros de cada servicio |

## Cambios respecto a Docker

- `docker-compose.yml` + `orientador.env` -> un solo `motivate.env`.
- `WEB_INTERNAL_URL` pasa de `http://web:7878` a `http://127.0.0.1:7878` (lo pone la app).
- Los dos agentes ya no chocan en el puerto de salud 8081: se agrego `AGENT_HTTP_PORT` en `agent.py` y `orientador/agent.py` (unico cambio al codigo original).

## ngrok (opcional)

Descarga el binario para Linux desde ngrok.com/download y dejalo en `/usr/local/bin/ngrok`.
En *Configuracion* pon `NGROK_ENABLED=1` y `NGROK_AUTHTOKEN=...`; la URL publica aparece en *Servicios*.
Si usas ngrok, pon esa URL en `PUBLIC_BASE_URL` para que los correos lleven enlaces al panel.

## Desinstalar

```bash
sudo /opt/motivate/uninstall.sh           # conserva configuracion y sesiones
sudo /opt/motivate/uninstall.sh --purge   # borra todo
```
