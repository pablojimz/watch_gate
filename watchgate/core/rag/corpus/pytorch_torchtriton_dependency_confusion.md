# Caso: PyTorch / torchtriton (PyPI) — dependency confusion en nightly builds (diciembre 2022)

## Resumen

Entre el 25 y el 30 de diciembre de 2022, las instalaciones *nightly* de
PyTorch en Linux quedaron comprometidas por un ataque de *dependency
confusion*. PyTorch-nightly declaraba una dependencia llamada
`torchtriton` que se servía desde el índice privado del propio proyecto;
un atacante registró un paquete con ese mismo nombre en PyPI, y como pip
da precedencia al índice público, todo `pip install torch --pre` durante
esos días instaló el paquete malicioso en lugar del interno. El equipo de
PyTorch retiró la dependencia, renombró el paquete interno a
`pytorch-triton` y reservó el nombre en PyPI para que no pudiera
repetirse. Las versiones estables de PyTorch nunca estuvieron afectadas.

## Vector de introducción

- Confusión de dependencias de manual: un nombre de paquete que solo
  existía en un índice privado quedó libre en el índice público, y el
  gestor de paquetes (pip) resolvió el público con prioridad. No hizo
  falta comprometer ninguna cuenta ni infraestructura de PyTorch — solo
  registrar un nombre.
- El binario malicioso (`triton`, dentro del paquete) se ejecutaba al
  importar y exfiltraba información del sistema: `/etc/passwd`,
  `/etc/hosts`, las primeras claves de `~/.ssh/*`, `~/.gitconfig`,
  variables de entorno y un listado de ficheros del `$HOME`.
- La exfiltración iba por consultas DNS cifradas hacia un dominio
  controlado por el atacante (`*.h4ck.cfd`) — canal que atraviesa la
  mayoría de firewalls corporativos sin inspección, porque casi nadie
  bloquea ni monitoriza DNS saliente.
- El autor del paquete alegó después que era "investigación de
  seguridad"; la exfiltración de claves SSH reales hace esa defensa
  irrelevante a efectos de riesgo.

## Patrón a vigilar

Dependencia declarada cuyo nombre pertenece al espacio interno/privado de
una organización (o que hasta ahora se instalaba con `--index-url`/
`--extra-index-url` propios) apareciendo resoluble desde el índice
público, o un diff que elimina el pin de índice privado de una dependencia
existente. Complementa `dependency_confusion.md`: este es el incidente
real de mayor perfil de esa técnica. También: código de paquete que
construye consultas DNS con datos codificados (subdominios largos y de
aspecto aleatorio) — exfiltración por DNS.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools — dependency confusion), T1048
(Exfiltration Over Alternative Protocol — DNS), T1552 (Unsecured
Credentials — claves SSH y gitconfig).
