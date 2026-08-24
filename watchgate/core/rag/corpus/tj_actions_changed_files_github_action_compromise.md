# Caso: tj-actions/changed-files — GitHub Action comprometida (CVE-2025-30066)

## Resumen

En marzo de 2025 se descubrió que `tj-actions/changed-files`, una GitHub
Action de terceros usada en más de 23.000 repositorios para detectar qué
ficheros cambia un PR, había sido comprometida: el atacante modificó
**todas las etiquetas de versión existentes** (`v1` a `v46`, incluidas
versiones ya publicadas hace tiempo) para que apuntaran a un commit
malicioso nuevo. Cualquier workflow que referenciara la Action por
etiqueta (`uses: tj-actions/changed-files@v45`, el patrón habitual, en vez
de fijar un SHA de commit exacto) empezó a ejecutar código malicioso sin
que nadie hubiera tocado su propio `.github/workflows/*.yml`.

## Vector de introducción

- El payload inyectado era una función Node.js con instrucciones
  codificadas en base64 que descargaba un script en Python. Ese script
  escaneaba la memoria del runner de GitHub Actions en busca de
  credenciales (tokens, claves de API, secretos de despliegue) y las
  volcaba **directamente en los logs del propio workflow** — visibles para
  cualquiera con acceso de lectura al repositorio si este era público, sin
  necesidad de exfiltración a un servidor externo.
- El acceso inicial no fue una vulnerabilidad de GitHub: el atacante
  comprometió un token de acceso personal (PAT) de un bot con permisos de
  escritura sobre el repositorio de la Action. Investigaciones posteriores
  apuntan a que ese token pudo obtenerse a través de otra Action
  comprometida en cadena (`reviewdog/action-setup`, CVE-2025-30154),
  ilustrando que la cadena de confianza de una Action incluye las
  dependencias/Actions que ESA Action usa internamente.
- El vector clave para detección: reescribir una etiqueta git ya publicada
  para que apunte a un commit distinto es indetectable si solo se confía
  en el nombre de la etiqueta (`@v45`) — un SHA de commit fijado
  explícitamente (`@a1b2c3d...`) no se ve afectado por este tipo de
  reescritura, precisamente la mitigación que GitHub y la comunidad
  recomendaron tras el incidente.

## Por qué es relevante para WatchGate

- Ataque directo a la superficie que WatchGate vigila: un cambio en
  `.github/workflows/*.yml` que introduce o actualiza una referencia a una
  Action de terceros por etiqueta mutable, en vez de por SHA fijo, es
  exactamente el patrón de riesgo que este caso demuestra como explotable
  en producción, no solo en teoría.
- El propio código de la Action comprometida no vivía en el repositorio
  que sufría el ataque — vivía en una dependencia externa de CI/CD. Un
  diff que "solo" añade o actualiza un `uses:` en un workflow parece
  trivial, pero concede ejecución de código arbitrario con acceso a los
  secretos del repositorio.
- Técnica MITRE ATT&CK relacionada: T1195.002 (Compromise Software Supply
  Chain), T1584 (Compromise Infrastructure — el token/Action previa en la
  cadena).
