# Caso: robo de variables de entorno vía el paquete `ctx` (PyPI, GHSA-4g82-3jcr-q52w)

## Resumen

En mayo de 2022, el proyecto `ctx` en PyPI fue tomado tras un secuestro de la
cuenta del mantenedor original (dominio de contacto expirado y re-registrado
por el atacante) y sustituido por una versión maliciosa. El código malicioso
recolectaba `os.environ.items()` cada vez que se instanciaba la clase `Ctx`
—es decir, en el uso normal de la librería, no en un paso especial— y enviaba
esas variables de entorno codificadas en base64 como parámetro de consulta a
una aplicación en `hxxps://anti-theft-web[.]herokuapp[.]com` (dominio
histórico de 2022, ya inactivo; se referencia desactivado, como IOC de un
caso cerrado, no como enlace real). Quien instalase el
paquete entre el 14 y el 24 de mayo de 2022 con secretos en variables de
entorno típicas (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, tokens de CI)
quedaba expuesto.

## Vector de introducción

- No fue un ataque de *typosquatting* (nombre parecido a otro paquete): `ctx`
  era el paquete legítimo, con historial y descargas reales, tomado por
  secuestro de cuenta — el mismo patrón de "reputación heredada" que XZ Utils,
  pero por compromiso de infraestructura en vez de ingeniería social a largo
  plazo.
- El payload se ejecutaba en tiempo de *import/uso normal* de la librería
  (constructor de una clase de uso común), no en un hook de instalación
  aislado (`setup.py`/`post_install`) que un revisor pudiera aislar más
  fácilmente como sospechoso.
- La exfiltración iba disfrazada de tráfico de red aparentemente inocuo (una
  petición HTTP con un parámetro base64), no una escritura a disco ni un
  `curl | bash` evidente.

## Patrón a vigilar

Código que recolecta `os.environ` (o `process.env`, `ENV` de Ruby) y lo
envía por red, en un método aparentemente normal de uso, no solo en un
script de instalación.

Técnica MITRE ATT&CK relacionada: T1195.002 (Compromise Software Supply
Chain), T1552 (Unsecured Credentials).

Fuente pública: GHSA-4g82-3jcr-q52w (GitHub Advisory Database, revisado).
