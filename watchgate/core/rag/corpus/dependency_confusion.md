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

## Patrón a vigilar

Paquete nuevo con nombre que sigue la convención interna del proyecto
(prefijo de organización, sufijos `-utils`/`-common`/`-internal`), o muy
parecido a uno popular real (`sympy-dev` vs. `sympy`), resuelto desde un
registro público.
