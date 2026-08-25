# Caso: Codecov Bash Uploader — compromiso de un script de CI ampliamente usado

## Resumen

En abril de 2021, Codecov (herramienta de cobertura de tests muy usada en
pipelines de CI/CD) reveló que su script "Bash Uploader" —descargado y
ejecutado directamente desde su infraestructura en miles de pipelines de
CI de terceros, típicamente con `curl ... | bash`— había sido modificado
por un atacante para exfiltrar variables de entorno del entorno de CI de
cada cliente que lo ejecutaba, incluyendo tokens, credenciales y claves
usadas en esos pipelines. El acceso inicial fue posible por un error en el
proceso de creación de la imagen Docker de Codecov, que dejó expuestas
credenciales que permitieron modificar el script en su origen.

## Vector de introducción

- El vector de entrada exacto (credenciales expuestas en una imagen Docker
  mal construida) es distinto en cada caso, pero el patrón de explotación
  es el mismo que se documenta en `docker_typosquatted_base_images.md` y en
  el `RUN curl | sh` de un `Dockerfile`: un script obtenido por red y
  ejecutado directamente (`curl ... | bash`), sin pinnear versión ni
  verificar checksum, en miles de pipelines de CI ajenos a Codecov.
- Las víctimas no cambiaron nada en su propio repositorio: el paso de CI
  que descargaba y ejecutaba el uploader llevaba tiempo sin tocarse, igual
  que en el caso `polyfill_io_cdn_compromise.md` — el riesgo vive en la
  confianza depositada en un tercero externo, no en ningún diff propio.
- El objetivo (variables de entorno de CI) es el mismo patrón ya visto en
  `github-actions-secret-leak` (caso de prueba en
  `scripts/rag_ablation_cases.py`) y en `prt_scan.md`: los entornos de CI
  concentran secretos de alto valor y son un objetivo recurrente.

## Patrón a vigilar

`curl ... | bash` (o equivalente) invocando un script de terceros sin
fijar por versión/hash dentro de un workflow de CI.

Técnica MITRE ATT&CK relacionada: T1195.002 (Compromise Software Supply
Chain).
