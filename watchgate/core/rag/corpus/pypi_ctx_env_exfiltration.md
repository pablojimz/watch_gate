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

## Por qué es relevante para WatchGate

- Mismo grupo de técnicas MITRE ATT&CK que otros casos de este corpus:
  T1195.002 (Compromise Software Supply Chain) y T1552 (Unsecured
  Credentials, vía variables de entorno) — la exfiltración de secretos de
  entorno es un objetivo recurrente en paquetes maliciosos de PyPI/npm.
- Para la capa semántica: cualquier código que recolecte `os.environ` (o
  equivalentes: `process.env`, `ENV` de Ruby) y lo envíe por red — aunque sea
  en un método aparentemente inocuo de una clase de uso normal, no solo en un
  script de instalación — es una señal de intención maliciosa por sí sola,
  con independencia de la reputación aparente del paquete o de su autor.
- Refuerza que la reputación heredada (un paquete con historial y descargas
  reales) no es garantía: un paquete legítimo puede ser tomado por secuestro
  de cuenta/infraestructura sin que cambie su nombre ni su historial visible.

Fuente pública: GHSA-4g82-3jcr-q52w (GitHub Advisory Database, revisado).
