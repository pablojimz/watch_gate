# Manual de Integración del Servidor MCP de WatchGate

**Model Context Protocol (MCP) Server**
**Ubicación**: `docs/manual_mcp.md`
**Fecha**: Agosto 2026

---

## 1. Introducción y Arquitectura

WatchGate incluye un **Servidor MCP Nativo** en modo `stdio` (`watchgate/mcp/`) que expone herramientas de análisis de riesgo de código en tiempo real para Agentes de IA e IDEs de desarrollo como **OpenCode**, **Cursor**, **VS Code** y **Claude Desktop**.

El servidor implementa el estándar **Model Context Protocol (MCP) v1.0** mediante mensajes JSON-RPC 2.0 sobre `sys.stdin`/`sys.stdout` (manteniendo `sys.stderr` exclusivamente para diagnóstico y logs de depuración).

```
+-------------------------------------------------------------------------------+
|                           AGENTE / IDE (Cliente MCP)                          |
|                  (OpenCode, Cursor, VS Code, Claude Desktop)                  |
+--------------------------------------+----------------------------------------+
                                       |
                           Mensajes JSON-RPC (stdio)
                                       |
                                       v
+-------------------------------------------------------------------------------+
|                       watchgate mcp serve --transport stdio                   |
|                        Servidor MCP Nativo (watchgate/mcp/)                   |
+-------------------------------------------------------------------------------+
|  Herramientas Expuestas:                                                      |
|   1. watchgate_analyze_diff  -> Análisis completo multi-capa                  |
|   2. watchgate_precheck      -> Evaluación determinista rápida (<100ms)       |
|   3. watchgate_explain_risk  -> Desglose explicativo de hallazgos             |
|   4. watchgate_verify_fix    -> Verificación comparativa de parches           |
|   5. watchgate_query_threat_kb -> Búsqueda vectorial en corpus RAG            |
+-------------------------------------------------------------------------------+
```

---

## 2. Herramientas MCP Disponibles

### 1. `watchgate_analyze_diff`
Realiza un análisis completo de riesgo sobre un parche unificado o diff de Git.
* **Parámetros**:
  * `diff_text` (*string*, opcional): Texto del parche unificado.
  * `base` (*string*, default `"main"`): Commit o rama base.
  * `head` (*string*, default `"HEAD"`): Commit o rama head.
  * `repo_path` (*string*, default `"."`): Ruta al repositorio Git local.
  * `metadata` (*object*, opcional): Metadatos adicionales (`pr_id`, `repo`, etc.).
* **Retorno**: JSON con `analysis` (`AggregatedResult`) y `guidance` (`AgentGuidance`).

### 2. `watchgate_precheck`
Evaluación determinista ultrarrápida (<100ms) ejecutando únicamente las capas estática, dependencias y reputación. Cero consumo de tokens LLM.
* **Parámetros**:
  * `diff_text` (*string*, requerido): Texto del parche unificado.
  * `repo_path` (*string*, default `"."`): Ruta al repositorio local.
* **Retorno**: Resultado determinista rápido con respuesta para iteraciones en caliente durante edición de código.

### 3. `watchgate_explain_risk`
Genera un desglose detallado en prosa técnica estructurada para que el agente entienda las razones del semáforo asignado.
* **Parámetros**:
  * `diff_text` (*string*, opcional): Texto del diff a explicar.
  * `analysis_json` (*string*, opcional): JSON de un `AggregatedResult` previo.
* **Retorno**: Texto explicativo detallado con hallazgos, desgloses y pasos concretos de remediación.

### 4. `watchgate_verify_fix`
Compara un diff original (con alertas) contra un nuevo diff candidato corregido por el agente. Compara firmas sintácticas de hallazgos (`compute_finding_signature`) para validar la corrección efectuada.
* **Parámetros**:
  * `original_diff` (*string*, requerido): Diff original con alertas.
  * `candidate_diff` (*string*, requerido): Nuevo diff candidato.
  * `repo_path` (*string*, default `"."`): Ruta al repositorio.
* **Retorno**: Estado de reducción de riesgo (`risk_reduced`), puntuación previa vs. nueva, lista de hallazgos resueltos y hallazgos remanentes.

### 5. `watchgate_query_threat_kb`
Consulta la base de conocimientos vectorial RAG de WatchGate sobre patrones de ataque conocidos, vulnerabilidades históricas y técnicas de MITRE ATT&CK.
* **Parámetros**:
  * `query` (*string*, requerido): Concepto de seguridad a buscar.
  * `k` (*integer*, default `3`): Número máximo de fragmentos.
* **Retorno**: Lista JSON con fragmentos relevantes (`case_name`, `origin`, `text`).

---

## 3. Configuración en Clientes e IDEs

### 3.1 OpenCode

Añade en el archivo de configuración `opencode.json` o `.opencode/mcp.json`:

```json
{
  "mcpServers": {
    "watchgate": {
      "command": "watchgate",
      "args": ["mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

O si utilizas el entorno virtual directo de Python:

```json
{
  "mcpServers": {
    "watchgate": {
      "command": "/ruta/a/watch_gate/.env/bin/python",
      "args": ["-m", "watchgate.cli", "mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

### 3.2 Claude Desktop

Edita el archivo de configuración de Claude Desktop:
* **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
* **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
* **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "watchgate-security": {
      "command": "watchgate",
      "args": ["mcp", "serve", "--transport", "stdio"],
      "env": {
        "WATCHGATE_LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### 3.3 Cursor

En Cursor IDE:
1. Abre **Settings** -> **Features** -> **MCP**.
2. Haz clic en **+ Add New MCP Server**.
3. Rellena los datos:
   * **Name**: `WatchGate`
   * **Type**: `command`
   * **Command**: `watchgate mcp serve --transport stdio`

### 3.4 VS Code (Extensión Cline / Roo Code / MCP Client)

En la configuración de la extensión MCP en VS Code:

```json
{
  "mcpServers": {
    "watchgate": {
      "command": "watchgate",
      "args": ["mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

---

## 4. Verificación de Funcionamiento Manual

Puedes probar interactivamente el servidor MCP ejecutando el comando y enviando un mensaje `initialize` por terminal:

```bash
watchgate mcp serve --transport stdio
```

Escribe en terminal (en una sola línea):

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}
```

La respuesta en `stdout` confirmará el servidor activo:

```json
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "watchgate-mcp", "version": "0.1.0"}}}
```

---

## 5. Bucle de Autocorrección para Agentes (Self-Correction Loop)

Flujo de trabajo recomendado para agentes de IA que utilicen WatchGate vía MCP:

```
 1. Agente escribe o modifica código.
 2. Agente llama a `watchgate_precheck` (0.05s).
 3. Si `watchgate_precheck` da AMARILLO/ROJO:
    a. Agente llama a `watchgate_explain_risk`.
    b. Agente aplica las correcciones sugeridas en `actionable_steps`.
    c. Agente llama a `watchgate_verify_fix` pasando `original_diff` y `candidate_diff`.
 4. Si el semáforo es VERDE:
    a. Agente aprueba el cambio y solicita el merge.
```
