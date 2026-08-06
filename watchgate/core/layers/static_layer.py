"""static_layer.py

Ver docs/WatchGate_spec_implementacion_IA.md §4 — capa estática (Semgrep + YARA).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import shutil
import stat # Import stat module for file permissions
from typing import Any

from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import (
    Confidence,
    FileStatus,
    LayerResult,
    NormalizedDiff,
    RiskCategory,
)

# Configuración de logging
logger = logging.getLogger(__name__)

# URL del repositorio externo de reglas Semgrep
SEMGREP_RULES_REPO_URL = "https://github.com/pablojimz/Repo-reglas-SEMGREP-y-YARA.git"


def _handle_remove_read_only(func, path, exc_info):
    """Error handler for shutil.rmtree that changes read-only permissions and retries."""
    # If the error is an access error, change the file's permissions to writable and retry.
    if func in (os.unlink, shutil.rmtree) and exc_info[0] is PermissionError:
        os.chmod(path, stat.S_IWRITE) # Change to writable
        func(path) # Retry the original function
    else:
        raise # Re-raise if not a permission error


@register_layer
class StaticLayer(AnalysisLayer):
    """Capa de análisis estático que ejecuta Semgrep en los archivos modificados.

    Detecta el lenguaje del archivo y carga reglas Semgrep personalizadas
    específicas para ese lenguaje desde un repositorio externo.
    """

    name: str = "static"

    def __init__(self) -> None:
        self._rules_repo_path: str | None = None
        self._temp_dir: str | None = None

    def _clone_semgrep_rules_repo(self) -> str | None:
        """Clona el repositorio de reglas Semgrep en un directorio temporal.

        Devuelve la ruta al repositorio clonado o None si falla.
        """
        if self._rules_repo_path and os.path.exists(self._rules_repo_path):
            return self._rules_repo_path

        try:
            # Usar un directorio temporal para clonar el repo
            self._temp_dir = tempfile.mkdtemp(prefix="semgrep_rules_")
            repo_name = SEMGREP_RULES_REPO_URL.split("/")[-1].replace(".git", "")
            self._rules_repo_path = os.path.join(self._temp_dir, repo_name)

            logger.info(f"Cloning Semgrep rules repository to {self._rules_repo_path}")
            subprocess.run(
                ["git", "clone", "--depth", "1", SEMGREP_RULES_REPO_URL, self._rules_repo_path],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
            logger.info("Semgrep rules repository cloned successfully.")
            return self._rules_repo_path
        except subprocess.CalledProcessError as e:
            logger.exception(f"Error cloning Semgrep rules repository: {e.stderr}")
            if self._temp_dir and os.path.exists(self._temp_dir):
                shutil.rmtree(self._temp_dir)
            self._rules_repo_path = None
            self._temp_dir = None
            return None
        except FileNotFoundError:
            logger.exception("Git command not found. Is Git installed and in PATH?")
            if self._temp_dir and os.path.exists(self._temp_dir):
                shutil.rmtree(self._temp_dir)
            self._rules_repo_path = None
            self._temp_dir = None
            return None

    def _cleanup_rules_repo(self) -> None:
        """Limpia el directorio temporal del repositorio de reglas clonado."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            logger.info(f"Cleaning up temporary rules directory: {self._temp_dir}")
            # Use the custom error handler for rmtree
            shutil.rmtree(self._temp_dir, onerror=_handle_remove_read_only)
            self._rules_repo_path = None
            self._temp_dir = None

    def __del__(self) -> None:
        """Asegura la limpieza del repositorio clonado al destruir la instancia."""
        self._cleanup_rules_repo()

    def _detect_language(self, file_path: str) -> str | None:
        """Detecta el lenguaje de un archivo basándose en su extensión."""
        extension = os.path.splitext(file_path)[1].lower()
        language_map = {
            ".html": "html", # Explicitly added for HTML files
            ".py": "python",
            ".js": "javascript", # Explicitly added for JavaScript files
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".c": "c",
            ".h": "c",
            ".go": "go",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            # Añadir más lenguajes según la estructura de reglas Semgrep.
        }
        return language_map.get(extension)

    def _run_semgrep(self, file_path: str, language: str) -> list[dict[str, Any]]:
        """Ejecuta Semgrep en un archivo y parsea los resultados."""
        results: list[dict[str, Any]] = []

        rules_repo_path = self._clone_semgrep_rules_repo()
        if not rules_repo_path:
            logger.error("Could not clone Semgrep rules repository. Skipping Semgrep analysis.")
            return []

        # La estructura dentro del repo clonado es `Repo-reglas-SEMGREP-y-YARA/rules/semgrep/custom/<language>/`
        #
        custom_rules_path = os.path.join(rules_repo_path, "rules", "semgrep", "custom", language)

        config_paths: list[str] = []
        if os.path.exists(custom_rules_path):
            config_paths.append(f"--config={custom_rules_path}")

        if not config_paths:
            logger.warning(f"No Semgrep rules found for language: {language} in cloned repo.")
            return []

        command = [
            "semgrep",
            "--json",
            "--quiet",
            file_path,
        ] + config_paths

        try:
            logger.debug(f"Running Semgrep command: {' '.join(command)}")
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
            semgrep_output = json.loads(process.stdout)
            for finding in semgrep_output.get("results", []):
                # Simplificar el parseo de Semgrep a un formato común
                #
                severity = finding["extra"]["severity"]
                risk_score = 0
                if severity == "ERROR":
                    risk_score = 100
                elif severity == "WARNING":
                    risk_score = 50
                elif severity == "INFO":
                    risk_score = 10

                results.append(
                    {
                        "tool": "semgrep",
                        "rule_id": finding["check_id"],
                        "message": finding["extra"]["message"],
                        "line": finding["start"]["line"],
                        "risk_score": risk_score,
                    }
                )
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.exception(f"Error running Semgrep on {file_path}: {e}")
        except FileNotFoundError:
            logger.exception("Semgrep command not found. Is Semgrep installed and in PATH?")
        return results

    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        all_findings: list[dict[str, Any]] = []
        max_risk_score = 0

        for file_change in diff.files:
            if file_change.status == FileStatus.DELETED or file_change.is_binary:
                continue

            if file_change.diff_hunk:
                target_file_path = file_change.path

                language = self._detect_language(target_file_path)
                if not language:
                    logger.info(
                        f"Skipping static analysis for unknown language file: {target_file_path}"
                    )
                    continue

                semgrep_findings = self._run_semgrep(target_file_path, language)
                all_findings.extend(semgrep_findings)

        if all_findings:
            max_risk_score = max(f["risk_score"] for f in all_findings)
            justification = (
                f"Se encontraron {len(all_findings)} hallazgos estáticos con una "
                f"puntuación de riesgo máxima de {max_risk_score}."
            )
        else:
            justification = "No se encontraron hallazgos estáticos."

        category = RiskCategory.NINGUNA
        confidence = Confidence.BAJA

        if max_risk_score > 0:
            confidence = Confidence.MEDIA
            category = RiskCategory.OFUSCACION

        return LayerResult(
            layer_name=self.name,
            risk_score=max_risk_score,
            justification=justification,
            category=category,
            confidence=confidence,
            skipped=False,
            skip_reason=None,
        )
