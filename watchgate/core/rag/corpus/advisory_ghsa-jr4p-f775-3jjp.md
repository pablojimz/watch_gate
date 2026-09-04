# Aviso: Malicious code in bamru (npm) (GHSA-jr4p-f775-3jjp)

## Resumen

This package presents itself as a "System binary configuration tool" — that is its entire manifest description, with keywords system, binary, util and config, an author of "SysDev", and no repository. What it actually installs is a concealed clipboard and screen harvester that elevates itself to Administrator. The chain was read directly. package/index.js probes for a Python interpreter and, if none is found, installs one along with libraries for clipboard access, screen capture, input synthesis and Windows UI Automation — without prompting. It then launches package/start_tool.vbs, whose ten lines are unambiguous: it builds a command to run pointer.py and executes it through ShellExecute with the verb "runas" and a window style of 0, which is to say with User Account Control elevation and no visible window. The author's own comments alongside that line say, in Hinglish, to run the tool silently in the background with admin rights. package/pointer.py then creates windows with blank titles, always-on-top, and with the window manager's decorations suppressed, so nothing appears in the interface. It reads the clipboard on a timer and, whenever the contents change and exceed a few characters, hands the text to a background thread that posts it to https://new-pointer.vercel.app/api. The same endpoint receives base64-encoded screen captures and text scraped from other applications' windows through UI Automation. The response is then typed back into whatever the user is focused on, with randomised delays to mimic human typing. Nothing about clipboard access, screen capture or network transmission appears in the package description, and there is no README. The deception is the decisive element: a tool that genuinely offered this functionality would say so, and would not need to hide its window, blank its title, or elevate itself silently. The three file digests cited were recomputed from the raw registry tarball rather than taken on trust. Note there is no install hook — the chain runs when a user invokes the command — but the package is the only publish from this account and holds the latest tag.

## Paquetes afectados

- `bamru` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-01T09:31:22Z
- Fuente: https://github.com/advisories/GHSA-jr4p-f775-3jjp

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `bamru`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
