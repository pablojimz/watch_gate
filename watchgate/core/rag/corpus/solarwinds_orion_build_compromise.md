# Caso: SUNBURST — compromiso del sistema de build de SolarWinds Orion

## Resumen

Descubierto en diciembre de 2020 (por FireEye/Mandiant, investigando su
propio incidente), es el caso de referencia de un ataque a la cadena de
suministro a través del **sistema de build**, no del código fuente en un
repositorio. Un actor con capacidades de estado-nación comprometió el
entorno de compilación de SolarWinds e insertó código malicioso (el
backdoor conocido como "SUNBURST") directamente en el proceso de build del
software Orion, de forma que las actualizaciones oficiales, firmadas
digitalmente con el certificado legítimo de SolarWinds y distribuidas por su
propia infraestructura, ya llevaban el backdoor. Se estima que llegó a unos
18.000 clientes que instalaron la actualización trojanizada, incluyendo
agencias gubernamentales y grandes empresas.

## Vector de introducción

- El compromiso **no ocurrió en ningún commit visible en el historial de
  git** del código fuente de Orion: el atacante modificó el propio proceso
  de build (el paso que compila el código fuente en el binario final) para
  inyectar el backdoor durante la compilación, sin que existiera un diff de
  código fuente que revisar.
- El binario resultante estaba firmado con el certificado de firma de código
  legítimo de SolarWinds, y se distribuyó a través del mecanismo de
  actualización automática oficial — máxima confianza aparente en cada paso
  de la cadena (código firmado, canal de distribución oficial, proveedor
  reconocido) sin que ninguno de esos pasos garantizara nada sobre el
  contenido real.
- El backdoor incluía lógica para permanecer inactivo (*dormant*) durante
  varios días tras la instalación antes de contactar su infraestructura de
  mando y control, dificultando la correlación con la actualización que lo
  introdujo.

## Patrón a vigilar

Cambio en configuración de build/CI (`Makefile`, `.github/workflows/*`,
scripts de release, pipelines de firma) — el compromiso no pasa por un
diff de código de aplicación.

Técnica MITRE ATT&CK relacionada: T1195.001 / T1195.002 (Compromise
Software Supply Chain), aplicada al eslabón de build.
