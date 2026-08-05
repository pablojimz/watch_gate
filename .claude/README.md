# Registro de reglas Semgrep — resumen

Última actualización: 2026-08-04

Este documento resume el estado del catálogo de reglas Semgrep auditado en este repositorio (ver el detalle fila-por-fila en [rules-audit-report.md](rules-audit-report.md)). Estas reglas están pendientes de pasar a la Fase 2 (estructura `/SEMGREP` en `Repo-reglas-SEMGREP-y-YARA`).

## Total: 714 reglas aprobadas

| Fuente | Reglas | Descripción |
|---|---|---|
| [`trailofbits/semgrep-rules`](https://github.com/trailofbits/semgrep-rules) | 112 | Auditadas una por una (Fase 1): patrón, tests, severity/confidence, referencias. Licencia AGPLv3. 8 reglas del set original fueron rechazadas (bug demostrado, CWE incoherente, no eran de seguridad...). |
| Reglas propias | 49 | Escritas y validadas en 4 tandas para cubrir huecos de alto impacto no cubiertos por las fuentes de terceros (inyección SQL, deserialización insegura, command injection, etc. en varios lenguajes). Cada una con YAML + fixture de test propio, 100% verificadas con `semgrep --test`. |
| [`semgrep/semgrep-rules`](https://github.com/semgrep/semgrep-rules) (registro oficial) | 553 | Importación masiva de las ~2.080 reglas oficiales, filtradas automáticamente por: pasa `semgrep --test` + `category: security` + `confidence` distinto de LOW. No revisadas manualmente patrón a patrón (inviable a esa escala). |

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
| HCL / Terraform | 9 | 0 | 4 | **13** |
| Scala | 0 | 0 | 11 | **11** |
| C / C++ | 0 | 7 | 2 | **9** |
| Bash | 0 | 1 | 6 | **7** |
| C# / .NET | 0 | 7 | 0 | **7** |
| Dockerfile | 0 | 2 | 5 | **7** |
| Swift | 1 | 4 | 2 | **7** |
| Regex (cadenas de conexión) | 2 | 4 | 0 | **6** |
| JSON | 0 | 1 | 4 | **5** |
| Rust | 1 | 4 | 0 | **5** |
| Clojure | 0 | 1 | 3 | **4** |
| HTML | 0 | 1 | 1 | **2** |
| OCaml | 0 | 1 | 1 | **2** |
| **TOTAL** | **112** | **49** | **553** | **714** |

## Notas importantes

- Las 112 de trailofbits y las 49 propias pasaron una **revisión manual completa** (patrón, breadth, severity/confidence, referencias) además de `semgrep --test`.
- Las 553 del registro oficial solo pasaron el **criterio automático** (test + categoría + confidence) — no revisión de patrón individual.
- `apex`, `elixir` (registro oficial) y el análisis nativo de PowerShell requieren el motor Pro de pago de Semgrep (no disponible en este entorno); no están representados en el total.
- Categorías con reglas conocidas pendientes de recuperar si se invierte más esfuerzo: `generic/secrets` (225 reglas, detección de secretos), `python/lang` (134), `terraform` de AWS/Azure/GCP (345), `go/lang` (62) — todas descartadas en bloque porque un único fichero roto tumbaba el test de toda la carpeta.
