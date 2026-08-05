# MITRE ATT&CK T1078 — Valid Accounts

## Descripción

El adversario obtiene y abusa de credenciales de cuentas *legítimas* ya
existentes, en vez de explotar una vulnerabilidad técnica. MITRE señala
específicamente que un atacante con acceso legítimo puede optar por **no
usar malware ni herramientas adicionales**, precisamente para que su
actividad sea más difícil de distinguir de la de un usuario/mantenedor
real. También señala el abuso de cuentas inactivas: cuentas de personas
que ya no forman parte de una organización, cuyo titular original no está
presente para detectar actividad anómala.

## Casos de este corpus que son ejemplos directos de esta técnica

- `coa_rc_npm_maintainer_compromise.md` y `rest_client_rubygems_backdoor.md`
  — compromiso de la cuenta de un mantenedor en el registro del paquete;
  el propio aviso de `rest-client` recomienda tratar cualquier máquina
  afectada como totalmente comprometida.
- `pypi_ctx_env_exfiltration.md` — toma de una cuenta/dominio de contacto
  vencido, no una vulnerabilidad del código del paquete `ctx` en sí.
- `xz_utils.md` — caso límite pero relacionado: no es una cuenta robada,
  sino una identidad de mantenedor **construida durante años** con
  contribuciones legítimas hasta obtener acceso real — MITRE no lo llama
  "cuenta válida" en sentido estricto, pero el efecto (acceso legítimo que
  nadie cuestiona) es el mismo.

## Por qué es relevante para WatchGate

- Es la técnica que mejor explica **por qué la reputación del autor no es
  suficiente señal por sí sola** (principio central del sistema, spec §6 y
  §7.1): cuando el vector de ataque es precisamente una cuenta legítima
  —robada o construida a propósito—, cualquier señal basada solo en "esta
  cuenta tiene historial" queda neutralizada por diseño. De ahí que la capa
  de reputación combine antigüedad de cuenta, contribuciones previas *y*
  verificación de identidad (email/firma), no una sola señal aislada.
- MITRE señala explícitamente el riesgo de cuentas inactivas reactivadas:
  un mantenedor que vuelve tras mucho tiempo sin actividad, o un colaborador
  con permisos antiguos que nadie ha revisado, merece el mismo escrutinio
  que una cuenta nueva — la capa de reputación ya puntúa "0 contribuciones
  previas" y "cuenta reciente", pero una cuenta *antigua e inactiva que se
  reactiva* es un patrón distinto, no cubierto explícitamente todavía.
