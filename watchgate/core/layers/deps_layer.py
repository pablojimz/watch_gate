"""Capa de dependencias (spec §5) — señales de ataque a la cadena de suministro.

Analiza cambios en manifiestos de dependencias (package.json, requirements.txt,
PKGBUILD, Cargo.toml) evaluando:
1. Typosquatting comparando contra datasets de paquetes populares con rapidfuzz.
2. Scripts de instalación sospechosos (preinstall/postinstall/PKGBUILD).
3. Instalación directa por URL/Git (evita el registro del ecosistema).

Deliberadamente sin CVEs conocidas (OSV) -- eso vive en
`vulnerabilities_layer.py`, una capa aparte y con su propio interruptor:
una CVE en una dependencia es una debilidad del ecosistema, no evidencia de
que *este PR concreto* sea un ataque, y muchos equipos ya cubren eso con
Dependabot/Snyk/similar. Las tres señales de aquí sí lo son.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rapidfuzz.distance import Levenshtein

from watchgate.core.layers._shared import (
    DEPENDENCY_MANIFEST_FILENAMES,
    DependencyChange,
    analyze_install_script_text,
    parse_manifest_file_change,
)
from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import (
    Confidence,
    Finding,
    LayerResult,
    NormalizedDiff,
    ThreatNature,
    compute_dominant_threat_nature,
)

logger = logging.getLogger("watchgate.deps")

__all__ = [
    "DependencyChange",
    "DepsLayer",
    "TyposquatChecker",
    "parse_manifest_file_change",
]


# Combosquatting: nombre real de un paquete popular + un sufijo genérico que
# suena a "versión de confianza" ("sympy-dev", "requests-official"...).
# Reproducido en vivo: "sympy-dev" no lo detectaba nada -- la distancia de
# Levenshtein contra "sympy" es 4 (se insertan 4 caracteres), por encima del
# límite de 2 que usa la comparación de abajo a propósito (para no marcar
# typos de una sola letra como si fueran a 4 de distancia). Un ataque de
# combosquatting no es un typo: añade texto a propósito, así que Levenshtein
# nunca lo va a pillar por diseño -- hace falta una comparación aparte, de
# sufijo exacto contra el nombre real. Solo sufijos con separador (no dígitos
# sueltos como "2"/"3": "boto3" es un paquete real y distinto de "boto", no
# typosquatting de él).
_COMBOSQUAT_SUFFIXES = (
    "-dev",
    "-test",
    "-official",
    "-secure",
    "-safe",
    "-real",
    "-patch",
    "-fix",
    "-utils",
    "-util",
    "-new",
    "-latest",
    "-stable",
    "-original",
)


class TyposquatChecker:
    """Verifica si un nombre de paquete es sospechoso de typosquatting
    comparando su distancia Levenshtein contra listados de referencia de paquetes populares,
    y de combosquatting (nombre real + sufijo genérico sospechoso, ver `_COMBOSQUAT_SUFFIXES`).
    """

    def __init__(self, dataset_dir: Path | None = None) -> None:
        if dataset_dir is None:
            dataset_dir = (
                Path(__file__).resolve().parent.parent.parent.parent
                / "datasets"
                / "typosquat_reference"
            )
        self.dataset_dir = dataset_dir
        self._reference_sets: dict[str, set[str]] = {}
        self._reference_lists: dict[str, list[str]] = {}

    def _load_ecosystem(self, ecosystem_key: str) -> None:
        if ecosystem_key in self._reference_sets:
            return

        file_map = {
            "npm": "npm.txt",
            "pypi": "pypi.txt",
            "aur": "aur.txt",
            "crates.io": "crates.txt",
            "go": "go.txt",
            "packagist": "packagist.txt",
        }
        filename = file_map.get(ecosystem_key.lower())
        if not filename:
            self._reference_sets[ecosystem_key] = set()
            self._reference_lists[ecosystem_key] = []
            return

        filepath = self.dataset_dir / filename
        if not filepath.exists():
            self._reference_sets[ecosystem_key] = set()
            self._reference_lists[ecosystem_key] = []
            return

        try:
            lines = [
                line.strip()
                for line in filepath.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self._reference_sets[ecosystem_key] = set(lines)
            self._reference_lists[ecosystem_key] = list(lines)
        except Exception:  # noqa: BLE001
            self._reference_sets[ecosystem_key] = set()
            self._reference_lists[ecosystem_key] = []

    def is_typosquatting(self, name: str, ecosystem: str) -> tuple[bool, str | None]:
        eco_key = ecosystem.lower()
        self._load_ecosystem(eco_key)

        top_set = self._reference_sets.get(eco_key, set())
        top_list = self._reference_lists.get(eco_key, [])

        if not top_list or not name:
            return False, None

        name_lower = name.lower()
        norm_name = name_lower.replace("_", "-")

        if name_lower in top_set or norm_name in top_set:
            # Es un paquete popular legítimo
            return False, None

        len_norm = len(norm_name)

        # Comparar distancia Levenshtein contra el listado popular (con normalización _ y -)
        for ref_pkg in top_list:
            ref_norm = ref_pkg.lower().replace("_", "-")
            if abs(len_norm - len(ref_norm)) > 2:
                continue

            dist = Levenshtein.distance(norm_name, ref_norm)
            if 0 < dist <= 2:
                return True, ref_pkg

        # Combosquatting (ver comentario de _COMBOSQUAT_SUFFIXES): el nombre
        # completo, no un paquete de longitud parecida -- por eso va en un
        # bucle aparte en vez de dentro del filtro de longitud de arriba.
        for ref_pkg in top_list:
            ref_norm = ref_pkg.lower().replace("_", "-")
            for suffix in _COMBOSQUAT_SUFFIXES:
                if norm_name == ref_norm + suffix:
                    return True, ref_pkg

        return False, None


# --- Capa Principal ---


@register_layer
class DepsLayer(AnalysisLayer):
    name: str = "dependencies"

    def __init__(
        self,
        typosquat_dataset_dir: Path | None = None,
    ) -> None:
        self.typosquat_checker = TyposquatChecker(dataset_dir=typosquat_dataset_dir)

    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        # 1. Filtrar si algún archivo modificado es un manifiesto reconocido
        manifest_files = [
            f for f in diff.files if Path(f.path).name in DEPENDENCY_MANIFEST_FILENAMES
        ]
        if not manifest_files:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="No se han modificado manifiestos de dependencias.",
            )

        # 2. Parsear cambios en dependencias
        all_changes: list[DependencyChange] = []
        for file_change in manifest_files:
            all_changes.extend(parse_manifest_file_change(file_change))

        if not all_changes:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification=(
                    "Se modificaron manifiestos pero no se añadieron ni cambiaron dependencias."
                ),
            )

        scores: list[int] = []
        # Solo entra aquí el detalle de un paquete con una señal REAL
        # (typosquatting/script sospechoso/instalación directa) -- ver
        # `has_real_signal` más abajo. `clean_count` cuenta el resto (incluida
        # "nueva dependencia sin señales", que puntúa 10 pero no es una
        # alerta, solo la base por ser dependencia nueva) para no perderlos
        # del todo, solo sacarlos del muro de texto.
        justifications: list[str] = []
        clean_count = 0
        structured_findings: list[Finding] = []

        # 3. Analizar cada cambio
        for change in all_changes:
            pkg_score = 0
            pkg_notes: list[str] = []
            pkg_nature: ThreatNature = ThreatNature.VULNERABILITY
            has_real_signal = False

            # A. Typosquatting
            is_typosquat, ref_pkg = self.typosquat_checker.is_typosquatting(
                change.name, change.ecosystem
            )
            if is_typosquat:
                pkg_score = max(pkg_score, 75)
                pkg_notes.append(
                    f"Posible typosquatting: '{change.name}' imita al paquete popular "
                    f"'{ref_pkg}' de {change.ecosystem} (nombre casi idéntico, técnica "
                    "habitual para hacer pasar un paquete malicioso por uno legítimo)"
                )
                pkg_nature = ThreatNature.MALICIOUS
                has_real_signal = True

            # B. Script de instalación
            if change.install_script:
                findings = analyze_install_script_text(change.install_script)
                if findings:
                    pkg_score = max(pkg_score, 80)
                    pkg_notes.append(
                        f"Script de instalación sospechoso ({', '.join(findings)}): se "
                        "ejecutaría automáticamente al instalar la dependencia, sin "
                        "intervención de quien la instala"
                    )
                    pkg_nature = ThreatNature.MALICIOUS
                    has_real_signal = True

            # C. Instalación directa por URL/Git
            if change.is_direct_url:
                pkg_score = max(pkg_score, 75)
                pkg_notes.append(
                    f"Instalación directa desde URL/Git ({change.new_version or change.name}) "
                    "en vez del registro oficial del ecosistema, evitando así sus "
                    "controles de publicación"
                )
                pkg_nature = ThreatNature.MALICIOUS
                has_real_signal = True

            # D. Si es nueva dependencia y no tuvo alertas
            if change.is_new and pkg_score == 0:
                pkg_score = 10
                pkg_notes.append(
                    "Nueva dependencia sin señales de typosquatting, scripts "
                    "sospechosos ni instalación directa; puntuación base baja solo "
                    "por tratarse de una dependencia añadida por primera vez"
                )

            scores.append(pkg_score)
            version_str = f"@{change.new_version}" if change.new_version else ""
            notes_str = "; ".join(pkg_notes) if pkg_notes else "sin señales de riesgo detectadas"
            if has_real_signal:
                justifications.append(f"{change.name}{version_str} ({change.ecosystem}): {notes_str}")
            else:
                # Bug real, reproducido: antes esto entraba SIEMPRE en
                # `justifications`, incluidas las ~90 dependencias "nueva
                # dependencia sin señales..." de un PR de 97 paquetes -- el
                # texto final era un muro con una entrada por dependencia,
                # obligando a leer 97 líneas para encontrar la única con una
                # señal real. Ahora solo entran aquí paquetes con una señal
                # de verdad (A/B/C); el resto solo se cuenta (`clean_count`).
                clean_count += 1

            if pkg_score > 0:
                m_path = change.manifest_path if change.manifest_path else change.name
                structured_findings.append(
                    Finding(
                        file_path=m_path,
                        rule_id=f"dependency-{change.ecosystem.lower()}",
                        message=f"{change.name}{version_str}: {notes_str}",
                        severity="error" if pkg_score >= 60 else "warning",
                        threat_nature=pkg_nature,
                    )
                )

        final_score = max(scores, default=0)
        dominant_threat = compute_dominant_threat_nature(structured_findings)

        # Resumen inicial: explica de dónde sale la puntuación antes del
        # detalle por paquete, para que el reporte del dashboard no obligue
        # a inferir el motivo a partir de una lista de notas sueltas.
        if final_score == 0:
            summary = (
                "Ninguna de las dependencias modificadas presenta señales de "
                "ataque a la cadena de suministro."
            )
        elif len(all_changes) > 1:
            summary = (
                f"Puntuación {final_score}/100: al menos una de las {len(all_changes)} "
                "dependencias analizadas presenta señales de riesgo (la puntuación "
                "final es el máximo entre todas, nunca la suma)."
            )
        else:
            summary = f"Puntuación {final_score}/100 por lo encontrado en esta dependencia."

        # El conteo de "limpias" solo aporta algo cuando ya hay al menos una
        # señal real que mostrar -- si no hay ninguna, `summary` ya deja
        # claro que nada tiene señales (caso `final_score == 0` arriba) y
        # añadir "(+N sin señales)" ahí sería ruido redundante, justo lo que
        # se quiere evitar.
        detail = " | ".join(justifications)
        if clean_count and justifications:
            detail += f" | (+{clean_count} dependencia(s) más sin señales de riesgo, omitidas por brevedad)"
        final_justification = f"{summary} {detail}".strip()

        confidence = None
        if final_score >= 70:
            confidence = Confidence.ALTA
        elif final_score >= 40:
            confidence = Confidence.MEDIA
        elif final_score > 0:
            confidence = Confidence.BAJA

        return LayerResult(
            layer_name=self.name,
            risk_score=final_score,
            justification=final_justification,
            findings=structured_findings,
            threat_nature=dominant_threat,
            confidence=confidence,
        )
