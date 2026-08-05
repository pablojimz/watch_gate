# Registro de reglas Semgrep — resumen

Última actualización: 2026-08-04

Este documento resume el estado del catálogo de reglas Semgrep auditado en este repositorio (ver el detalle fila-por-fila en [rules-audit-report.md](rules-audit-report.md)). Estas reglas están pendientes de pasar a la Fase 2 (estructura `/SEMGREP` en `Repo-reglas-SEMGREP-y-YARA`).

## ⚠️ Problema de licencia detectado (resuelto)

Las 553 reglas del registro oficial de Semgrep están bajo la **Semgrep Rules License v1.0**, que **prohíbe expresamente la redistribución** ("no puedes distribuir las reglas, ni ponerlas a disposición de otros"), incluso en un repo privado con acceso de lectura a terceros. GitHub tampoco permite restringir el acceso de lectura a una sola carpeta dentro de un mismo repo (los permisos son a nivel de repo completo), así que aislarlas en una subcarpeta no las protege.

**Decisión**: esas 553 reglas **no se incluyen** en el registro redistribuible. En su lugar, se reescribió desde cero un subconjunto de 15 reglas de alto impacto (vulnerabilidades con CVE real conocido, en Django/Flask/Express/Spring/Rails) como obra independiente — sin partir del código de las reglas originales — lo que las libera de la restricción de licencia. Detalle completo del mapeo regla↔CVE en [vulnerability-mapping.md](vulnerability-mapping.md).

## ✅ Actualización: las reglas ya están instaladas permanentemente

Todo lo aprobado (ver tabla siguiente) está copiado de forma permanente en [`rules/semgrep/`](../rules/semgrep/) dentro de este mismo repositorio (`third-party/<fuente>/` + `custom/`), con [`NOTICE.md`](../rules/semgrep/NOTICE.md) explicando las licencias y [`registry.json`](../rules/semgrep/registry.json) como índice completo. Verificado con `semgrep --test` tras la instalación.

## Total: 778 reglas aprobadas y redistribuibles

| Fuente | Reglas | Licencia | Descripción |
|---|---|---|---|
| [`trailofbits/semgrep-rules`](https://github.com/trailofbits/semgrep-rules) | 112 | AGPL-3.0 | Auditadas una por una (Fase 1): patrón, tests, severity/confidence, referencias. 8 reglas del set original fueron rechazadas (bug demostrado, CWE incoherente, no eran de seguridad...). |
| Reglas propias | 64 | Propia (a definir) | Escritas y validadas en 5 tandas para cubrir huecos de alto impacto no cubiertos por las fuentes de terceros (inyección SQL, deserialización insegura, command injection, SSTI, etc. en varios lenguajes y frameworks, incluyendo vulnerabilidades con CVE real como Log4Shell). Cada una con YAML + fixture de test propio, 100% verificadas con `semgrep --test`. |
| [`opengrep/opengrep-rules`](https://github.com/opengrep/opengrep-rules) | 556 | LGPL-2.1 + Commons Clause | Fork abierto (Dic-2024) del registro oficial de Semgrep, **sin** la restricción de redistribución del original — solo prohíbe vender el software. Filtro automático: pasa test + `category: security` + `confidence` no-LOW. Recupera contenido que el registro oficial no pudo entregar por licencia, incluyendo 360 reglas de Terraform y 175 de detección de secretos (gitleaks). |
| [`elttam/semgrep-rules`](https://github.com/elttam/semgrep-rules) | 6 | MIT | Firma de pentesting; mismo filtro automático. |
| [`0xdea/semgrep-rules`](https://github.com/0xdea/semgrep-rules) | 40 | MIT | Reglas de investigación de vulnerabilidades en C/C++ (Marco Ivaldi); mismo filtro automático. |
| ~~[`semgrep/semgrep-rules`](https://github.com/semgrep/semgrep-rules) (registro oficial)~~ | ~~553~~ **0 instaladas** | Semgrep Rules License v1.0 | Se probaron y documentaron 553 reglas que pasaban los criterios de calidad, pero **se excluyeron por incompatibilidad de licencia** (prohíbe redistribución). `opengrep/opengrep-rules` (arriba) cubre gran parte del mismo contenido sin esa restricción. |

### Fuentes descartadas (0 reglas aportadas)

| Fuente | Motivo |
|---|---|
| [`j3ssie/curated-semgrep-rules`](https://github.com/j3ssie/curated-semgrep-rules) (821 reglas) | Su única carpeta que pasa test es una copia desactualizada de trailofbits (ya cubierta). El resto (0xdea, android-security, dgryski, elttam, federicodotta, gitlab, hashicorp, kondukto, ligurio, semgrep-smart-contracts) falla `semgrep --test` a nivel de carpeta. |
| [`tuannq2299/semgrep-rules`](https://github.com/tuannq2299/semgrep-rules) (87 reglas) | Sus 2 carpetas (Java, C#) fallan; incluye ficheros YAML que ni siquiera parsean. |
| [`iosifache/semgrep-rules-manager`](https://github.com/iosifache/semgrep-rules-manager) | No es un repo de reglas, es una herramienta que descarga de 14 fuentes de terceros. 11 de esas 14 ya estaban cubiertas (registro oficial, trailofbits, o duplicadas dentro de j3ssie). Las 3 fuentes realmente nuevas (`akabe1`, `atlassian-labs`, `apiiro`) se probaron: 2 no tienen ningún fichero de test y la tercera falla 0/68 tests — las 3 rechazadas. |

## Desglose por lenguaje

| Lenguaje | trailofbits | Propias | Oficial (bulk) | **Total** |
|---|---:|---:|---:|---:|
| Python | 20 | 2 | 159 | **181** |
| JavaScript / TypeScript | 9 | 1 | 100 | **110** |
| Java / Kotlin | 1 | 4 | 84 | **89** |
| Ruby | 14 | 1 | 53 | **68** |
| Generic (comandos shell, PowerShell...) | 14 | 3 | 39 | **56** |
| YAML | 24 | 0 | 28 | **52** |
| Go | 17 | 0 | 27 | **44** |
| PHP | 0 | 5 | 24 | **29** |
|
| **TOTAL** | **112** | **49** | **553** | **714** |

## Notas importantes

- Las 112 de trailofbits y las 49 propias pasaron una **revisión manual completa** (patrón, breadth, severity/confidence, referencias) además de `semgrep --test`.
- Las 553 del registro oficial solo pasaron el **criterio automático** (test + categoría + confidence) — no revisión de patrón individual.
- `apex`, `elixir` (registro oficial) y el análisis nativo de PowerShell requieren el motor Pro de pago de Semgrep (no disponible en este entorno); no están representados en el total.
- Categorías con reglas conocidas pendientes de recuperar si se invierte más esfuerzo: `generic/secrets` (225 reglas, detección de secretos), `python/lang` (134), `terraform` de AWS/Azure/GCP (345), `go/lang` (62) — todas descartadas en bloque porque un único fichero roto tumbaba el test de toda la carpeta.
