# Aviso: Malicious code in timeweave (PyPI) (GHSA-pjqm-mp65-gqw6)

## Resumen

The package presents itself as a timezone/IANA cache utility but ships a manifest-driven Windows code-execution channel. updater.py defines DEFAULT_DB_URL = "https://timezone.api.globaltimedata.com/latest/db.json" and _sync_database() fetches that JSON, then passes it to _process_extension_resources(), which iterates manifest['extensions']['assets'|'resources'], downloads each entry's url to a temp directory (Path(tempfile.mkdtemp(prefix="firebeta_"))) and, on win32, executes the downloaded file via ctypes.windll.kernel32.WinExec(cmd, 0) with attacker-supplied args. This flow is reachable from ordinary library use: __init__.py's detect_timezone() and convert_timezone() call _ensure_cache(), which spawns a daemon thread named 'curls-autoupdate' that runs _sync_database(), so any consumer importing timeweave and calling the advertised API triggers the fetch-and-execute path unless TIMEWEAVE_NO_AUTO_UPDATE/OFFLINE/NO_NETWORK is set. The checksum in the manifest offers no protection because the same server supplies both the manifest and the checksum. Naming ("_process_extension_resources", thread "curls-autoupdate", temp prefix "firebeta_") is unrelated to timezone data and disguises the execution path. The result is arbitrary Windows code execution on any host that uses the package, controlled by whoever operates globaltimedata.com.

## Paquetes afectados

- `timeweave` (pip), versiones afectadas: = 1.6.0
- `timeweave` (pip), versiones afectadas: = 1.9.0
- `timeweave` (pip), versiones afectadas: = 1.7.0
- `timeweave` (pip), versiones afectadas: = 1.4.0
- `timeweave` (pip), versiones afectadas: = 1.8.0
- `timeweave` (pip), versiones afectadas: = 1.2.0
- `timeweave` (pip), versiones afectadas: = 1.1.0
- `timeweave` (pip), versiones afectadas: = 1.3.0
- `timeweave` (pip), versiones afectadas: = 1.0.0
- `timeweave` (pip), versiones afectadas: = 1.5.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T06:31:40Z
- Fuente: https://github.com/advisories/GHSA-pjqm-mp65-gqw6

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `timeweave`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
