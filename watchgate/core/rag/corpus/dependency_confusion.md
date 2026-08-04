# Técnica: *dependency confusion* (confusión de dependencias)

## Resumen

Técnica publicada por el investigador Alex Birsan en febrero de 2021
("Dependency Confusion: How I Hacked Into Apple, Microsoft and Dozens of
Other Companies"), que le permitió, de forma ética y con recompensas de
*bug bounty*, ejecutar código en la infraestructura de más de 35 empresas
grandes. Es una técnica distinta del *typosquatting* (nombres parecidos a
un paquete popular): aquí el atacante usa el **mismo nombre exacto** que un
paquete interno/privado de una organización.

Muchas empresas usan paquetes internos (p. ej. `empresa-auth-utils`) en un
registro privado, pero configuran sus herramientas (`pip`, `npm`, `yarn`,
`Maven`, etc.) para buscar también en el registro público (PyPI, npmjs.org)
como *fallback* o simplemente sin especificar prioridad. Si el gestor de
paquetes resuelve por número de versión más alto en vez de por origen
(público vs. privado) de forma predecible, publicar un paquete público con
ese mismo nombre y una versión más alta que la interna hace que el build
del objetivo instale el paquete del atacante en vez del interno — sin que
nadie haya tocado el código fuente del proyecto objetivo.

## Vector de introducción

- No requiere ninguna vulnerabilidad de código: explota cómo el gestor de
  paquetes **decide qué registro consultar primero**, no un fallo en el
  paquete en sí.
- El atacante necesita averiguar el nombre exacto de un paquete interno —
  algo sorprendentemente fácil: nombres de paquetes internos aparecen
  filtrados en `package.json`/`requirements.txt` de repositorios públicos
  de la propia empresa, en mensajes de error, en código open-source que
  referencia dependencias internas por error, o en el propio `README`.
- El payload del paquete malicioso suele ser un simple script de
  instalación (`setup.py`, hook `postinstall` de npm) que exfiltra
  variables de entorno, hostname o metadata del entorno de build —
  suficiente para confirmar la ejecución y a menudo para robar secretos de
  CI/CD.

## Variante emparentada: *typosquatting* de un paquete popular real

Distinto de la confusión de dependencias (nombre interno filtrado), pero con
el mismo objetivo final: imitar el nombre de un paquete público ya conocido
y confiado, no uno interno. Caso real documentado en OSV
(`MAL-2026-450`, ene. 2026): el paquete `sympy-dev` en PyPI, publicado en
varias versiones (`1.2.3`-`1.2.6`), imitaba al paquete legítimo y muy
popular `sympy` (librería de matemática simbólica) y descargaba y ejecutaba
código desde servidores remotos. El sufijo `-dev` es plausible para un
desarrollador que busca una variante de desarrollo del paquete real,
reduciendo la sospecha frente a un typosquat más burdo.

## Por qué es relevante para WatchGate

- Directamente relacionado con la consulta automática de dependencias
  nuevas ya implementada (`gather_dependency_findings`): un paquete nuevo
  en `requirements.txt` con un nombre que sigue la convención de nombrado
  interna del proyecto (prefijo de la organización, sufijos tipo `-utils`,
  `-common`, `-internal`) merece más escrutinio, no menos, precisamente
  porque *parece* interno y de confianza. Lo mismo aplica a un nombre que
  se parece mucho a un paquete popular real (`sympy-dev` vs. `sympy`,
  `requestn` vs. `requests`): la similitud con algo confiable es la propia
  señal de alarma, no una razón para bajar la guardia.
- La capa semántica debe fijarse en si una dependencia nueva tiene sentido
  para el ecosistema/dominio del proyecto: un paquete con nombre que suena
  interno pero que se resuelve desde un registro público es la propia
  definición de esta técnica.
- Mismo objetivo final que el caso `ctx` (exfiltración vía dependencia),
  pero el vector de entrada es la **resolución del gestor de paquetes**, no
  el secuestro de un paquete ya existente y de confianza.
