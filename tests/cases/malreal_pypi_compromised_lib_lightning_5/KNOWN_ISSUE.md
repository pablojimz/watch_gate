# Ground truth no fiable

El fichero de este caso es código real y benigno, no el payload malicioso
del paquete comprometido -- el payload real está protegido con contraseña
en el ZIP de origen (dataset DataDog) y no se extrajo al generar esta
fixture. `expected.json` no se ha tocado a propósito (el paquete sí fue
comprometido de verdad, solo que no en este fichero).

Ver el hallazgo completo, cómo se verificó, y por qué no se ha "arreglado"
sin más: `docs/evaluacion_ia/ground_truth_dudoso_dataset_datadog.md`.
