"""Capa de análisis estático (spec §4).

Ejecuta Semgrep sobre los parches de código modificados (`diff_hunk`),
cargando reglas Semgrep específicas para el lenguaje del archivo.

Sincronización inteligente de reglas:
1. Reutilización directa con 0 ms de sobrecoste si la caché local en
   .watchgate/rules_cache/ ha sido verificada en las últimas 24 horas.
2. Comprobación ultra-ligera por commit hash (`git ls-remote`) tras 24h.
3. Fallback transparente a la caché local si no hay red o hay timeout.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import (
    Confidence,
    FileStatus,
    LayerResult,
    NormalizedDiff,
    RiskCategory,
)

logger = logging.getLogger("watchgate.static")

# URL del repositorio externo de reglas Semgrep
SEMGREP_RULES_REPO_URL = "https://github.com/pablojimz/Repo-reglas-SEMGREP-y-YARA.git"

# Puntuación de riesgo por severidad oficial de Semgrep (spec §4)
SEVERITY_SCORE: dict[str, int] = {
    "INFO": 10,
    "WARNING": 30,
    "ERROR": 60,
}

# Tiempo TTL (24 horas) para verificación de actualización del repo de reglas
_CACHE_TTL_SECONDS = 86400
_GIT_TIMEOUT_SECONDS = 5.0


def _handle_remove_read_only(func: Any, path: str, exc_info: Any) -> None:
    """Error handler para shutil.rmtree que cambia permisos de solo lectura y reintenta."""
    if func in (os.unlink, shutil.rmtree) and issubclass(exc_info[0], PermissionError):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise exc_info[1]


@register_layer
class StaticLayer(AnalysisLayer):
    """Capa de análisis estático que ejecuta Semgrep sobre los parches modificados."""

    name: str = "static"

    def __init__(self, rules_dir_override: str | Path | None = None) -> None:
        self.rules_dir_override = Path(rules_dir_override) if rules_dir_override else None

    def _get_rules_dir(self) -> Path | None:
        """Obtiene la ruta al directorio de reglas Semgrep con sincronización inteligente.

        Prioridad de resolución:
        1. Override explícito por parámetro de constructor.
        2. Variable de entorno WATCHGATE_SEMGREP_RULES_DIR.
        3. Directorio local del proyecto rules/semgrep/ si contiene reglas.
        4. Caché local persistente en .watchgate/rules_cache/ con TTL de 24h y fallback offline.
        """
        # 1. Override por constructor
        if self.rules_dir_override and self.rules_dir_override.exists():
            return self.rules_dir_override

        # 2. Variable de entorno
        env_rules_dir = os.environ.get("WATCHGATE_SEMGREP_RULES_DIR")
        if env_rules_dir:
            env_path = Path(env_rules_dir)
            if env_path.exists():
                return env_path

        # 3. Directorio local del proyecto
        local_rules_dir = Path("rules/semgrep")
        if local_rules_dir.exists() and any(local_rules_dir.iterdir()):
            return local_rules_dir

        # 4. Caché persistente en .watchgate/rules_cache/
        cache_base = Path.home() / ".watchgate" / "rules_cache"
        repo_name = "Repo-reglas-SEMGREP-y-YARA"
        cached_repo_dir = cache_base / repo_name
        timestamp_file = cache_base / ".last_updated"

        now = time.time()
        should_check_remote = False

        if cached_repo_dir.exists():
            # Si pasaron más de 24 horas o se fuerza por entorno, se marca comprobación remota
            if os.environ.get("WATCHGATE_UPDATE_RULES", "").lower() in ("true", "1"):
                should_check_remote = True
            elif timestamp_file.exists():
                try:
                    last_check = float(timestamp_file.read_text(encoding="utf-8").strip())
                    if now - last_check >= _CACHE_TTL_SECONDS:
                        should_check_remote = True
                except Exception:  # noqa: BLE001
                    should_check_remote = True
            else:
                should_check_remote = True

            if not should_check_remote:
                # Caché local vigente (0 ms sobrecoste de red)
                return cached_repo_dir

            # Intentar comprobación ligera git ls-remote / pull
            try:
                logger.info("Comprobando actualizaciones remotas del repositorio de reglas...")
                cache_base.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "fetch", "--depth=1"],
                    cwd=str(cached_repo_dir),
                    capture_output=True,
                    timeout=_GIT_TIMEOUT_SECONDS,
                    check=False,
                )
                timestamp_file.write_text(str(now), encoding="utf-8")
                return cached_repo_dir
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "No se pudo actualizar el repo de reglas por red (%r). Usando caché local.", exc
                )
                return cached_repo_dir

        # Si la caché local no existe, clonar por primera vez
        try:
            cache_base.mkdir(parents=True, exist_ok=True)
            logger.info("Clonando repositorio de reglas Semgrep en %s", cached_repo_dir)
            res = subprocess.run(
                ["git", "clone", "--depth", "1", SEMGREP_RULES_REPO_URL, str(cached_repo_dir)],
                capture_output=True,
                text=True,
                timeout=15.0,
                check=False,
            )
            if res.returncode == 0 and cached_repo_dir.exists():
                timestamp_file.write_text(str(now), encoding="utf-8")
                return cached_repo_dir
            logger.warning("Fallo al clonar reglas Semgrep: %s", res.stderr)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error al clonar repositorio de reglas Semgrep: %r", exc)
            return None

    def _detect_language(self, file_path: str) -> str | None:
        """Infiere el lenguaje del archivo para mapearlo contra las reglas Semgrep."""
        extension = os.path.splitext(file_path)[1].lower()
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".go": "go",
            ".sh": "bash",
            ".bash": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".html": "html",
            ".rb": "ruby",
        }
        return language_map.get(extension)

    def _run_semgrep_on_file(
        self, temp_file_path: str, language: str, rules_dir: Path
    ) -> list[dict[str, Any]]:
        """Ejecuta Semgrep sobre un archivo temporal específico."""
        results: list[dict[str, Any]] = []

        # Buscar subdirectorio de reglas por lenguaje dentro del repo de reglas
        # Estrategia 1: rules/semgrep/custom/<language>
        # Estrategia 2: rules/semgrep/watchgate.yml
        # Estrategia 3: raiz del directorio de reglas
        config_paths: list[str] = []

        custom_lang_dir = rules_dir / "rules" / "semgrep" / "custom" / language
        watchgate_yml = rules_dir / "rules" / "semgrep" / "watchgate.yml"

        if custom_lang_dir.exists():
            config_paths.append(f"--config={custom_lang_dir}")
        if watchgate_yml.exists():
            config_paths.append(f"--config={watchgate_yml}")

        if not config_paths and rules_dir.exists():
            config_paths.append(f"--config={rules_dir}")

        if not config_paths:
            return results

        command = ["semgrep", "--json", "--quiet", temp_file_path] + config_paths

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20.0,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            if process.returncode not in (0, 1):  # Semgrep retorna 1 si encuentra hallazgos
                logger.debug("Semgrep retornó código %d: %s", process.returncode, process.stderr)

            if not process.stdout.strip():
                return results

            semgrep_output = json.loads(process.stdout)
            for finding in semgrep_output.get("results", []):
                extra = finding.get("extra", {})
                severity_str = str(extra.get("severity", "INFO")).upper()
                risk_score = SEVERITY_SCORE.get(severity_str, 10)

                results.append(
                    {
                        "tool": "semgrep",
                        "rule_id": finding.get("check_id", "semgrep-finding"),
                        "message": extra.get("message", "Hallazgo estático detectado"),
                        "line": finding.get("start", {}).get("line", 1),
                        "risk_score": risk_score,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Excepción al ejecutar Semgrep sobre %s: %r", temp_file_path, exc)

        return results

    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        rules_dir = self._get_rules_dir()
        if not rules_dir:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="No se pudieron cargar las reglas de análisis estático.",
                skipped=True,
                skip_reason="Reglas Semgrep no disponibles",
            )

        all_findings: list[dict[str, Any]] = []

        # Crear directorio temporal para aislar la escritura de parches (diff_hunks)
        temp_dir = tempfile.mkdtemp(prefix="watchgate_static_")
        try:
            for file_change in diff.files:
                if (
                    file_change.status == FileStatus.DELETED
                    or file_change.is_binary
                    or not file_change.diff_hunk.strip()
                ):
                    continue

                language = self._detect_language(file_change.path)
                if not language:
                    continue

                ext = os.path.splitext(file_change.path)[1] or ".txt"
                temp_file = tempfile.NamedTemporaryFile(
                    dir=temp_dir, suffix=ext, delete=False, mode="w", encoding="utf-8"
                )
                try:
                    temp_file.write(file_change.diff_hunk)
                    temp_file.close()

                    findings = self._run_semgrep_on_file(
                        temp_file.name, language, rules_dir=rules_dir
                    )
                    all_findings.extend(findings)
                finally:
                    if os.path.exists(temp_file.name):
                        try:
                            os.unlink(temp_file.name)
                        except Exception:  # noqa: BLE001
                            pass
        finally:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, onerror=_handle_remove_read_only)
                except Exception:  # noqa: BLE001
                    pass

        if not all_findings:
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="No se encontraron hallazgos estáticos sospechosos.",
            )

        # Regla explícita de la spec §4: tomar el MÁXIMO, NUNCA SUMAR
        max_risk_score = max((f["risk_score"] for f in all_findings), default=0)
        rule_ids = list(dict.fromkeys(f["rule_id"].split(".")[-1] for f in all_findings))
        rules_str = ", ".join(rule_ids[:3])

        justification = (
            f"Se encontraron {len(all_findings)} hallazgos estáticos con puntuación "
            f"máxima de {max_risk_score} (reglas: {rules_str})."
        )

        category = RiskCategory.OFUSCACION if max_risk_score >= 50 else RiskCategory.NINGUNA
        confidence = Confidence.MEDIA if max_risk_score > 0 else Confidence.BAJA

        return LayerResult(
            layer_name=self.name,
            risk_score=max_risk_score,
            justification=justification,
            category=category,
            confidence=confidence,
        )
