"""Capa de dependencias (spec §5).

Analiza cambios en manifiestos de dependencias (package.json, requirements.txt,
PKGBUILD, Cargo.toml) evaluando:
1. Vulnerabilidades conocidas en OSV (api.osv.dev) con caché SQLite (TTL 24h).
2. Typosquatting comparando contra datasets de paquetes populares con rapidfuzz.
3. Scripts de instalación sospechosos (preinstall/postinstall/PKGBUILD).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel
from rapidfuzz.distance import Levenshtein

from watchgate.core.layers._shared import (
    DEPENDENCY_MANIFEST_FILENAMES,
    analyze_install_script_text,
)
from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import LayerResult, NormalizedDiff

_OSV_API_URL = "https://api.osv.dev/v1/query"
_CACHE_TTL_HOURS = 24


class DependencyChange(BaseModel):
    ecosystem: str  # "npm" | "PyPI" | "aur" | "crates.io"
    name: str
    old_version: str | None = None
    new_version: str | None = None
    is_new: bool = True
    install_script: str | None = None


class OSVCache:
    """Caché SQLite para respuestas de OSV.dev con TTL de 24 horas y tolerancia a fallos
    en la ruta del archivo (fallback a /tmp o :memory: si la ruta home falla).
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self.db_path = self._resolve_db_path(db_path)
        self._init_db()

    def _resolve_db_path(self, db_path: str | None) -> str:
        if db_path:
            return db_path
        env_dir = os.environ.get("WATCHGATE_CACHE_DIR")
        if env_dir:
            return str(Path(env_dir) / "cache.db")

        default_dir = Path.home() / ".watchgate"
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
            test_file = default_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return str(default_dir / "cache.db")
        except Exception:  # noqa: BLE001
            tmp_dir = Path("/tmp/.watchgate")  # noqa: S108
            try:
                tmp_dir.mkdir(parents=True, exist_ok=True)
                return str(tmp_dir / "cache.db")
            except Exception:  # noqa: BLE001
                return ":memory:"

    def _init_db(self) -> None:
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            with self._lock:
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS osv_cache (
                        name TEXT,
                        ecosystem TEXT,
                        version TEXT,
                        response_json TEXT,
                        fetched_at TEXT,
                        PRIMARY KEY (name, ecosystem, version)
                    )
                    """
                )
                self._conn.commit()
        except Exception:  # noqa: BLE001
            self._conn = None

    def get(self, name: str, ecosystem: str, version: str | None) -> dict[str, Any] | None:
        if self._conn is None:
            return None
        v_key = version or ""
        with self._lock:
            try:
                row = self._conn.execute(
                    """
                    SELECT response_json, fetched_at FROM osv_cache
                    WHERE name = ? AND ecosystem = ? AND version = ?
                    """,
                    (name, ecosystem, v_key),
                ).fetchone()
                if not row:
                    return None
                resp_json, fetched_at_str = str(row[0]), str(row[1])
                fetched_at = datetime.fromisoformat(fetched_at_str)
                if datetime.now(UTC) - fetched_at > timedelta(hours=_CACHE_TTL_HOURS):
                    return None
                data: dict[str, Any] = json.loads(resp_json)
                return data
            except Exception:  # noqa: BLE001
                return None

    def set(
        self,
        name: str,
        ecosystem: str,
        version: str | None,
        response_data: dict[str, Any],
    ) -> None:
        if self._conn is None:
            return
        v_key = version or ""
        now_str = datetime.now(UTC).isoformat()
        resp_json = json.dumps(response_data)
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO osv_cache
                    (name, ecosystem, version, response_json, fetched_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, ecosystem, v_key, resp_json, now_str),
                )
                self._conn.commit()
            except Exception:  # noqa: BLE001
                pass

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None


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
            self._reference_lists[ecosystem_key] = lines
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
        if name_lower in top_set:
            # Es un paquete popular legítimo
            return False, None

        # Comparar distancia Levenshtein contra el listado popular
        for ref_pkg in top_list:
            dist = Levenshtein.distance(name_lower, ref_pkg.lower())
            if 0 < dist <= 2:
                return True, ref_pkg

        return False, None


# --- Parsers de Manifiestos ---

_PKG_JSON_DEP_REGEX = re.compile(r'^\+\s*"([^"]+)":\s*"([^"]+)"')
_PKG_JSON_SCRIPT_REGEX = re.compile(r'^\+\s*"(preinstall|postinstall|install)":\s*"([^"]+)"')


def parse_package_json(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    install_scripts: list[str] = []

    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue

        script_match = _PKG_JSON_SCRIPT_REGEX.search(line)
        if script_match:
            install_scripts.append(f"{script_match.group(1)}: {script_match.group(2)}")
            continue

        dep_match = _PKG_JSON_DEP_REGEX.search(line)
        if dep_match:
            dep_name = dep_match.group(1)
            dep_version = dep_match.group(2)
            changes.append(
                DependencyChange(
                    ecosystem="npm",
                    name=dep_name,
                    new_version=dep_version,
                    is_new=True,
                )
            )

    if install_scripts and changes:
        combined_script = "; ".join(install_scripts)
        for change in changes:
            change.install_script = combined_script

    return changes


_REQ_LINE_REGEX = re.compile(
    r"^\+\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:==|>=|<=|~=|>|<)?([A-Za-z0-9._-]*)?"
)


def parse_requirements_txt(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        content = line[1:].strip()
        if not content or content.startswith("#") or content.startswith("-r"):
            continue
        match = _REQ_LINE_REGEX.match(line)
        if match:
            name = match.group(1)
            version = match.group(2) if match.group(2) else None
            changes.append(
                DependencyChange(
                    ecosystem="PyPI",
                    name=name,
                    new_version=version,
                    is_new=True,
                )
            )
    return changes


_PKGBUILD_DEP_REGEX = re.compile(r"^\+\s*(?:depends|makedepends)=\((.*?)\)", re.DOTALL)


def parse_pkgbuild(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    install_script_lines: list[str] = []

    for line in diff_hunk.splitlines():
        if line.startswith("+") and not line.startswith("++"):
            install_script_lines.append(line[1:])
            dep_matches = re.findall(r"['\"]?([a-zA-Z0-9._-]+)['\"]?", line)
            if "depends=" in line or "makedepends=" in line:
                for dep in dep_matches:
                    if dep not in ("depends", "makedepends", "="):
                        changes.append(
                            DependencyChange(
                                ecosystem="aur",
                                name=dep,
                                is_new=True,
                            )
                        )

    combined_script = "\n".join(install_script_lines) if install_script_lines else None
    if combined_script:
        for change in changes:
            change.install_script = combined_script

    return changes


_CARGO_DEP_REGEX = re.compile(
    r'^\+\s*([A-Za-z0-9._-]+)\s*=\s*(?:"([^"]+)"|\{\s*version\s*=\s*"([^"]+)")'
)


def parse_cargo_toml(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        match = _CARGO_DEP_REGEX.match(line)
        if match:
            name = match.group(1)
            version = match.group(2) or match.group(3)
            changes.append(
                DependencyChange(
                    ecosystem="crates.io",
                    name=name,
                    new_version=version,
                    is_new=True,
                )
            )
    return changes


# --- Capa Principal ---


@register_layer
class DepsLayer(AnalysisLayer):
    name: str = "dependencies"

    def __init__(
        self,
        cache_db_path: str | None = None,
        typosquat_dataset_dir: Path | None = None,
    ) -> None:
        self.cache = OSVCache(db_path=cache_db_path)
        self.typosquat_checker = TyposquatChecker(dataset_dir=typosquat_dataset_dir)

    def _query_osv(self, change: DependencyChange) -> tuple[dict[str, Any] | None, str | None]:
        cached = self.cache.get(change.name, change.ecosystem, change.new_version)
        if cached is not None:
            return cached, None

        body: dict[str, Any] = {
            "package": {"name": change.name, "ecosystem": change.ecosystem}
        }
        if change.new_version:
            body["version"] = change.new_version

        try:
            response = httpx.post(_OSV_API_URL, json=body, timeout=10.0)
            response.raise_for_status()
            res_data: dict[str, Any] = response.json()
            self.cache.set(change.name, change.ecosystem, change.new_version, res_data)
            return res_data, None
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            return None, f"No verificable por fallo de red en OSV ({exc!r})"

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
            if fname == "package.json":
                all_changes.extend(parse_package_json(hunk))
            elif fname in ("requirements.txt", "Pipfile"):
                all_changes.extend(parse_requirements_txt(hunk))
            elif fname == "PKGBUILD":
                all_changes.extend(parse_pkgbuild(hunk))
            elif fname == "Cargo.toml":
                all_changes.extend(parse_cargo_toml(hunk))

        if not all_changes:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification=(
                    "Se modificaron manifiestos pero no se añadieron ni "
                    "cambiaron dependencias."
                ),
            )

        scores: list[int] = []
        justifications: list[str] = []

        # 3. Analizar cada cambio
        for change in all_changes:
            pkg_score = 0
            pkg_notes: list[str] = []

            # A. Typosquatting
            is_typosquat, ref_pkg = self.typosquat_checker.is_typosquatting(
                change.name, change.ecosystem
            )
            if is_typosquat:
                pkg_score = max(pkg_score, 75)
                pkg_notes.append(
                    f"Posible typosquatting: '{change.name}' imita a '{ref_pkg}'"
                )

            # B. Script de instalación
            if change.install_script:
                findings = analyze_install_script_text(change.install_script)
                if findings:
                    pkg_score = max(pkg_score, 80)
                    pkg_notes.append(
                        f"Script de instalación sospechoso ({', '.join(findings)})"
                    )

            # C. Consulta OSV
            osv_res, osv_err = self._query_osv(change)
            if osv_err:
                pkg_notes.append(osv_err)
            elif osv_res and osv_res.get("vulns"):
                vulns = osv_res["vulns"]
                has_high_crit = False
                for v in vulns:
                    severities = v.get("severity", [])
                    database_specific = v.get("database_specific", {})
                    severity_str = str(severities) + str(database_specific)
                    if any(
                        keyword in severity_str.upper()
                        for keyword in ("CRITICAL", "HIGH", "9.", "10.")
                    ):
                        has_high_crit = True
                        break

                if has_high_crit:
                    pkg_score = max(pkg_score, 90)
                    pkg_notes.append(
                        f"Vulnerabilidad crítica/alta en OSV ({len(vulns)} vulns)"
                    )
                else:
                    pkg_score = max(pkg_score, 60)
                    pkg_notes.append(
                        f"Vulnerabilidades encontradas en OSV ({len(vulns)} vulnerabilidades)"
                    )

            # D. Si es nueva dependencia y no tuvo alertas mayores
            if change.is_new and pkg_score == 0:
                pkg_score = 10
                pkg_notes.append("Nueva dependencia verificada sin vulnerabilidades conocidas")

            scores.append(pkg_score)
            version_str = f"@{change.new_version}" if change.new_version else ""
            notes_str = "; ".join(pkg_notes) if pkg_notes else "OK"
            justifications.append(f"{change.name}{version_str} ({change.ecosystem}): {notes_str}")

        final_score = max(scores, default=0)
        final_justification = " | ".join(justifications)

        return LayerResult(
            layer_name=self.name,
            risk_score=final_score,
            justification=final_justification,
        )
