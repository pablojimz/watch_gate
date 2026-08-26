# Aviso: Malicious code in reqcrypt (PyPI) (GHSA-m6gg-ffj5-fxqh)

## Resumen

reqcrypt presents itself as a general-purpose HTTP client, but its internal PayloadProcessor unconditionally inspects every HTTP response for JSON keys named 'payloaddd', 'payload_gz', and 'payload_zlib', base64/gzip/zlib-decodes the associated values, and passes the decoded bytes to exec() inside the caller's Python process. This decode-and-exec path is wired into _process_response, which is invoked from every public verb (get/post/put/delete/patch/download/upload), so any server the caller contacts—or any network attacker able to tamper with a response—can push arbitrary Python code into the caller's process by adding one of those keys to a JSON body. In-source comments label the sinks as 'Hidden execution', and the behavior is not disclosed in the package's advertised API. Effect on any program using this library is a remote code execution channel driven by attacker-controlled or attacker-influenced HTTP responses.

The package contains a hidden backdoor. The promised functionality is an HTTP request library with some additional functions. On every usage, code secretly checks for the presence of specific fields in the response, and if they are found, their content is secretly executed.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-reqcrypt

Reasons (based on the campaign):

 - backdoor

## Paquetes afectados

- `reqcrypt` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-19T00:31:27Z
- Fuente: https://github.com/advisories/GHSA-m6gg-ffj5-fxqh

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `reqcrypt`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
