# Manual de Desarrollo y Guía del Entorno para WatchGate

**Guía del Desarrollador y Mantenimiento**
**Ubicación**: `docs/manual_desarrollo.md`
**Fecha**: Agosto 2026

---

## 1. Requisitos del Sistema y Entorno de Desarrollo

Para colaborar en el desarrollo de WatchGate se requieren las siguientes herramientas:

* **Python**: versión `>= 3.11` (recomendado Python 3.11 o 3.12).
* **Gestor de Paquetes**: `poetry` (para gestión determinista de dependencias con `poetry.lock`).
* **Control de Versiones**: `git` y **`git-lfs`** (necesario para el almacenamiento de reglas de seguridad Semgrep/YARA).

---

## 2. Instalación y Configuración del Proyecto

```bash
# 1. Clonar el repositorio
git clone https://github.com/pablojimz/watch_gate.git
cd watch_gate

# 2. Inicializar Git LFS para descargar archivos grandes de reglas
git lfs install
git lfs pull

# 3. Crear el entorno virtual e instalar dependencias con Poetry
poetry install
```

---

## 3. Comandos de Calidad y Suite de Pruebas

WatchGate mantiene una política de cero advertencias y cero errores de tipado estricto:

```bash
# Ejecutar linteado de código (Ruff)
poetry run ruff check .

# Formateo automático de código
poetry run ruff format .

# Verificación de tipos estáticos (Mypy --strict)
poetry run ruff check . && poetry run mypy watchgate

# Ejecutar la suite de pruebas unitarias
poetry run pytest -q
```

---

## 4. Configuración Importante: Exclusión de Windows Defender

### ⚠️ Riesgo Operativo en Máquinas de Desarrollo Windows
El repositorio de WatchGate incluye reglas YARA reales para detección de malware/webshells (`rules/yara/`) y un conjunto de *fixtures* de aceptación con muestras reales vetadas de paquetes maliciosos (`tests/cases/`). 

En entornos de desarrollo sobre **Windows**, la protección en tiempo real de **Windows Defender** puede detectar falsamente estos archivos inofensivos de prueba y ponerlos en **cuarentena**, provocando que `git status` detecte archivos eliminados accidentalmente.

### 🛡️ Solución: Configurar Exclusión de Carpeta en Windows Defender

Abre una consola de **PowerShell como Administrador** en Windows y ejecuta los siguientes comandos ajustando la ruta a tu carpeta del proyecto:

```powershell
# Añadir la carpeta del proyecto a las exclusiones de Windows Defender
Add-MpPreference -ExclusionPath "C:\Ruta\A\Tu\Proyecto\watch_gate"

# Añadir específicamente la carpeta de cachés de reglas y fixtures
Add-MpPreference -ExclusionPath "C:\Ruta\A\Tu\Proyecto\watch_gate\.watchgate"
Add-MpPreference -ExclusionPath "C:\Ruta\A\Tu\Proyecto\watch_gate\tests\cases"
```

O desde la interfaz gráfica de Windows:
1. Ve a **Inicio -> Configuración -> Configuración de Windows / Seguridad de Windows**.
2. Selecciona **Protección contra virus y amenazas -> Configuración de protección contra virus y amenazas -> Administrar la configuración**.
3. En **Exclusiones**, selecciona **Agregar o quitar exclusiones**.
4. Selecciona **Agregar una exclusión -> Carpeta** y elige la carpeta raíz del repositorio `watch_gate`.
