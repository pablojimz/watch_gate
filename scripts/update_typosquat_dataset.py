#!/usr/bin/env python3
"""Script para descargar y actualizar las listas de referencia de typosquatting.

Soporta actualización automática desde fuentes públicas oficiales para:
- PyPI (Top 2.000 paquetes vía hugovk/top-pypi-packages)
- crates.io (Top 500 crates por descargas)
- npm (Top paquetes populares)
- AUR (Paquetes populares y base-devel)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

DATASET_DIR = Path(__file__).resolve().parent.parent / "datasets" / "typosquat_reference"
USER_AGENT = "WatchGate-DatasetUpdater/1.0 (https://github.com/watchgate)"


def _read_existing(filepath: Path) -> set[str]:
    if not filepath.exists():
        return set()
    return {
        line.strip()
        for line in filepath.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def _write_sorted(filepath: Path, packages: set[str]) -> int:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    sorted_pkgs = sorted(packages, key=lambda s: s.lower())
    filepath.write_text("\n".join(sorted_pkgs) + "\n", encoding="utf-8")
    return len(sorted_pkgs)


def update_pypi() -> int:
    print("-> Actualizando dataset de PyPI...")
    target_file = DATASET_DIR / "pypi.txt"
    packages = _read_existing(target_file)
    url = "https://raw.githubusercontent.com/hugovk/top-pypi-packages/main/top-pypi-packages-30-days.json"
    try:
        resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        fetched = [row["project"] for row in data.get("rows", [])[:2000]]
        packages.update(fetched)
        print(f"   Descargados {len(fetched)} paquetes de PyPI.")
    except Exception as exc:
        print(f"   [AVISO] No se pudo obtener la lista remota de PyPI: {exc!r}")

    total = _write_sorted(target_file, packages)
    print(f"   [OK] pypi.txt contiene {total} paquetes.")
    return total


def update_crates() -> int:
    print("-> Actualizando dataset de crates.io (Rust)...")
    target_file = DATASET_DIR / "crates.txt"
    packages = _read_existing(target_file)
    fetched_count = 0
    for page in range(1, 6):
        url = f"https://crates.io/api/v1/crates?page={page}&per_page=100&sort=downloads"
        try:
            resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            crates = [c["id"] for c in data.get("crates", [])]
            packages.update(crates)
            fetched_count += len(crates)
        except Exception as exc:
            print(f"   [AVISO] Error al obtener página {page} de crates.io: {exc!r}")
            break

    print(f"   Descargados {fetched_count} crates.")
    total = _write_sorted(target_file, packages)
    print(f"   [OK] crates.txt contiene {total} paquetes.")
    return total


def update_npm() -> int:
    print("-> Actualizando dataset de npm (Node.js)...")
    target_file = DATASET_DIR / "npm.txt"
    packages = _read_existing(target_file)
    # Lista de paquetes populares esenciales de npm
    popular_npm = [
        "express",
        "lodash",
        "react",
        "react-dom",
        "vue",
        "next",
        "nuxt",
        "axios",
        "typescript",
        "chalk",
        "commander",
        "commander",
        "fs-extra",
        "glob",
        "minimatch",
        "mkdirp",
        "semver",
        "uuid",
        "yargs",
        "bluebird",
        "body-parser",
        "cookie-parser",
        "cors",
        "dotenv",
        "helmet",
        "jsonwebtoken",
        "mongoose",
        "morgan",
        "multer",
        "pg",
        "mysql2",
        "redis",
        "socket.io",
        "ws",
        "webpack",
        "eslint",
        "prettier",
        "jest",
        "mocha",
        "chai",
        "sinon",
        "rxjs",
        "vite",
        "rollup",
        "esbuild",
        "parcel",
        "nodemon",
        "rimraf",
        "concurrently",
        "inquirer",
        "ora",
        "nanoid",
        "superagent",
        "got",
        "node-fetch",
        "cheerio",
        "puppeteer",
        "playwright",
        "aws-sdk",
        "stripe",
        "prisma",
        "typeorm",
        "knex",
        "sequelize",
        "ioredis",
        "nodemailer",
        "handlebars",
        "ejs",
        "chokidar",
        "execa",
        "shelljs",
        "simple-git",
        "husky",
        "lint-staged",
        "tslib",
        "core-js",
        "moment",
        "date-fns",
        "dayjs",
        "ramda",
        "underscore",
        "styled-components",
        "framer-motion",
        "recharts",
        "d3",
        "chart.js",
        "three",
        "bootstrap",
        "tailwindcss",
        "aiogram",
    ]
    packages.update(popular_npm)
    total = _write_sorted(target_file, packages)
    print(f"   [OK] npm.txt contiene {total} paquetes.")
    return total


def update_aur() -> int:
    print("-> Actualizando dataset de AUR / Arch Linux...")
    target_file = DATASET_DIR / "aur.txt"
    packages = _read_existing(target_file)
    popular_aur = [
        "base-devel",
        "git",
        "python",
        "curl",
        "wget",
        "gcc",
        "make",
        "cmake",
        "ninja",
        "pkg-config",
        "glibc",
        "openssl",
        "systemd",
        "bash",
        "zsh",
        "vim",
        "neovim",
        "htop",
        "tmux",
        "docker",
        "containerd",
        "yay",
        "paru",
        "pacman",
        "archlinux-keyring",
        "linux",
        "linux-lts",
        "linux-headers",
        "sudo",
        "shadow",
        "util-linux",
        "coreutils",
        "findutils",
        "grep",
        "gawk",
        "sed",
        "tar",
        "gzip",
        "bzip2",
        "xz",
        "zstd",
        "unzip",
        "7zip",
        "rsync",
        "net-tools",
        "iproute2",
        "iputils",
        "wireguard-tools",
        "openvpn",
        "openssh",
        "gnupg",
        "ca-certificates",
        "nss",
        "pam",
        "dbus",
        "polkit",
        "xorg-server",
        "wayland",
        "mesa",
        "vulkan-icd-loader",
        "nvidia-utils",
        "intel-media-driver",
        "lib32-glibc",
        "lib32-gcc-libs",
        "alsa-utils",
        "pulseaudio",
        "pipewire",
        "pipewire-pulse",
        "wireplumber",
        "fontconfig",
        "freetype2",
        "ttf-dejavu",
        "noto-fonts",
        "gtk3",
        "gtk4",
        "qt5-base",
        "qt6-base",
        "electron",
        "chromium",
        "firefox",
        "discord",
        "spotify",
        "telegram-desktop",
        "visual-studio-code-bin",
        "sublime-text",
        "slack-desktop",
        "steam",
        "lutris",
        "wine",
        "wine-staging",
    ]
    packages.update(popular_aur)
    total = _write_sorted(target_file, packages)
    print(f"   [OK] aur.txt contiene {total} paquetes.")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Actualiza datasets de typosquatting.")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Descarga las listas remotas de PyPI y crates.io",
    )
    args = parser.parse_args()

    if args.fetch:
        print("Obteniendo listas remotas actualizadas...")
        update_pypi()
        update_crates()

    update_npm()
    update_aur()

    print("\nDatasets de typosquatting listos en:", DATASET_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
