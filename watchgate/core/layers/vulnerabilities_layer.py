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
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import Engine, create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from watchgate.core.layers._shared import (
    DEPENDENCY_MANIFEST_FILENAMES,
    DependencyChange,
    parse_manifest_file_change,
)
from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import Confidence, Finding, LayerResult, NormalizedDiff, ThreatNature

logger = logging.getLogger("watchgate.vulnerabilities")

_OSV_API_URL = "https://api.osv.dev/v1/query"
_OSV_QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"
_CACHE_TTL_HOURS = 24
# OSV no documenta un tope de tamaño de lote en /v1/querybatch (probado en
# vivo con 60 consultas en una sola llamada, sin problema); 20 era un límite
# autoimpuesto sin motivo real que además se aplicaba SIEMPRE, ignorando
# cualquier valor mayor que un admin configurase vía policy
# (max_dependency_checks) -- ver auditoría. 200 sigue acotado (payload/
# timeout razonables) pero dejar de recortar en silencio configuraciones
# explícitas.
_HARD_MAX_BATCH_SIZE = 200


class _OSVCacheBase(DeclarativeBase):
    """Base declarativa propia y aislada -- esta caché vive en su propio
    fichero SQLite (`~/.watchgate/cache.db`, o el que resuelva
    `_resolve_db_path`), una TERCERA base de datos física distinta tanto de
    la Engine DB como del Dashboard DB, así que necesita su propio
    `MetaData` igual que ellas."""


class OSVCacheEntry(_OSVCacheBase):
    __tablename__ = "osv_cache"

    name: Mapped[str] = mapped_column(primary_key=True)
    ecosystem: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(primary_key=True)
    response_json: Mapped[str] = mapped_column(nullable=False)
    fetched_at: Mapped[str] = mapped_column(nullable=False)


class OSVCache:
    """Caché SQLite para respuestas de OSV.dev con TTL de 24 horas y tolerancia a fallos
    en la ruta del archivo (fallback a /tmp o :memory: si la ruta home falla).
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._engine: Engine | None = None
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
            connect_args = {"check_same_thread": False, "timeout": 30.0}
            if self.db_path == ":memory:":
                # SQLite en memoria es POR CONEXIÓN: sin `StaticPool` (que
                # mantiene una única conexión física viva para todo el
                # engine), cada checkout del pool vería una base de datos en
                # blanco distinta -- el `sqlite3.Connection` original,
                # reusado tal cual durante toda la vida de la instancia,
                # evitaba esto de forma implícita al ser una única conexión.
                engine = create_engine(
                    "sqlite:///:memory:", connect_args=connect_args, poolclass=StaticPool
                )
            else:
                engine = create_engine(f"sqlite:///{self.db_path}", connect_args=connect_args)
            with self._lock:
                _OSVCacheBase.metadata.create_all(engine)
            self._engine = engine
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallo al inicializar la base de datos de caché OSV (%r)", exc)
            self._engine = None

    def get(self, name: str, ecosystem: str, version: str | None) -> dict[str, Any] | None:
        if self._engine is None:
            return None
        v_key = version or ""
        with self._lock:
            try:
                with Session(self._engine) as session:
                    record = session.get(OSVCacheEntry, (name, ecosystem, v_key))
                if record is None:
                    return None
                fetched_at = datetime.fromisoformat(record.fetched_at)
                if datetime.now(UTC) - fetched_at > timedelta(hours=_CACHE_TTL_HOURS):
                    return None
                data: dict[str, Any] = json.loads(record.response_json)
                return data
            except Exception as exc:  # noqa: BLE001
                logger.debug("Fallo al leer de la caché OSV para %s (%r)", name, exc)
                return None

    def _upsert(
        self, session: Session, name: str, ecosystem: str, version: str, resp_json: str, now: str
    ) -> None:
        table = OSVCacheEntry.__table__
        stmt = sqlite_insert(table).values(  # type: ignore[arg-type]
            name=name,
            ecosystem=ecosystem,
            version=version,
            response_json=resp_json,
            fetched_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c.name, table.c.ecosystem, table.c.version],
            set_={
                "response_json": stmt.excluded.response_json,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        session.execute(stmt)

    def set(
        self,
        name: str,
        ecosystem: str,
        version: str | None,
        response_data: dict[str, Any],
    ) -> None:
        if self._engine is None:
            return
        v_key = version or ""
        now_str = datetime.now(UTC).isoformat()
        resp_json = json.dumps(response_data)
        with self._lock:
            try:
                with Session(self._engine) as session:
                    self._upsert(session, name, ecosystem, v_key, resp_json, now_str)
                    session.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallo al guardar en caché OSV para %s (%r)", name, exc)

    def set_many(
        self,
        records: list[tuple[str, str, str | None, dict[str, Any]]],
    ) -> None:
        if self._engine is None or not records:
            return
        now_str = datetime.now(UTC).isoformat()
        with self._lock:
            try:
                with Session(self._engine) as session:
                    for name, ecosystem, version, resp in records:
                        self._upsert(
                            session, name, ecosystem, version or "", json.dumps(resp), now_str
                        )
                    session.commit()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallo al guardar lote en caché OSV (%r)", exc)

    def close(self) -> None:
        if self._engine is not None:
            try:
                self._engine.dispose()
            except Exception:  # noqa: BLE001
                pass
            self._engine = None


_CVSS3_WEIGHTS_CIA = {"N": 0.0, "L": 0.22, "H": 0.56}
_CVSS3_WEIGHTS_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_CVSS3_WEIGHTS_AC = {"L": 0.77, "H": 0.44}
_CVSS3_WEIGHTS_PR_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_CVSS3_WEIGHTS_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}
_CVSS3_WEIGHTS_UI = {"N": 0.85, "R": 0.62}


def _cvss_roundup(value: float) -> float:
    """Redondeo "hacia arriba" de la spec CVSS -- un `round()` normal usa
    redondeo bancario y da resultados distintos de los publicados (p.ej.
    4.02 debe dar 4.1, no 4.0); el truco de enteros es el que usa la
    calculadora oficial de FIRST.org para evitar el error de coma
    flotante."""
    int_value = int(round(value * 100000))
    if int_value % 10000 == 0:
        return int_value / 100000
    return (int_value // 10000 + 1) / 10


def _cvss3_base_score(vector: str) -> float | None:
    """Calcula el Base Score de un vector CVSS v3.0/3.1 con la fórmula
    oficial (FIRST.org). OSV solo expone el vector en `severity[].score`
    (p.ej. "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H"), nunca un número
    ni la palabra "HIGH"/"CRITICAL" -- sin parsearlo de verdad, esta es la
    única fuente de severidad para avisos que no traen
    `database_specific`/`ecosystem_specific` (frecuente fuera de GitHub
    Security Advisories, p.ej. PyPI/PySec). Devuelve None si el vector no
    es CVSS v3 o le falta alguna métrica obligatoria."""
    if not vector.startswith("CVSS:3."):
        return None
    metrics: dict[str, str] = {}
    for part in vector.split("/"):
        if ":" not in part:
            continue
        key, _, value = part.partition(":")
        metrics[key] = value

    try:
        av = _CVSS3_WEIGHTS_AV[metrics["AV"]]
        ac = _CVSS3_WEIGHTS_AC[metrics["AC"]]
        ui = _CVSS3_WEIGHTS_UI[metrics["UI"]]
        scope_changed = metrics["S"] == "C"
        pr_table = _CVSS3_WEIGHTS_PR_CHANGED if scope_changed else _CVSS3_WEIGHTS_PR_UNCHANGED
        pr = pr_table[metrics["PR"]]
        c = _CVSS3_WEIGHTS_CIA[metrics["C"]]
        i = _CVSS3_WEIGHTS_CIA[metrics["I"]]
        a = _CVSS3_WEIGHTS_CIA[metrics["A"]]
    except KeyError:
        return None

    iss = 1 - ((1 - c) * (1 - i) * (1 - a))
    if iss <= 0:
        return 0.0
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if scope_changed else 6.42 * iss
    if impact <= 0:
        return 0.0

    exploitability = 8.22 * av * ac * pr * ui
    raw = (impact + exploitability) * (1.08 if scope_changed else 1.0)
    return _cvss_roundup(min(raw, 10.0))


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
        vector = s_entry.get("score")
        # Campo estándar de OSV (`severity[].score`): SIEMPRE un vector CVSS
        # ("CVSS:3.1/AV:N/..."), nunca un número ni "HIGH"/"CRITICAL" en
        # texto -- confirmado en vivo contra la API real de OSV. Un
        # `float()`/substring sobre esto nunca acierta; hay que calcular el
        # base score de verdad.
        if not isinstance(vector, str):
            continue
        base_score = _cvss3_base_score(vector)
        if base_score is not None and base_score >= 7.0:
            return True

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
            all_changes.extend(parse_manifest_file_change(file_change))

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
            unverified = False

            # Default explícito distinto de "sin vulnerabilidades": un
            # índice que falte aquí (p.ej. OSV devolvió menos resultados de
            # los pedidos en el batch, sin lanzar excepción) antes se leía
            # como "no verificable" indistinguible de "revisado y limpio"
            # -- ver auditoría. Ahora ese hueco también cuenta como no
            # verificado en vez de asumir que está limpio.
            osv_res, osv_err = osv_batch_results.get(
                idx, (None, "Respuesta de OSV incompleta para esta dependencia")
            )
            if osv_err:
                note = osv_err
                unverified = True
            elif osv_res and osv_res.get("vulns"):
                vulns = osv_res["vulns"]
                has_high_crit = any(_is_high_or_critical_vuln(v) for v in vulns)
                if has_high_crit or len(vulns) >= 5:
                    pkg_score = 90
                    note = f"Vulnerabilidad crítica/alta o acumulada en OSV ({len(vulns)} vulns)"
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
            elif unverified:
                # No es "sin vulnerabilidades", es "no lo sabemos" -- visible
                # como finding propio (antes solo vivía enterrado en la
                # justificación conjunta, sin afectar el score ni aparecer
                # como algo a revisar aparte).
                m_path = change.manifest_path if change.manifest_path else change.name
                structured_findings.append(
                    Finding(
                        file_path=m_path,
                        rule_id=f"vulnerability-unverified-{change.ecosystem.lower()}",
                        message=f"{change.name}{version_str}: {note}",
                        severity="warning",
                    )
                )

        final_score = max(scores, default=0)
        final_justification = " | ".join(justifications)

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
            confidence=confidence,
            threat_nature=ThreatNature.VULNERABILITY if final_score > 0 else None,
        )
