# Caso: ultralytics (PyPI, PYSEC-2024-154) — compromiso solo en el artefacto publicado

## Resumen

En diciembre de 2024, varias versiones del paquete `ultralytics` (librería
muy popular de visión por computador, modelos YOLO) publicadas en PyPI
contenían un minero de criptomonedas que se descargaba y ejecutaba al
instanciar un modelo YOLO. Lo más relevante del caso, según el propio aviso
oficial: **el código malicioso se inyectó en los artefactos de la
release publicados en PyPI, pero nunca estuvo presente en el repositorio
público de GitHub**.

## Vector de introducción

- El compromiso ocurrió en el **proceso de build/empaquetado y publicación**
  (probablemente en el pipeline de CI/CD que genera el paquete a partir del
  código fuente), no en el código fuente en sí — quien revisara el
  repositorio de GitHub, incluido cada PR y cada commit, no habría visto
  absolutamente nada anómalo, porque el código fuente estaba limpio.
- Es la contrapartida directa, a escala de un solo paquete PyPI en vez de
  una empresa entera, del caso SolarWinds: el límite de "solo podemos
  analizar diffs de código fuente" es el mismo, pero aquí ocurre en la
  cadena de distribución de un paquete Python que cualquier proyecto puede
  instalar como dependencia.
- Injectar el payload en el artefacto (el `.whl`/`.tar.gz` publicado) en
  vez de en el código fuente evita también cualquier revisión de código
  automatizada que analice el repositorio de GitHub directamente en vez
  del paquete finalmente instalado.

## Por qué es relevante para WatchGate

- Documenta honestamente una limitación estructural del sistema: WatchGate
  analiza diffs de **código fuente** (`NormalizedDiff`), no artefactos de
  build ya empaquetados — un ataque como este, igual que SolarWinds, cae
  fuera de lo que la capa semántica puede ver por diseño.
- Refuerza por qué la consulta en vivo a OSV (`gather_dependency_findings`,
  `lookup_package_registry`) es una capa de defensa independiente y
  necesaria: es la única señal de este corpus capaz de detectar este tipo
  de compromiso, precisamente porque no depende de leer código fuente.
- El objetivo del payload (minería de criptomonedas al instanciar un
  modelo YOLO) ilustra un patrón de activación distinto a los demás casos:
  no se dispara al importar el módulo, sino en un punto de uso normal y
  esperado de la librería, maximizando el número de máquinas afectadas sin
  requerir ninguna acción inusual del usuario.

Técnica MITRE ATT&CK relacionada: T1195.002 (Compromise Software Supply
Chain), sobre el eslabón de build/distribución en vez del código fuente.
