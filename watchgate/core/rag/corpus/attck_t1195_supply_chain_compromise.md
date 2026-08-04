# MITRE ATT&CK T1195 — Supply Chain Compromise

## Descripción

El adversario manipula productos o mecanismos de entrega de software antes de
que lleguen al consumidor final, con el objetivo de comprometer datos o
sistemas a través de la cadena de suministro en lugar de atacar directamente
al objetivo. Incluye las sub-técnicas:

- **T1195.001** — Compromiso de dependencias y herramientas de desarrollo
  (compiladores, librerías compartidas, paquetes de gestores como npm/PyPI).
- **T1195.002** — Compromiso de software de cadena de suministro: modificar
  código fuente, binarios de distribución o actualizaciones legítimas de una
  aplicación para incluir funcionalidad maliciosa.
- **T1195.003** — Compromiso de infraestructura de cadena de suministro
  (repositorios, sistemas de build/CI, servidores de distribución de
  paquetes).

## Patrones observables en un diff de PR

- Adición o modificación de dependencias declaradas (`package.json`,
  `requirements.txt`, `Cargo.toml`, `PKGBUILD`) sin relación aparente con el
  resto del cambio funcional del PR.
- Scripts de instalación/build (`postinstall`, `preinstall`, funciones
  `pre_install`/`post_install` de un `PKGBUILD`, `setup.py`) que ejecutan
  código de red o escriben en rutas del sistema fuera del árbol del proyecto.
- Cambios en ficheros de configuración de CI/CD (`.github/workflows/*.yml`,
  `Jenkinsfile`, `.gitlab-ci.yml`) que alteran qué variables de entorno o
  secretos están accesibles durante el build.
- Nombres de paquete a distancia de edición muy pequeña de un paquete popular
  legítimo (typosquatting), especialmente si la versión declarada es reciente
  y el paquete tiene pocas descargas o pocos días de antigüedad.

## Relevancia para WatchGate

Esta técnica es el paraguas bajo el que caen la mayoría de los casos que
WatchGate intenta detectar (xz-utils, Atomic Arch, prt-scan). Las capas de
**dependencias** y **estática** cubren los indicadores mecánicos (paquete
nuevo/typosquat, patrón de red en script de build); la capa **semántica**
debe evaluar si la *combinación* de esos indicadores tiene sentido para el
propósito declarado del cambio.
