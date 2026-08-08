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
    parse_cargo_toml,
    parse_package_json,
    parse_pkgbuild,
    parse_requirements_txt,
)
from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import (
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
    "parse_cargo_toml",
    "parse_package_json",
    "parse_pkgbuild",
    "parse_requirements_txt",
]


class TyposquatChecker:
    """Verifica si un nombre de paquete es sospechoso de typosquatting
    comparando su distancia Levenshtein contra listados de referencia de paquetes populares.
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
            fname = Path(file_change.path).name
            hunk = file_change.diff_hunk
            parsed: list[DependencyChange] = []
            if fname == "package.json":
                parsed = parse_package_json(hunk)
            elif fname in ("requirements.txt", "Pipfile"):
                parsed = parse_requirements_txt(hunk)
            elif fname == "PKGBUILD":
                parsed = parse_pkgbuild(hunk)
            elif fname == "Cargo.toml":
                parsed = parse_cargo_toml(hunk)
            for ch in parsed:
                ch.manifest_path = file_change.path
            all_changes.extend(parsed)

        if not all_changes:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification=(
                    "Se modificaron manifiestos pero no se añadieron ni " "cambiaron dependencias."
                ),
            )

        scores: list[int] = []
        justifications: list[str] = []
        structured_findings: list[Finding] = []

        # 3. Analizar cada cambio
        for change in all_changes:
            pkg_score = 0
            pkg_notes: list[str] = []
            pkg_nature: ThreatNature = ThreatNature.VULNERABILITY

            # A. Typosquatting
            is_typosquat, ref_pkg = self.typosquat_checker.is_typosquatting(
                change.name, change.ecosystem
            )
            if is_typosquat:
                pkg_score = max(pkg_score, 75)
                pkg_notes.append(f"Posible typosquatting: '{change.name}' imita a '{ref_pkg}'")
                pkg_nature = ThreatNature.MALICIOUS

            # B. Script de instalación
            if change.install_script:
                findings = analyze_install_script_text(change.install_script)
                if findings:
                    pkg_score = max(pkg_score, 80)
                    pkg_notes.append(f"Script de instalación sospechoso ({', '.join(findings)})")
                    pkg_nature = ThreatNature.MALICIOUS

            # C. Instalación directa por URL/Git
            if change.is_direct_url:
                pkg_score = max(pkg_score, 75)
                pkg_notes.append(
                    f"Instalación directa desde URL/Git ({change.new_version or change.name})"
                )
                pkg_nature = ThreatNature.MALICIOUS

            # D. Si es nueva dependencia y no tuvo alertas
            if change.is_new and pkg_score == 0:
                pkg_score = 10
                pkg_notes.append(
                    "Nueva dependencia sin señales de typosquatting, scripts "
                    "sospechosos ni instalación directa"
                )

            scores.append(pkg_score)
            version_str = f"@{change.new_version}" if change.new_version else ""
            notes_str = "; ".join(pkg_notes) if pkg_notes else "OK"
            justifications.append(f"{change.name}{version_str} ({change.ecosystem}): {notes_str}")

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
        final_justification = " | ".join(justifications)
        dominant_threat = compute_dominant_threat_nature(structured_findings)

        return LayerResult(
            layer_name=self.name,
            risk_score=final_score,
            justification=final_justification,
            findings=structured_findings,
            threat_nature=dominant_threat,
        )
