"""Generador de formato SARIF v2.1.0 para GitHub Code Scanning (spec CI/CD)."""

from __future__ import annotations

import json
from typing import Any

from watchgate.core.models import AggregatedResult


def normalize_sarif_path(file_path: str) -> str:
    """Normaliza la ruta de un archivo para SARIF 2.1.0 (Rule 3).

    Garantiza que la ruta sea relativa al repositorio, sin prefijos absolutos
    ni secuencias de navegación `../`.
    """
    clean_path = file_path.replace("\\", "/")
    # Eliminar prefijo de esquema o raíz si lo hay
    if ":" in clean_path and not clean_path.startswith("http"):
        # Tipo C:/path o file:///path
        clean_path = clean_path.split(":", 1)[-1]

    parts = [p for p in clean_path.split("/") if p and p != "." and p != ".."]
    result = "/".join(parts)
    return result or "repository"


def _severity_to_level(severity: str) -> str:
    sev = severity.lower()
    if sev == "error":
        return "error"
    if sev in ("warning", "warn"):
        return "warning"
    return "note"


def render_sarif(aggregated: AggregatedResult) -> str:
    """Convierte un `AggregatedResult` en un documento JSON SARIF v2.1.0 válido."""
    rules_dict: dict[str, dict[str, Any]] = {}
    results_list: list[dict[str, Any]] = []

    for layer_name, layer_res in aggregated.layer_results.items():
        if layer_res.skipped:
            continue

        # Convertir findings estructurados si existen
        if layer_res.findings:
            for finding in layer_res.findings:
                rule_id = f"watchgate-{layer_name}-{finding.rule_id}"
                threat_nat_val = finding.threat_nature.value
                tags = ["malware"] if threat_nat_val == "malicioso" else ["vulnerability"]
                if rule_id not in rules_dict:
                    rules_dict[rule_id] = {
                        "id": rule_id,
                        "name": finding.rule_id,
                        "shortDescription": {
                            "text": f"WatchGate [{layer_name}]: {finding.rule_id}"
                        },
                        "fullDescription": {"text": finding.message},
                        "defaultConfiguration": {
                            "level": _severity_to_level(finding.severity)
                        },
                        "properties": {"tags": tags},
                    }

                clean_file = normalize_sarif_path(finding.file_path)
                region: dict[str, Any] = {}
                if finding.line is not None and finding.line > 0:
                    region["startLine"] = finding.line
                    if finding.end_line is not None and finding.end_line >= finding.line:
                        region["endLine"] = finding.end_line
                else:
                    # Fallback Rule 4: sin línea específica
                    region["startLine"] = 1

                results_list.append(
                    {
                        "ruleId": rule_id,
                        "level": _severity_to_level(finding.severity),
                        "message": {"text": finding.message},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": clean_file,
                                        "uriBaseId": "%SRCROOT%",
                                    },
                                    "region": region,
                                }
                            }
                        ],
                        "properties": {"threatNature": threat_nat_val},
                    }
                )
        else:
            # Fallback para capas sin findings estructurados (ej. Semántica o Reputación con riesgo)
            if layer_res.risk_score >= 40:
                rule_id = f"watchgate-{layer_name}-risk"
                if rule_id not in rules_dict:
                    rules_dict[rule_id] = {
                        "id": rule_id,
                        "name": f"{layer_name}_risk",
                        "shortDescription": {"text": f"Riesgo elevado en capa {layer_name}"},
                        "fullDescription": {"text": layer_res.justification},
                        "defaultConfiguration": {
                            "level": "error" if layer_res.risk_score >= 70 else "warning"
                        },
                    }

                results_list.append(
                    {
                        "ruleId": rule_id,
                        "level": "error" if layer_res.risk_score >= 70 else "warning",
                        "message": {"text": layer_res.justification},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": "repository",
                                        "uriBaseId": "%SRCROOT%",
                                    },
                                    "region": {"startLine": 1},
                                }
                            }
                        ],
                    }
                )

    sarif_doc: dict[str, Any] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "WatchGate",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/pabloayllong/watch_gate",
                        "rules": list(rules_dict.values()),
                    }
                },
                "results": results_list,
            }
        ],
    }

    return json.dumps(sarif_doc, indent=2, ensure_ascii=False)
