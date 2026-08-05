# Reglas por lenguaje

Desglose de las **778 reglas** instaladas en `rules/semgrep/` (ver [`NOTICE.md`](NOTICE.md) para las fuentes y licencias, [`registry.json`](registry.json) para el índice completo id-por-id).

| Lenguaje | trailofbits | opengrep | elttam | 0xdea | propias | **Total** |
|---|---:|---:|---:|---:|---:|---:|
| Python | 20 | 124 | 0 | 0 | 7 | **151** |
| Java / Kotlin | 0 | 87 | 0 | 0 | 0 | **87** |
| JavaScript / TypeScript | 9 | 71 | 0 | 0 | 4 | **84** |
| HCL / Terraform | 9 | 61 | 0 | 0 | 0 | **70** |
| Go | 17 | 50 | 2 | 0 | 0 | **69** |
| Ruby | 14 | 48 | 0 | 0 | 3 | **65** |
| YAML | 24 | 21 | 3 | 0 | 1 | **49** |
| C / C++ | 0 | 0 | 0 | 40 | 7 | **47** |
| Generic (shell, PowerShell...) | 14 | 20 | 1 | 0 | 3 | **38** |
| PHP | 0 | 22 | 0 | 0 | 5 | **27** |
| Solidity | 0 | 21 | 0 | 0 | 0 | **21** |
| C# / .NET | 0 | 17 | 0 | 0 | 7 | **24** |
| Scala | 0 | 12 | 0 | 0 | 0 | **12** |
| Swift | 1 | 2 | 0 | 0 | 4 | **7** |
| Regex (cadenas de conexión) | 2 | 0 | 0 | 0 | 4 | **6** |
| Rust | 1 | 0 | 0 | 0 | 4 | **5** |
| Clojure | 0 | 3 | 0 | 0 | 1 | **4** |
| JSON | 0 | 3 | 0 | 0 | 1 | **4** |
| Bash | 0 | 1 | 0 | 0 | 1 | **2** |
| HTML | 0 | 1 | 0 | 0 | 1 | **2** |
| OCaml | 0 | 1 | 0 | 0 | 1 | **2** |
| Dockerfile | 0 | 0 | 0 | 0 | 2 | **2** |
| **TOTAL** | **112** | **556** | **6** | **40** | **64** | **778** |

## Los 5 lenguajes con más cobertura

1. **Python** (151) — inyección de comandos, deserialización insegura (pickle), SSRF, SSTI en Flask, XSS/SQLi en Django
2. **Java/Kotlin** (87) — mayormente del fork opengrep (criptografía, deserialización, Spring)
3. **JavaScript/TypeScript** (84) — Express, JWT, CORS, XSS en múltiples frameworks (Angular, React, Vue...)
4. **HCL/Terraform** (70) — el hueco que dejó el registro oficial (falló su test) lo cubre casi entero `opengrep`
5. **Go** (69) — condiciones de carrera, mutex, deserialización insegura de tags

## Notas

- **C/C++** es el único lenguaje sin ninguna aportación de trailofbits ni opengrep en este desglose — toda su cobertura viene de `0xdea` (investigador de vulnerabilidades en C, 40 reglas) y de las 7 propias (buffer overflow, use-after-free, double-free, TOCTOU, integer overflow, command injection).
- **C#/.NET** y **Rust** siguen siendo los lenguajes con más peso relativo de reglas propias frente a terceros (7 de 24, y 4 de 5 respectivamente).
- El desglose completo por regla individual (id, ruta exacta, fuente) está en [`registry.json`](registry.json).
