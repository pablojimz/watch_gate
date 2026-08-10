"""Capa de vulnerabilidades conocidas en dependencias (extraída de deps_layer.py).

Separada a petición explícita: "diferenciar entre vulnerabilidades que
tenga el código y posibles ataques que te están haciendo en el repositorio,
y poder desactivar esa capa de vulnerabilidades". Antes de esto,
`deps_layer.py` mezclaba en una sola nota dos señales de naturaleza
distinta:

- Vulnerabilidades conocidas (CVEs vía OSV.dev): una debilidad del propio
  ecosistema/paquete, no evidencia de que este PR concreto sea un ataque --
  un `pip install django==3.0` con una CVE conocida no es sospechoso, es
  simplemente una versión desactualizada. Muchos equipos ya cubren esto con
  Dependabot/Snyk/similar y no quieren que WatchGate lo repita ni lo pese en
  el score de "esto parece un ataque".
- Señales de ataque a la cadena de suministro (typosquatting, scripts de
  instalación sospechosos, instalación directa por URL/Git): esto sí es
  evidencia de intención maliciosa concreta en el PR, y es la parte que
  sigue en `deps_layer.py`.

Ambas capas parsean el mismo diff con los mismos parsers de
`layers/_shared.py` de forma independiente (sin pasarse estado entre sí,
spec §9/A.1: cada capa se ejecuta en paralelo sin depender de las demás) --
evaluar OSV es la única responsabilidad de esta capa; typosquatting/scripts/
URL directa siguen sin tocarse en deps_layer.py.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from watchgate.core.layers._shared import (
    DEPENDENCY_MANIFEST_FILENAMES,
    DependencyChange,
    parse_cargo_toml,
    parse_composer_json,
    parse_go_mod,
    parse_package_json,
    parse_pkgbuild,
    parse_requirements_txt,
)
from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import Finding, LayerResult, NormalizedDiff

logger = logging.getLogger("watchgate.vulnerabilities")

_OSV_API_URL = "https://api.osv.dev/v1/query"
_OSV_QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"
_CACHE_TTL_HOURS = 24
_HARD_MAX_BATCH_SIZE = 20


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
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
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
                if datetime.now(UTC) - fetched_at > timedelta(hours=_CACHE_TTL_HOURS):
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


@register_layer
class VulnerabilitiesLayer(AnalysisLayer):
    name: str = "vulnerabilities"

    def __init__(
        self,
        cache_db_path: str | None = None,
        max_osv_queries: int = 20,
    ) -> None:
        self.cache = OSVCache(db_path=cache_db_path)
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
            q: dict[str, Any] = {"package": {"name": change.name, "ecosystem": change.ecosystem}}
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

        body: dict[str, Any] = {"package": {"name": change.name, "ecosystem": change.ecosystem}}
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
        manifest_files = [
            f for f in diff.files if Path(f.path).name in DEPENDENCY_MANIFEST_FILENAMES
        ]
        if not manifest_files:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="No se han modificado manifiestos de dependencias.",
            )

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
            elif fname == "go.mod":
                parsed = parse_go_mod(hunk)
            elif fname == "composer.json":
                parsed = parse_composer_json(hunk)
            for ch in parsed:
                ch.manifest_path = file_change.path
            all_changes.extend(parsed)

        # Sin nombre de paquete (p. ej. solo cambió un script de instalación,
        # sin dependencias nuevas) no hay nada que consultar en OSV -- esa
        # señal es de deps_layer.py, no de esta capa.
        named_changes = [c for c in all_changes if c.name and "(scripts)" not in c.name]
        if not named_changes:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification=(
                    "Se modificaron manifiestos pero no hay dependencias nuevas que consultar."
                ),
            )

        osv_batch_results = self._query_osv_batch(named_changes)

        scores: list[int] = []
        justifications: list[str] = []
        structured_findings: list[Finding] = []

        for idx, change in enumerate(named_changes):
            pkg_score = 0
            note = "Sin vulnerabilidades conocidas en OSV."

            osv_res, osv_err = osv_batch_results.get(idx, (None, None))
            if osv_err:
                note = osv_err
            elif osv_res and osv_res.get("vulns"):
                vulns = osv_res["vulns"]
                has_high_crit = any(_is_high_or_critical_vuln(v) for v in vulns)
                if has_high_crit:
                    pkg_score = 90
                    note = f"Vulnerabilidad crítica/alta en OSV ({len(vulns)} vulns)"
                else:
                    pkg_score = 60
                    note = f"Vulnerabilidades encontradas en OSV ({len(vulns)} vulnerabilidades)"

            scores.append(pkg_score)
            version_str = f"@{change.new_version}" if change.new_version else ""
            justifications.append(f"{change.name}{version_str} ({change.ecosystem}): {note}")

            if pkg_score > 0:
                m_path = change.manifest_path if change.manifest_path else change.name
                structured_findings.append(
                    Finding(
                        file_path=m_path,
                        rule_id=f"vulnerability-{change.ecosystem.lower()}",
                        message=f"{change.name}{version_str}: {note}",
                        severity="error" if pkg_score >= 60 else "warning",
                    )
                )

        final_score = max(scores, default=0)
        final_justification = " | ".join(justifications)

        return LayerResult(
            layer_name=self.name,
            risk_score=final_score,
            justification=final_justification,
            findings=structured_findings,
        )
