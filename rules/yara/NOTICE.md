# NOTICE

Este directorio contiene reglas YARA derivadas de una única fuente de terceros,
bajo una licencia distinta a la del resto del repositorio (ver [`LICENSE`](../../LICENSE)
raíz, MIT). Lee esta nota antes de añadir, copiar o redistribuir cualquier
contenido de aquí.

## Fuente y licencia

| Origen | Licencia | Categorías | Reglas |
|---|---|---|---|
| [Yara-Rules/rules](https://github.com/Yara-Rules/rules) | **GPL-2.0** (ver [`LICENSE`](LICENSE) en este mismo directorio, copia íntegra del original) | `antidebug_antivm/`, `exploit_kits/`, `packers/`, `utils/`, `webshells/` | 10.107 |

El texto completo de la GPLv2 se distribuye junto con las reglas en
[`LICENSE`](LICENSE), tal y como exige la licencia. Cada regla conserva,
cuando la fuente original la incluía, su `meta.author` original.

## Qué se modificó respecto a la fuente original

Cada `.yar` de este directorio es una **obra derivada**, no una copia
literal: se generan automáticamente (`scripts/generate_scored_yara.py`, en
el repo privado `pablojimz/Repo-reglas-SEMGREP-y-YARA`) a partir del cuerpo
real (`strings:`/`condition:`) de la regla original, con campos adicionales
inyectados en su bloque `meta:`:

- `severity_score`, `confidence_score`, `exploitability_score`, `risk_score`
  — puntuación de riesgo propia (metodología en
  `.claude/criterioPuntuacionReglas.md` de ese repo), calculada como
  `risk = 0.45·severidad + 0.30·confianza + 0.25·explotabilidad`.
- `risk_justification` — motivación de la puntuación.
- `finding_type` (`"malicious"` o `"vulnerability"`) y, cuando aplica,
  `needs_review` / `needs_review_reason` — ver más abajo.

Solo se incluye el subconjunto de reglas presentes en
`yara_scores_output/yara_rule_scores.json` de ese repo (no el catálogo
completo de Yara-Rules/rules), más cualquier `private rule` auxiliar de la
que dependa una regla incluida, para que el fichero siga compilando de
forma independiente.

## Sobre `needs_review`

Algunas reglas de la categoría `utils/` (extractores de IOC genéricos:
URLs, IPs, bloques base64...) llevan `needs_review: true` porque, por
diseño, no son un veredicto de "malicioso" por sí mismas -- son bloques de
construcción pensados para que otra regla los combine con más contexto.
Una de ellas (`utils/domain.yar`, regex `([\w\.-]+)` sin exigir TLD ni
contexto) resultó no discriminar absolutamente nada -- coincidía con
cualquier cadena no vacía -- y se eliminó por completo (ver el commit que
introduce este NOTICE) en vez de mantenerla marcada como pendiente de
revisar.

## Compatibilidad con la licencia MIT del repositorio

La GPLv2 de este directorio no afecta a la licencia MIT del resto del
código de WatchGate: estas reglas son datos que `static_layer.py` carga en
tiempo de ejecución con `yara.compile()` (ver
`StaticLayer._get_compiled_yara_rules`), no código Python enlazado ni
derivado de ellas. Quien redistribuya específicamente el contenido de
`rules/yara/` (modificado o no) debe hacerlo bajo GPLv2, con este mismo
aviso y el `LICENSE` de este directorio; el resto del repositorio sigue
bajo MIT.
