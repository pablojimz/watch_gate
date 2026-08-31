#!/usr/bin/env bash
# Fragmento benigno de ejemplo: un script de build normal.
set -euo pipefail

echo "Instalando dependencias..."
npm ci

echo "Compilando..."
npm run build

echo "Listo."
