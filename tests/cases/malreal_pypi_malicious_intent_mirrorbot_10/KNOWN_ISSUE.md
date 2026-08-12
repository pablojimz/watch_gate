# Ground truth dudoso: desajuste de categoría, no fichero equivocado

A diferencia de otros casos `malreal_*` documentados en
`docs/evaluacion_ia/ground_truth_dudoso_dataset_datadog.md`, aquí el
fichero del fixture (`after/direct_link_generator.py`) SÍ coincide con el
fichero real del ZIP de origen del dataset DataDog (mismo tamaño, mismo
contenido) -- no falta ningún payload por muestreo incorrecto.

Se revisó el ZIP completo (78 ficheros Python del paquete `mirrorbot`)
buscando exfiltración, credenciales robadas, ejecución de comandos ocultos
o cualquier otro indicio de ataque a la cadena de suministro: no se
encontró nada. Es código real y funcional de un bot de Telegram que genera
enlaces de descarga directa desde servicios de alojamiento de ficheros
(mediafire, uptobox, 1fichier, terabox...), usando `cloudscraper`/
`lk21.Bypass` para esquivar captchas/protecciones anti-bot.

Hipótesis: el dataset DataDog lo etiqueta `malicious_intent` por su
propósito (facilita descargar/redistribuir contenido de servicios que no
lo permiten -- un problema de ToS/copyright), no por el propio código.
Ese criterio no coincide con el de WatchGate (ataques a la cadena de
suministro, backdoors, exfiltración, RCE). `expected.json` no se ha
tocado a propósito -- no hay una corrección obvia y unilateral que hacer
aquí, a diferencia de los casos con fichero equivocado.

Ver el análisis completo en
`docs/evaluacion_ia/ground_truth_dudoso_dataset_datadog.md`.
