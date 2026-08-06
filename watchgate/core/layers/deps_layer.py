"""Capa de dependencias (spec §5).

Analiza cambios en manifiestos de dependencias (package.json, requirements.txt,
PKGBUILD, Cargo.toml) evaluando:
1. Vulnerabilidades conocidas en OSV (api.osv.dev) con caché SQLite (TTL 24h).
2. Typosquatting comparando contra datasets de paquetes populares con rapidfuzz.
3. Scripts de instalación sospechosos (preinstall/postinstall/PKGBUILD).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
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

logger = logging.getLogger("watchgate.deps")

_OSV_API_URL = "https://api.osv.dev/v1/query"
_OSV_QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"
_CACHE_TTL_HOURS = 24
_HARD_MAX_BATCH_SIZE = 20


class DependencyChange(BaseModel):
    ecosystem: str  # "npm" | "PyPI" | "aur" | "crates.io"
    name: str
    old_version: str | None = None
    new_version: str | None = None
    is_new: bool = True
    install_script: str | None = None
    is_direct_url: bool = False


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
            self._conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallo al inicializar la base de datos de caché OSV (%r)", exc)
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
                if datetime.now(timezone.utc) - fetched_at > timedelta(hours=_CACHE_TTL_HOURS):
                    return None
                data: dict[str, Any] = json.loads(resp_json)
                return data
            except Exception as exc:  # noqa: BLE001
                logger.debug("Fallo al leer de la caché OSV para %s (%r)", name, exc)
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
        now_str = datetime.now(timezone.utc).isoformat()
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
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallo al guardar en caché OSV para %s (%r)", name, exc)

    def set_many(
        self,
        records: list[tuple[str, str, str | None, dict[str, Any]]],
    ) -> None:
        if self._conn is None or not records:
            return
        now_str = datetime.now(UTC).isoformat()
        rows = [
            (name, ecosystem, version or "", json.dumps(resp), now_str)
            for name, ecosystem, version, resp in records
        ]
        with self._lock:
            try:
                self._conn.executemany(
                    """
                    INSERT OR REPLACE INTO osv_cache
                    (name, ecosystem, version, response_json, fetched_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                self._conn.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallo al guardar lote en caché OSV (%r)", exc)

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


# --- Parsers de Manifiestos ---

_PKG_JSON_DEP_REGEX = re.compile(r'^\+\s*"([^"]+)":\s*"([^"]+)"')
_PKG_JSON_SCRIPT_REGEX = re.compile(r'^\+\s*"(preinstall|postinstall|install)":\s*"([^"]+)"')


def _is_npm_url_version(version_str: str) -> bool:
    v = version_str.lower()
    return (
        v.startswith(
            (
                "git+",
                "git://",
                "http://",
                "https://",
                "file:",
                "github:",
                "bitbucket:",
                "gitlab:",
            )
        )
        or "github.com" in v
        or v.endswith((".tgz", ".tar.gz", ".git"))
    )


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
            is_direct = _is_npm_url_version(dep_version)
            changes.append(
                DependencyChange(
                    ecosystem="npm",
                    name=dep_name,
                    new_version=dep_version,
                    is_new=True,
                    is_direct_url=is_direct,
                )
            )

    if install_scripts:
        combined_script = "; ".join(install_scripts)
        if changes:
            for change in changes:
                change.install_script = combined_script
        else:
            changes.append(
                DependencyChange(
                    ecosystem="npm",
                    name="package.json (scripts)",
                    is_new=False,
                    install_script=combined_script,
                )
            )

    return changes


_REQ_EGG_REGEX = re.compile(r"#egg=([A-Za-z0-9._-]+)")
_REQ_AT_REGEX = re.compile(
    r"^\+\s*([A-Za-z0-9._-]+)\s*@\s*(https?://|git\+|file://|http://)"
)
_REQ_LINE_REGEX = re.compile(
    r"^\+\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:==|>=|<=|~=|!=|>|<)?\s*([A-Za-z0-9._-]*)?"
)

def parse_requirements_txt(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        content = line[1:].strip()
        if not content or content.startswith("#") or content.startswith("-r"):
            continue

        content = re.sub(r"^-(?:-?editable|e)\s+", "", content).strip()

        is_direct_url = False
        name: str | None = None
        version: str | None = None

        if (
            content.startswith(("git+", "http://", "https://", "file://", "svn+", "hg+"))
            or " @ " in content
        ):
            is_direct_url = True
            egg_match = _REQ_EGG_REGEX.search(content)
            at_match = _REQ_AT_REGEX.match(line)
            if egg_match:
                name = egg_match.group(1)
                version = content
            elif at_match:
                name = at_match.group(1)
                version = content
            else:
                clean_url = content.split("#")[0].rstrip("/")
                pkg_candidate = (
                    clean_url.split("/")[-1]
                    .replace(".git", "")
                    .replace(".whl", "")
                    .replace(".tar.gz", "")
                )
                name = pkg_candidate if pkg_candidate else "unknown-url-pkg"
                version = content
        else:
            match = _REQ_LINE_REGEX.match(line)
            if match:
                name = match.group(1)
                version = match.group(2) if match.group(2) else None

        if name:
            changes.append(
                DependencyChange(
                    ecosystem="PyPI",
                    name=name,
                    new_version=version,
                    is_new=True,
                    is_direct_url=is_direct_url,
                )
            )
    return changes


_PKGBUILD_DEP_REGEX = re.compile(r"^\+\s*(?:depends|makedepends)\+?=\((.*?)\)")

def parse_pkgbuild(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    install_script_lines: list[str] = []

    for line in diff_hunk.splitlines():
        if line.startswith("+") and not line.startswith("++"):
            install_script_lines.append(line[1:])
            dep_match = _PKGBUILD_DEP_REGEX.search(line)
            if dep_match:
                deps_body = dep_match.group(1)
                deps = re.findall(r"['\"]?([a-zA-Z0-9._-]+)['\"]?", deps_body)
                for dep in deps:
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
    r'^\+\s*([A-Za-z0-9._-]+)\s*=\s*(?:"([^"]+)"|\{\s*(.*?)\s*\})'
)

def parse_cargo_toml(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        match = _CARGO_DEP_REGEX.match(line)
        if match:
            name = match.group(1)
            is_direct = False
            version: str | None = None

            if match.group(2):
                version = match.group(2)
            elif match.group(3):
                inner = match.group(3)
                v_match = re.search(r'version\s*=\s*"([^"]+)"', inner)
                if v_match:
                    version = v_match.group(1)
                else:
                    version = inner
                if "git" in inner or "path" in inner:
                    is_direct = True

            changes.append(
                DependencyChange(
                    ecosystem="crates.io",
                    name=name,
                    new_version=version,
                    is_new=True,
                    is_direct_url=is_direct,
                )
            )
    return changes


def _is_high_or_critical_vuln(vuln: dict[str, Any]) -> bool:
    """Evalúa si una vulnerabilidad de OSV es de severidad ALTA o CRÍTICA.

    Inspecciona severidades nominales ("CRITICAL", "HIGH") en database_specific y
    ecosystem_specific, o puntuaciones CVSS >= 7.0.
    """
    database_specific = vuln.get("database_specific") or {}
    ecosystem_specific = vuln.get("ecosystem_specific") or {}

    db_sev = str(database_specific.get("severity", "")).upper()
    gh_sev = str(database_specific.get("github_reviewed_severity", "")).upper()
    eco_sev = str(ecosystem_specific.get("severity", "")).upper()

    if any(s in ("CRITICAL", "HIGH") for s in (db_sev, gh_sev, eco_sev)):
        return True

    cvss_obj = database_specific.get("cvss")
    if isinstance(cvss_obj, dict):
        score = cvss_obj.get("score")
        if isinstance(score, int | float) and score >= 7.0:
            return True
        if isinstance(score, str):
            try:
                if float(score) >= 7.0:
                    return True
            except ValueError:
                pass

    for s_entry in vuln.get("severity", []):
        if not isinstance(s_entry, dict):
            continue
        score_val = str(s_entry.get("score", "")).upper()
        if "CRITICAL" in score_val or "HIGH" in score_val:
            return True
        try:
            if float(score_val) >= 7.0:
                return True
        except ValueError:
            pass

    return False


# --- Capa Principal ---


@register_layer
class DepsLayer(AnalysisLayer):
    name: str = "dependencies"

    def __init__(
        self,
        cache_db_path: str | None = None,
        typosquat_dataset_dir: Path | None = None,
        max_osv_queries: int = 20,
    ) -> None:
        self.cache = OSVCache(db_path=cache_db_path)
        self.typosquat_checker = TyposquatChecker(dataset_dir=typosquat_dataset_dir)
        self.max_osv_queries = min(max(1, max_osv_queries), _HARD_MAX_BATCH_SIZE)

    def _query_osv_batch(
        self, changes: list[DependencyChange]
    ) -> dict[int, tuple[dict[str, Any] | None, str | None]]:
        results: dict[int, tuple[dict[str, Any] | None, str | None]] = {}

        uncached_indices: list[int] = []
        for idx, change in enumerate(changes):
            cached = self.cache.get(change.name, change.ecosystem, change.new_version)
            if cached is not None:
                results[idx] = (cached, None)
            else:
                uncached_indices.append(idx)

        if not uncached_indices:
            return results

        to_fetch_indices = uncached_indices[: self.max_osv_queries]
        over_limit_indices = uncached_indices[self.max_osv_queries :]

        for idx in over_limit_indices:
            results[idx] = (None, "OSV omitido (límite de consultas batch alcanzado)")

        if not to_fetch_indices:
            return results

        queries = []
        for idx in to_fetch_indices:
            change = changes[idx]
            q: dict[str, Any] = {
                "package": {"name": change.name, "ecosystem": change.ecosystem}
            }
            if change.new_version and not change.is_direct_url:
                q["version"] = change.new_version
            queries.append(q)

        try:
            response = httpx.post(
                _OSV_QUERYBATCH_URL,
                json={"queries": queries},
                timeout=10.0,
            )
            response.raise_for_status()
            res_data: dict[str, Any] = response.json()
            batch_results = res_data.get("results", [])

            to_cache: list[tuple[str, str, str | None, dict[str, Any]]] = []

            for idx, res_item in zip(to_fetch_indices, batch_results, strict=False):
                change = changes[idx]
                item_data = res_item if isinstance(res_item, dict) else {}
                results[idx] = (item_data, None)
                to_cache.append((change.name, change.ecosystem, change.new_version, item_data))

            if to_cache:
                self.cache.set_many(to_cache)

        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            for idx in to_fetch_indices:
                results[idx] = (
                    None,
                    f"No verificable por fallo de red en OSV ({exc!r})",
                )

        return results

    def _query_osv(self, change: DependencyChange) -> tuple[dict[str, Any] | None, str | None]:
        cached = self.cache.get(change.name, change.ecosystem, change.new_version)
        if cached is not None:
            return cached, None

        body: dict[str, Any] = {
            "package": {"name": change.name, "ecosystem": change.ecosystem}
        }
        if change.new_version and not change.is_direct_url:
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

        # Batch OSV query for all changes
        osv_batch_results = self._query_osv_batch(all_changes)

        scores: list[int] = []
        justifications: list[str] = []

        # 3. Analizar cada cambio
        for idx, change in enumerate(all_changes):
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

            # C. Instalación directa por URL/Git
            if change.is_direct_url:
                pkg_score = max(pkg_score, 75)
                pkg_notes.append(
                    f"Instalación directa desde URL/Git ({change.new_version or change.name})"
                )

            # D. Consulta OSV
            osv_res, osv_err = osv_batch_results.get(idx, (None, None))
            if osv_err:
                pkg_notes.append(osv_err)
            elif osv_res and osv_res.get("vulns"):
                vulns = osv_res["vulns"]
                has_high_crit = any(_is_high_or_critical_vuln(v) for v in vulns)

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

            # E. Si es nueva dependencia y no tuvo alertas mayores
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
