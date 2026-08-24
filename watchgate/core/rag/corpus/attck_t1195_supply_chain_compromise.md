# MITRE ATT&CK T1195 — Supply Chain Compromise

**Táctica:** Initial Access. **Plataformas:** Linux, SaaS, Windows, macOS.
**Versión:** 1.7 (última modificación: 24 de octubre de 2025).

## Descripción

El adversario manipula productos o mecanismos de entrega de software antes de
que lleguen al consumidor final, con el objetivo de comprometer datos o
sistemas a través de la cadena de suministro en lugar de atacar directamente
al objetivo. Esto puede ocurrir en múltiples etapas: manipulación de
herramientas de desarrollo, compromiso de repositorios de código fuente,
manipulación del mecanismo de actualización, imágenes de sistema infectadas,
sustitución de software legítimo, venta de producto falsificado, o
interceptación de envíos físicos.

Aunque cualquier componente puede ser objetivo, MITRE señala explícitamente
que "los adversarios que buscan conseguir ejecución de código se han
centrado a menudo en añadidos maliciosos a software legítimo dentro de
canales de distribución o actualización". El atacante puede limitar el
objetivo a víctimas específicas o distribuir ampliamente con seguimiento
selectivo después. Las dependencias open-source populares son un objetivo
frecuente precisamente porque propagan el código malicioso a todas las
aplicaciones que dependen de ellas.

## Sub-técnicas

- **T1195.001** — Compromise Software Dependencies and Development Tools
  (ver `attck_t1195_001_compromise_dependencies.md` para el detalle
  completo de esta sub-técnica).
- **T1195.002** — Compromise Software Supply Chain: modificar código fuente,
  binarios de distribución o actualizaciones legítimas de una aplicación
  para incluir funcionalidad maliciosa.
- **T1195.003** — Compromise Hardware Supply Chain.

## Ejemplos de procedimiento (grupos y campañas reales documentados por MITRE)

- **Ember Bear (G1003)** — "Comprometió proveedores de tecnología de la
  información y desarrolladores de software que daban servicio a objetivos
  de interés, construyendo el acceso inicial a las víctimas finales al
  menos en parte a través del compromiso de esos proveedores de servicio."
- **Lumma Stealer (S1213)** — Distribuido a través de descargas de software
  "crackeado" por múltiples vectores.
- **OilRig (G0049)** — "Aprovechó organizaciones comprometidas para llevar
  a cabo ataques a la cadena de suministro contra entidades
  gubernamentales."
- **Raccoon Stealer (S1148)** — Distribuido a través de canales de descarga
  de software "crackeado".
- **Sandworm Team (G0034)** — "Alojó versiones comprometidas de instaladores
  de software legítimo en foros para conseguir acceso inicial no dirigido."

## Mitigaciones (MITRE)

| ID | Mitigación | Descripción |
|---|---|---|
| M1013 | Application Developer Guidance | Fijar las dependencias a versiones concretas en vez de tomar siempre la última en el build. |
| M1046 | Boot Integrity | Verificar la integridad del SO y del mecanismo de arranque mediante secure boot. |
| M1033 | Limit Software Installation | Exigir que los desarrolladores usen repositorios internos verificados en vez de externos sin control. |
| M1051 | Update Software | Gestión de parches que revise dependencias sin usar, vulnerables o sin mantenimiento. |
| M1018 | User Account Management | Restringir permisos de ejecución de software para minimizar el riesgo de propagación. |
| M1016 | Vulnerability Scanning | Monitorización continua con revisión de código automática y manual. |

## Estrategia de detección (MITRE)

- **DET0537/AN1480** — Vigilar fuentes de software atípicas, discrepancias
  de firma, escrituras de binarios inesperadas, carga de módulos sin
  firmar.
- **DET0537/AN1481** — Repositorios de paquetes no aprobados, paquetes sin
  firmar, modificaciones de la variable `PATH`, procesos hijo inesperados.
- **DET0537/AN1482** — Fuentes de paquetes/notarización atípicas, avisos de
  Gatekeeper, sustitución de rutas en `/Applications`, generación de
  procesos hijo sin firmar.

## Patrones observables en un diff de PR (nota WatchGate)

Adición/modificación de dependencias (`package.json`, `requirements.txt`,
`Cargo.toml`, `PKGBUILD`) sin relación con el resto del cambio; scripts de
instalación (`postinstall`, `pre_install`) que ejecutan código de red;
cambios en `.github/workflows/*.yml`/`Jenkinsfile`/`.gitlab-ci.yml` que
alteran qué secretos son accesibles durante el build; nombres de paquete a
distancia de edición pequeña de uno popular (typosquatting). Las capas de
**dependencias** y **estática** cubren los indicadores mecánicos; la capa
**semántica** evalúa si la combinación tiene sentido para el propósito
declarado del cambio.
