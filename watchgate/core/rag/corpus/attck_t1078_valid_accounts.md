# MITRE ATT&CK T1078 — Valid Accounts

**Tácticas:** Initial Access, Persistence, Privilege Escalation, Defense
Evasion. **Plataformas:** Containers, ESXi, IaaS, Identity Provider, Linux,
Network Devices, Office Suite, SaaS, Windows, macOS. **Versión:** 3.0.

## Descripción

El adversario obtiene y abusa de credenciales de cuentas *legítimas* ya
existentes, en vez de explotar una vulnerabilidad técnica. "Las credenciales
comprometidas pueden usarse para saltarse los controles de acceso puestos
sobre varios recursos de sistemas dentro de la red, e incluso para acceso
persistente a sistemas remotos y servicios externos disponibles, como VPNs,
Outlook Web Access, dispositivos de red y escritorio remoto."

MITRE señala específicamente que un atacante con acceso legítimo puede optar
por **no usar malware ni herramientas adicionales**, precisamente para que
su actividad sea más difícil de distinguir de la de un usuario/mantenedor
real. También cubre explícitamente el abuso de **cuentas inactivas**:
cuentas de personas que ya no forman parte de una organización, cuyo titular
original no está presente para detectar actividad anómala. Una preocupación
crítica es el solapamiento de permisos entre cuentas locales, de dominio y
de nube, que permite movimiento lateral hacia el compromiso administrativo.

## Sub-técnicas

- **T1078.001** — Default Accounts
- **T1078.002** — Domain Accounts
- **T1078.003** — Local Accounts
- **T1078.004** — Cloud Accounts

## Ejemplos de procedimiento (selección de grupos documentados por MITRE)

**Grupos de estado-nación / espionaje:**
- **APT28 (G0007)** — "Usó credenciales legítimas para conseguir acceso
  inicial, mantener acceso y exfiltrar datos de la red de la víctima";
  robó credenciales vía spearphishing contra la red del DCCC y explotó
  contraseñas de fábrica en dispositivos IoT (teléfonos VOIP, impresoras,
  decodificadores de vídeo).
- **APT29 (G0016)** — Comprometió cuentas para acceder a infraestructura VPN
  en operaciones contra entornos Microsoft.
- **Sandworm Team (G0034)** — Aplicó cuentas válidas "para escalar
  privilegios, moverse lateralmente y establecer persistencia dentro de la
  red corporativa" durante el ataque de 2015 a la red eléctrica de Ucrania.
- **Volt Typhoon (G1017)** — "Se apoya principalmente en credenciales
  válidas para persistencia."

**Grupos con motivación financiera:**
- **Carbanak (G0008)** — "Usó credenciales legítimas de empleados bancarios
  para realizar operaciones que les enviaron millones de dólares."
- **FIN7 (G0046)** — "Recolectó credenciales administrativas legítimas para
  movimiento lateral."
- **Wizard Spider (G0102)** — "Usó credenciales válidas de cuentas
  privilegiadas con el objetivo de acceder a controladores de dominio."

**Ransomware/extorsión:**
- **Akira (G1024)**, **BlackByte (G1043)**, **Play (G1040)** — acceso
  inicial mediante credenciales VPN legítimas robadas.
- **LAPSUS$ (G1004)** — "Usó credenciales comprometidas y/o tokens de
  sesión para acceder a la VPN, VDI, RDP e IAM de la víctima."
- **Scattered Spider (G1015)** — "Usó credenciales comprometidas para
  acceso inicial."

**Cadena de suministro:**
- **AppleJeus (G1049)** — Durante el ataque a la cadena de suministro de
  3CX, "consiguió acceso al entorno corporativo de 3CX a través de
  credenciales VPN legítimas".

## Mitigaciones (MITRE)

- **M1036 — Account Use Policies**: políticas de acceso condicional que
  bloqueen inicios de sesión desde dispositivos no conformes o fuera de
  rangos IP definidos por la organización.
- **M1032 — Multi-factor Authentication**: MFA en todos los tipos de
  cuenta (por defecto, local, dominio, nube) para prevenir acceso no
  autorizado aunque las credenciales estén comprometidas.
- **M1027 — Password Policies**: cambiar usuarios/contraseñas por defecto
  inmediatamente tras la instalación; minimizar la reutilización de
  contraseñas entre cuentas.
- **M1026 — Privileged Account Management**: auditar rutinariamente cuentas
  de dominio y locales, y sus niveles de permiso.
- **M1018 — User Account Management**: auditar regularmente cuentas de
  usuario por actividad y desactivar/eliminar las que ya no se necesiten.
- **M1017 — User Training**: entrenar a los usuarios para aceptar solo
  notificaciones push de MFA legítimas y reportar las sospechosas.

## Estrategia de detección (MITRE)

**DET0560 — Detection of Valid Account Abuse Across Platforms**

- **AN1543**: patrones de inicio de sesión anómalos, tipos de logon
  atípicos, inconsistencias geográficas e irregularidades temporales en
  endpoints Windows.
- **AN1544**: uso indebido de cuentas válidas vía SSH, abuso de `sudo`/`su`
  y anomalías de cuentas de servicio fuera de patrones esperados.
- **AN1546**: logs del proveedor de identidad con anomalías geográficas,
  indicadores de "viaje imposible", inicios de sesión de riesgo y fallos
  repetidos de MFA.

## Casos de este corpus que son ejemplos directos de esta técnica

- `coa_rc_npm_maintainer_compromise.md`, `rest_client_rubygems_backdoor.md`,
  `solana_web3js_npm_phishing_compromise.md`,
  `eslint_config_prettier_npm_postinstall_rat.md` — compromiso de la cuenta
  de un mantenedor en el registro del paquete.
- `pypi_ctx_env_exfiltration.md` — toma de una cuenta/dominio de contacto
  vencido.
- `xz_utils.md` — caso límite: no es una cuenta robada, sino una identidad
  de mantenedor construida durante años hasta obtener acceso real — el
  efecto (acceso legítimo que nadie cuestiona) es el mismo.

## Nota WatchGate

Explica por qué la reputación del autor no es señal suficiente por sí sola:
cuando el vector de ataque es precisamente una cuenta legítima —robada o
construida a propósito—, cualquier señal basada solo en "esta cuenta tiene
historial" queda neutralizada por diseño.
