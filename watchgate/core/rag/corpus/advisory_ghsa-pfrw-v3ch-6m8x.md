# Aviso: Malicious code in python-walletlibr-v (PyPI) (GHSA-pfrw-v3ch-6m8x)

## Resumen

python-walletlibr-v is a wallet-lookalike PyPI package that ships no wallet functionality — only a stub hello() that prints 'Hello from my custom library!' and placeholder author metadata (__author__ = 'Your Name'). Its setup.py registers a CustomInstall command that, on Windows at pip install time, writes a.bat file into %TEMP%, spawns a new cmd.exe console to execute it via subprocess.Popen(['cmd.exe','/k', bat_path], CREATE_NEW_CONSOLE), and calls os.system('calc'). Arbitrary local command execution fires automatically during pip install on Windows hosts, unrelated to any advertised functionality.

## Paquetes afectados

- `python-walletlibr-v` (pip), versiones afectadas: = 0.7.9

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-pfrw-v3ch-6m8x

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `python-walletlibr-v`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
