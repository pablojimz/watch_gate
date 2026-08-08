"""Capa de análisis estático (spec §4).

Ejecuta Semgrep sobre los parches de código modificados (`diff_hunk`),
cargando reglas Semgrep específicas para el lenguaje del archivo: las
propias (`rules/semgrep/custom/<lenguaje>`), las de terceros relevantes
para ese lenguaje (`rules/semgrep/third-party/<vendor>/<carpeta>`) y las
reglas de patrones genéricos (`rules/semgrep/custom/regex`, secretos
hardcodeados etc.), que se aplican siempre con independencia del lenguaje.

Resolución del directorio de reglas (`_get_rules_dir`), en orden:
1. Override explícito por parámetro de constructor.
2. Variable de entorno WATCHGATE_SEMGREP_RULES_DIR.
3. Directorio local del proyecto `rules/semgrep/` -- esta es la ruta que
   pueblan y verifican por hash .github/workflows/sync-rules.yml y
   reconcile-rules.yml (ver docs/integracion_repo_reglas.md); en este
   propio repo SIEMPRE debería resolverse aquí.
4. Caché local persistente en .watchgate/rules_cache/ (TTL 24h, clon
   directo de GitHub sin ninguna verificación de hash). Es un ÚLTIMO
   RECURSO pensado para un consumidor externo que instale `watchgate`
   como paquete sin el checkout de reglas ya sincronizado -- nunca
   debería alcanzarse en el análisis de PRs de este propio repo, y si se
   alcanza, se loggea como warning explícito porque implica ejecutar
   reglas sin pasar por la verificación de integridad.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import (
    Confidence,
    FileStatus,
    Finding,
    LayerResult,
    NormalizedDiff,
    RiskCategory,
    ThreatNature,
    compute_dominant_threat_nature,
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

# Categoría de reglas custom/ que se aplica SIEMPRE, con independencia del
# lenguaje detectado (patrones de secretos hardcodeados, cadenas de
# conexión, etc. -- no son específicos de un lenguaje).
_ALWAYS_ON_CUSTOM_CATEGORY = "regex"

# Mapeo EXPLÍCITO (a mano, nunca adivinado por coincidencia de nombre) de
# lenguaje detectado -> carpetas de third-party relevantes. El repo de
# reglas deja claro que <carpeta> de third-party es un namespace
# independiente que NO siempre coincide con el nombre del lenguaje (p. ej.
# trailofbits/rs son reglas de Rust) -- por eso esta tabla se mantiene a
# mano en vez de intentar `carpeta == language`. Se excluyen a propósito
# los paquetes que no son de un lenguaje concreto (opengrep/generic,
# opengrep/problem-based-packs, trailofbits/generic, 0xdea/noisy): este
# análisis es por-fichero, y esos paquetes no están pensados para eso.
THIRD_PARTY_LANGUAGE_MAP: dict[str, list[tuple[str, str]]] = {
    "python": [("trailofbits", "python"), ("opengrep", "python")],
    "javascript": [("trailofbits", "javascript"), ("opengrep", "javascript")],
    "typescript": [("opengrep", "typescript")],
    "java": [("opengrep", "java"), ("trailofbits", "jvm")],
    "c": [("0xdea", "c")],
    "go": [("elttam", "go"), ("opengrep", "go"), ("trailofbits", "go")],
    "bash": [("opengrep", "bash")],
    "yaml": [("elttam", "yaml"), ("opengrep", "yaml"), ("trailofbits", "yaml")],
    "html": [("opengrep", "html")],
    "ruby": [("opengrep", "ruby"), ("trailofbits", "ruby")],
    "csharp": [("opengrep", "csharp")],
    "clojure": [("opengrep", "clojure")],
    "ocaml": [("opengrep", "ocaml")],
    "php": [("opengrep", "php")],
    "json": [("opengrep", "json")],
    "rust": [("trailofbits", "rs")],
    "swift": [("opengrep", "swift"), ("trailofbits", "swift")],
    "kotlin": [("opengrep", "kotlin")],
    "scala": [("opengrep", "scala")],
    "solidity": [("opengrep", "solidity")],
    "terraform": [("opengrep", "terraform"), ("trailofbits", "hcl")],
}


def _infer_threat_nature_from_semgrep(finding_extra: dict[str, Any], rule_id: str) -> ThreatNature:
    """Infiere la naturaleza de la amenaza a partir de la metadata de la regla Semgrep."""
    metadata = finding_extra.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    cat = str(metadata.get("category", "")).lower()
    nature = str(metadata.get("threat_nature", "")).lower()
    subcategory = str(metadata.get("subcategory", "")).lower()

    malicious_keywords = {
        "malware",
        "backdoor",
        "exfiltration",
        "obfuscation",
        "trojan",
        "c2",
        "persistence",
        "supply-chain-attack",
    }

    if nature in ("malicioso", "malicious"):
        return ThreatNature.MALICIOUS
    if nature in ("vulnerabilidad", "vulnerability"):
        return ThreatNature.VULNERABILITY

    rule_lower = rule_id.lower()
    # Coincidencia por palabra completa, no por substring: "c2" es lo
    # bastante corto para matchear por accidente dentro de un id/categoría
    # de regla que no tenga nada que ver (p. ej. algo con "c2c" o "src2").
    keyword_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(kw) for kw in malicious_keywords) + r")\b"
    )
    if (
        keyword_pattern.search(cat)
        or keyword_pattern.search(subcategory)
        or keyword_pattern.search(rule_lower)
    ):
        return ThreatNature.MALICIOUS

    return ThreatNature.VULNERABILITY


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

        # 3. Directorio local del proyecto. `_run_semgrep_on_file` espera
        # recibir una ruta "raíz de repo" y compone rules_dir/"rules"/
        # "semgrep"/... (la misma convención que el repo externo clonado en
        # el caso 4) -- devolver directamente `rules/semgrep` aquí duplicaba
        # el segmento (`rules/semgrep/rules/semgrep/custom/<lenguaje>`, que
        # nunca existe) y hacía que el checkout local siempre cayera al
        # fallback de escanear el directorio entero con todas las reglas de
        # terceros en vez de solo las del lenguaje del fichero. Verificado:
        # `Path("rules/semgrep")` existe pero
        # `Path("rules/semgrep") / "rules" / "semgrep" / "custom" / "python"`
        # no.
        local_rules_dir = Path("rules/semgrep")
        if local_rules_dir.exists() and any(local_rules_dir.iterdir()):
            return Path(".")

        # 4. Caché persistente en .watchgate/rules_cache/ -- ÚLTIMO RECURSO.
        # A partir de aquí se clona el repo de reglas directamente por su
        # cuenta, SIN pasar por la verificación de integridad por hash de
        # sync-rules.yml / reconcile-rules.yml (ver docs/integracion_repo_reglas.md).
        # En este propio repo nunca debería alcanzarse (el paso 3 siempre
        # encuentra rules/semgrep/ ya poblado y verificado) -- si se
        # alcanza, es una señal de que algo no está bien (checkout
        # incompleto, o un consumidor externo del paquete sin ese
        # checkout), así que se deja constancia explícita en el log.
        logger.warning(
            "rules/semgrep/ no está disponible localmente -- cayendo al fallback de "
            "clonar el repo de reglas directamente, SIN la verificación de integridad "
            "por hash de sync-rules.yml/reconcile-rules.yml (ver docs/integracion_repo_reglas.md)."
        )
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
        """Infiere el lenguaje del archivo para mapearlo contra las reglas Semgrep.

        Cubre los 17 lenguajes de rules/semgrep/custom/ más los que solo
        tienen reglas de terceros (kotlin, scala, solidity, terraform) --
        ver THIRD_PARTY_LANGUAGE_MAP.
        """
        basename = os.path.basename(file_path).lower()
        # Dockerfile no sigue convención de extensión: puede ser
        # literalmente "Dockerfile", "Dockerfile.prod", o "algo.dockerfile".
        if (
            basename == "dockerfile"
            or basename.startswith("dockerfile.")
            or basename.endswith(".dockerfile")
        ):
            return "dockerfile"

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
            ".cs": "csharp",
            ".clj": "clojure",
            ".cljs": "clojure",
            ".cljc": "clojure",
            ".ml": "ocaml",
            ".mli": "ocaml",
            ".php": "php",
            ".ps1": "powershell",
            ".psm1": "powershell",
            ".json": "json",
            ".rs": "rust",
            ".swift": "swift",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".scala": "scala",
            ".sol": "solidity",
            ".tf": "terraform",
            ".hcl": "terraform",
        }
        return language_map.get(extension)

    def _run_semgrep_on_file(
        self, temp_file_path: str, language: str, rules_dir: Path
    ) -> list[dict[str, Any]]:
        """Ejecuta Semgrep sobre un archivo temporal específico."""
        results: list[dict[str, Any]] = []

        # Buscar subdirectorio de reglas por lenguaje dentro del repo de reglas
        # Estrategia 1: rules/semgrep/custom/<language>
        # Estrategia 1b: rules/semgrep/custom/regex (patrones genéricos,
        #   siempre se aplican con independencia del lenguaje)
        # Estrategia 1c: rules/semgrep/third-party/<vendor>/<carpeta>
        #   relevantes para <language> (ver THIRD_PARTY_LANGUAGE_MAP)
        # Estrategia 2: rules/semgrep/watchgate.yml
        # Estrategia 3: raiz del directorio de reglas (si nada de lo
        #   anterior existe -- último recurso, escanea todo)
        config_paths: list[str] = []
        semgrep_root = rules_dir / "rules" / "semgrep"

        custom_lang_dir = semgrep_root / "custom" / language
        if custom_lang_dir.exists():
            config_paths.append(f"--config={custom_lang_dir}")

        if language != _ALWAYS_ON_CUSTOM_CATEGORY:
            custom_regex_dir = semgrep_root / "custom" / _ALWAYS_ON_CUSTOM_CATEGORY
            if custom_regex_dir.exists():
                config_paths.append(f"--config={custom_regex_dir}")

        for vendor, carpeta in THIRD_PARTY_LANGUAGE_MAP.get(language, []):
            third_party_dir = semgrep_root / "third-party" / vendor / carpeta
            if third_party_dir.exists():
                config_paths.append(f"--config={third_party_dir}")

        watchgate_yml = semgrep_root / "watchgate.yml"
        if watchgate_yml.exists():
            config_paths.append(f"--config={watchgate_yml}")

        if not config_paths:
            # Último recurso: si el árbol `rules/semgrep` existe pero ninguna
            # subcarpeta concreta aplicó (p. ej. un checkout a medio
            # sincronizar al que solo le falta `custom/regex`), acotar el
            # escaneo a ese árbol -- nunca a `rules_dir` a secas, que en el
            # caso 3 de `_get_rules_dir` es literalmente `Path(".")` (la
            # raíz del repo completo) y escanearía con Semgrep cualquier
            # YAML con forma de regla en todo el proyecto, no solo las
            # reglas de WatchGate.
            if semgrep_root.exists():
                config_paths.append(f"--config={semgrep_root}")
            elif rules_dir.exists():
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
                rule_id = finding.get("check_id", "semgrep-finding")
                threat_nature = _infer_threat_nature_from_semgrep(extra, rule_id)

                results.append(
                    {
                        "tool": "semgrep",
                        "rule_id": rule_id,
                        "message": extra.get("message", "Hallazgo estático detectado"),
                        "line": finding.get("start", {}).get("line", 1),
                        "risk_score": risk_score,
                        "threat_nature": threat_nature,
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
                    for f in findings:
                        f["file_path"] = file_change.path
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

        structured_findings = [
            Finding(
                file_path=f.get("file_path", "desconocido"),
                line=f.get("line"),
                rule_id=f.get("rule_id", "static-finding"),
                message=f.get("message", "Hallazgo estático"),
                severity="error" if f.get("risk_score", 0) >= 50 else "warning",
                threat_nature=f.get("threat_nature", ThreatNature.VULNERABILITY),
            )
            for f in all_findings
        ]

        dominant_threat = compute_dominant_threat_nature(structured_findings)

        return LayerResult(
            layer_name=self.name,
            risk_score=max_risk_score,
            justification=justification,
            findings=structured_findings,
            category=category,
            confidence=confidence,
            threat_nature=dominant_threat,
        )
