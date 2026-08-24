# Caso: arrayref (crates.io, Rust) — dropper vía typosquat de proc-macro2 en build.rs

## Resumen

El 20 de agosto de 2026, tres crates legítimos de Rust muy usados —
`arrayref` 0.3.10 (244 millones de descargas, presente en aproximadamente
tres cuartas partes de todos los entornos Rust), `internment` 0.8.7 y
`append-only-vec` 0.1.9— fueron publicados con una única línea nueva en su
manifiesto de dependencias (`Cargo.toml`): una dependencia hacia
`proc-macro1`, un *typosquat* del crate legítimo y muy popular
`proc-macro2`. **Ninguno de los tres crates comprometidos contenía ni una
sola línea de código malicioso propio** — el payload real vivía
íntegramente en el script `build.rs` del crate typosquat, que Cargo
ejecuta automáticamente durante la compilación. Investigadores de
seguridad (Wiz) encontraron solapamiento significativo con infraestructura
de campañas previas atribuidas a Corea del Norte (UNC1069). El equipo de
respuesta de seguridad de Rust retiró los paquetes en 86-107 minutos.

## Vector de introducción

- Cronología: a la 01:55 UTC el atacante publicó `proc-macro1` 1.0.106,
  una copia limpia (no maliciosa) de `proc-macro2` con metadatos de autor
  falsificados — permaneció así, inofensiva, más de cinco horas, sin duda
  para acumular una apariencia de normalidad antes de armarse. A las 07:11
  UTC, la misma cuenta publicó `proc-macro1` 1.0.107, ya con el payload
  real. Cuatro minutos después, `arrayref` 0.3.10 apareció con una
  dependencia declarada hacia ese typosquat armado.
- Mecanismo de ejecución: `build.rs` es un script que Cargo ejecuta
  automáticamente en tiempo de compilación, antes de que exista ningún
  binario del proyecto — a diferencia de código de aplicación normal, que
  requiere que el programa se ejecute para activarse. Compilar un proyecto
  que dependa (aunque sea transitivamente) de la versión armada era
  suficiente para ejecutar el payload, sin ninguna acción adicional.
- Resiliencia deliberada de la campaña: existía un segundo crate dropper
  (`proc-macro-en`) con el mismo `build.rs` malicioso que `proc-macro1` —
  retirar un solo typosquat no desarmaba la campaña completa.
- El payload contactaba una IP fija por los puertos 9089 y 443,
  saltándose la validación de certificados TLS, y seleccionaba malware
  específico según la plataforma (Unix/Windows) — dejando que la
  compilación pareciera terminar con normalidad.

## Patrón a vigilar

Un diff que **solo** añade una línea nueva a un manifiesto de dependencias
(`Cargo.toml`, o equivalente en otros ecosistemas) apuntando a un nombre
de paquete a distancia de edición mínima de uno legítimo y muy conocido
(`proc-macro1` vs. `proc-macro2`), sin ningún otro cambio de código — la
ausencia total de cambios "sustanciales" en el propio diff no es señal de
bajo riesgo, es exactamente el patrón de este ataque.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools — typosquatting), T1584 (Compromise
Infrastructure — servidor de C2 fijo usado por el payload).
