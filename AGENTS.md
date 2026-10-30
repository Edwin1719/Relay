# AGENTS.md — Relay

> Instrucciones para agentes de IA que trabajen en este proyecto.
> Leer antes de hacer cualquier cambio.

## ¿Qué es Relay?

Entorno de desarrollo aumentado con IA (FastAPI + React). Un agente de código con
chat, explorador de archivos, syntax highlighting, MCP, skills y sesiones.
El motor del agente está **vendorizado** en `backend/agent_core.py` — no depende
de paquetes externos.

**Stack:** Python 3.10+ (FastAPI), Node.js 18+ (React + Vite + Tailwind), SQLite.

> **Identificadores históricos:** el proyecto se llamaba Kodama. La marca visible
> es Relay, pero se conservan por compatibilidad `KODAMA_*` (variables de
> entorno), `backend/.kodama/`, `KODAMA_MEMORY.md` y la clase `KodamaAgent`.

---

## Cómo ejecutar

```bash
cd <carpeta-del-proyecto>
pip install -r backend/requirements.txt
npm install --prefix frontend
python run.py           # desarrollo (backend :8000 + frontend :5173)
python run.py --build   # producción (todo en :8000)
```

O doble clic en `run.bat` (Windows).

---

## Estructura clave

```
Relay/
├── README.md                   # Documentación completa para humanos
├── AGENTS.md                   # Este archivo — instrucciones para agentes
├── run.py / run.bat            # Lanzadores
├── backend/
│   ├── main.py                 # FastAPI — todos los endpoints REST + SSE
│   ├── agent_core.py           # Motor vendorizado (KodamaAgent, WorkspaceContext, SessionStore)
│   ├── agent_stream.py         # Streaming SSE, planificación, smart retries
│   ├── prompt_builder.py       # build_system_prompt(), truncado de contexto, traducción de errores
│   ├── providers.py            # Catálogo de proveedores y modelos (tiers)
│   ├── model_clients.py        # OpenAICompatibleClient (REST + SSE, retry 429)
│   ├── mcp_manager.py          # Gestión de servidores MCP (stdio + asyncio)
│   ├── integrations_manager.py # Marketplace de 10 integraciones MCP
│   ├── skills_manager.py       # 8 skills (debug, tdd, security, review, batch, scheduled_automation, rtk, programming)
│   ├── session_db.py           # SQLite: sesiones, integraciones, skills
│   ├── workspace_manager.py    # Persistencia del directorio de trabajo
│   ├── skills/                 # Archivos .md con prompts de skills
│   ├── mcp_scripts/            # Servidores MCP locales (gmail, whatsapp)
│   ├── .env                    # API keys (NO versionado)
│   └── tests/                  # Tests con pytest
├── frontend/
│   └── src/
│       ├── App.tsx             # Layout 3 columnas + tabs
│       ├── hooks/useChat.ts    # SSE streaming + estado
│       ├── api/client.ts       # Cliente HTTP tipado
│       └── components/         # ChatPanel, FileExplorer, FilePreview, SessionList,
│                               # SkillsPanel, IntegrationsPanel, SettingsPanel,
│                               # MessageBubble, ToolCallCard
```

---

## Arquitectura — flujo de datos

```
Frontend (React :5173)
    ↕ HTTP REST + SSE
FastAPI (main.py :8000)
    ├── resolve_client() → ChatModelClient (Ollama) | OpenAICompatibleClient (cloud)
    ├── create_agent()   → KodamaAgent + build_system_prompt() + skills + MCP tools
    └── ask_stream()     → planificación → ejecución → streaming SSE
            ↕
KodamaAgent (agent_core.py)
    ├── build_prefix()  → system prompt base con tools nativas
    ├── parse()         → JSON <tool> / XML <tool> / <final>
    └── herramientas: list_files, read_file, search, write_file,
                      patch_file, run_shell, delegate
            ↕
MCP Servers externos (wigolo, Context7, playwright, puppeteer, github,
                      google-maps, filesystem, gmail, whatsapp, codebase-memory-mcp)
```

---

## Proveedores de modelos

El catálogo vive en `backend/providers.py`. **Nada infiere el proveedor a partir
del nombre del modelo**: `get_model_spec()` es la única fuente de verdad.

| Proveedor | Backend | Tier | Modelos |
|-----------|---------|------|---------|
| **Ollama Cloud** | `/api/chat` NDJSON | `fast` | solo `*-cloud` (los locales están excluidos) |
| **DeepSeek** | `/v1/chat/completions` SSE | `deep` | `deepseek-v4-pro`, `deepseek-v4-flash` |
| **APInex** | `/v1/chat/completions` SSE | `deep` | `free/*` (lista en `KODAMA_APINEX_MODELS`) |

API keys en `backend/.env`: `DEEPSEEK_API_KEY=sk-...`, `APINEX_API_KEY=...`
(también editables desde **Config → Proveedores**, que escribe en ese mismo archivo).

La lista de APInex se revalida al arrancar contra `apinex.bond/api/public/models`
(solo `allowFree` + `supportsTools` + `$0`); `KODAMA_APINEX_MODELS` la sobrescribe.
Si la red falla se conserva la última lista conocida.

**Política:** los modelos locales de Ollama no se exponen. Su ventana por
defecto (4K) queda mayormente consumida por el system prompt, lo que hace
inestable el uso de herramientas en varios pasos. `fast` = tareas cortas o de
complejidad media; `deep` = trabajo agentico de varios pasos.

---

## Endpoints principales

| Método | Ruta | Qué hace |
|--------|------|----------|
| GET | `/api/status` | Estado del agente + MCP |
| POST | `/api/chat` | Chat con streaming SSE |
| GET | `/api/models` | Modelos disponibles |
| POST | `/api/models/select` | Cambiar modelo en caliente |
| GET/POST | `/api/workspace/*` | Gestión de workspace |
| GET/POST | `/api/sessions/*` | CRUD de sesiones (SQLite) |
| GET/POST | `/api/skills*` | Skills on/off |
| GET/POST | `/api/integrations/*` | Marketplace MCP |
| GET/POST | `/api/mcp/*` | Estado MCP |

---

## Sistemas clave

### Sistema de prompt (`prompt_builder.py`)
`build_system_prompt()` construye el prompt en este orden:
1. Skills activas (máxima prioridad)
2. Reglas críticas (answer from knowledge, file access, email, web search)
3. Formato profesional (Markdown, tablas, emojis)
4. Guía MCP (patrón de nombres, selección por tarea)
5. Contexto del workspace (git, archivos)

### Planificación (`agent_stream.py`)
- `detect_model_tier()` lee el tier declarado en el catálogo (`fast` / `deep`)
- Todos los modelos usan el prompt completo; no hay prompt ligero
- Preguntas simples → `<final>` directo, sin herramientas
- El planificador no puede responder de memoria sobre archivos: si la petición
  menciona un archivo, ruta o acción del proyecto, debe emitir `<plan>`
- Si el bucle agota pasos sin respuesta final, se emite un mensaje explicativo
  en lugar de una burbuja vacía

### Gestión de contexto (`prompt_builder.py`)
- `estimate_prompt_tokens()` — ~4 chars/token
- `truncate_conversation_history()` — presupuesto = mitad de `context_limit`
  del modelo, con tope en `MAX_HISTORY_TOKENS` (64K)
- Smart retries: máx 3 fallos consecutivos por tool → cambiar estrategia
- Una denegación de aprobación no cuenta como fallo reintentable: el modelo
  recibe "no reintentes" y debe proponer una alternativa o preguntar
- Los errores 429/5xx se reintentan en el cliente con backoff exponencial,
  respetando `Retry-After` (máx 30s)

### MCP (`mcp_manager.py` + `integrations_manager.py`)
- 10 integraciones en el marketplace
- Tools namespaced: `mcp_<server>_<tool>`
- Config sensible → `.env`, no sensible → SQLite
- Conexión vía stdio con ClientSession del SDK MCP
- Coste medido: 41 herramientas MCP = 8.980 caracteres (~2.245 tokens),
  27,7% de un prompt de ~8.100; Playwright sola 4.336. La palanca recomendada
  es **desactivar integraciones**, no filtrar herramientas por tarea
  (evaluado: ahorro modesto frente al riesgo de ocultar una tool necesaria).

### Skills (`skills_manager.py`)
- 8 skills cargadas desde `backend/skills/*.md`
- Estado persistido en SQLite
- Inyectadas al inicio del system prompt

### Sesiones (`session_db.py`)
- Persistencia dual: SQLite (metadatos UI) + JSON en `<workspace>/.mini-coding-agent/sessions`
- Reanudación: restaura historial completo al cambiar de sesión

### Concurrencia (`main.py`)
- Un solo chat a la vez: `_chat_lock` serializa `/api/chat`; el segundo
  request recibe 409 con un mensaje en español.
- El candado lo libera el hilo trabajador, no el generador: si el cliente se
  desconecta, el agente puede seguir mutando su historial.
- `_ensure_chat_idle()` devuelve 409 en `reset`, `workspace/set`,
  `models/select` y `sessions/switch` mientras hay un stream.

### Aprobación de herramientas (`main.py` + `agent_core.py`)
- Con **Modo Programación** activo, `create_agent(approval="ask")`: las
  herramientas con `risky=True` (`write_file`, `patch_file`, `run_shell`,
  `edit_file`) piden permiso antes de ejecutarse.
- El gate ya existe en el motor (`run_tool` → `approve()`); lo que se sustituye
  es `input()` por el canal SSE: evento `approval_required` + `POST /api/approve`.
- Timeout de 60 s y desconexión del cliente rechazan la acción; el modelo recibe
  `error: approval denied` y puede proponer otra cosa.
- Sin el perfil activo, `approval="auto"`: nada cambia.
- La tarjeta muestra la vista previa antes de decidir: diff unificado para
  `write_file`/`patch_file`/`edit_file` y `$ comando` para `run_shell`.
  `_approval_diff()` resuelve la ruta con `agent.path()` (que ya valida el
  sandbox), lee el archivo actual, calcula con `difflib` y trunca con `clip()`.

---

## Tests

```bash
cd backend
python -m pytest tests/ -v
```

Tests para: agent_stream, edit_file, integrations_manager, main, mcp_manager,
model_clients, prompt_tools, session_db, skills_manager, workspace_boundary,
workspace_root, http_client.
La suite debe pasar en verde; un fallo o un error de colección no se deja pasar.

---

## Reglas para trabajar en este proyecto

1. **No reinstalar dependencias externas del agente.** El motor ya está vendorizado
   en `agent_core.py`. No agregar `mini-coding-agent` como dependencia.
2. **El .env NUNCA se versiona.** Las API keys van en `backend/.env` (gitignored).
3. **Las integraciones MCP se agregan en `integrations_manager.py` → `CATALOG`.**
   Solo necesita entrada en la lista; el ciclo de vida es automático.
4. **Las skills se agregan como `.md` en `backend/skills/` y entrada en
   `skills_manager.py` → `SKILLS_CATALOG`.**
5. **Backend y frontend se comunican vía REST + SSE.** No hay WebSockets.
6. **El streaming usa `complete_stream()` cuando está disponible** en el cliente
   (OpenAICompatibleClient y ChatModelClient lo tienen). Fallback a `complete()`.
7. **Los cambios en el agente (tools, prompt, parseo) van en `agent_core.py`.**
   La capa de integración (streaming, planificación) va en `agent_stream.py`;
   los servidores MCP se gestionan en `mcp_manager.py`.
8. **No uses `npm run build` manualmente.** Usa `python run.py --build`.
9. **Politica de manejo de errores:**
   - Funciones de **consulta** (listar, leer, status): retornan `[]`, `None` o `False`
     en caso de fallo **y loguean `logger.warning()`** con el error. Nunca `pass` silencioso.
   - Funciones de **mutacion** (escribir, crear, eliminar, iniciar): **propagan la excepcion**
     hacia arriba para que el llamador decida. El mensaje de error debe ser descriptivo.
   - Las excepciones esperadas (ej. columna ya existe en SQLite, archivo no encontrado
     en cleanup) se capturan con el tipo mas especifico posible, no `except Exception`.

## KODAMA_MEMORY.md

Convención de memoria persistente entre sesiones (similar a CLAUDE.md):
- Archivo `KODAMA_MEMORY.md` en la raíz del workspace
- Se inyecta en el system prompt al iniciar el agente (`agent_factory.py`), desde la raíz del workspace
- El agente lo actualiza via `write_file` cuando el usuario dice "recuerda esto"
- Contiene preferencias, convenciones y decisiones del proyecto

---

## Limitaciones conocidas (2026-10-29)

Estado verificado ejecutando el código, no leyendo la documentación. Si algo de
esta lista se arregla, actualizar esta sección.

- **`rtk` requiere `KODAMA_RTK_FILTER`** apuntando a `rtk_filter.py`; si la
  variable no está definida, la skill no se aplica.
- **`codebase-memory-mcp` requiere el binario en `PATH`** o `CODEBASE_MEMORY_BIN`
  apuntando a él.
- **Cada proyecto abierto crea `<proyecto>/.mini-coding-agent/`** con las
  sesiones. Añadirlo al `.gitignore` del proyecto si usa git.

### Resuelto (2026-10-29)

- `edit_file` registrada correctamente: `agent_factory.py` asigna la herramienta
  bajo su nombre en lugar de descomponerla. Desaparecen las cuatro entradas
  falsas (`schema`, `description`, `risky`, `run`) y el `KeyError` que abortaba
  el turno.
- El prompt ya no nombra `mcp_tavily-mcp_tavily-search` ni `mcp_fetch_fetch`;
  solo referencia herramientas del catálogo. La descripción de `web_search`
  tampoco menciona Tavily.
- `tests/test_edit_file.py` importa `build_edit_file_tool` desde
  `prompt_builder` (antes lo hacía desde `agent_stream`, donde ya no vive).
  El módulo vuelve a recolectar: 9 tests en verde y 242 en total.
- **Frontera del workspace unificada** en `agent_core.is_within_root()` y
  aplicada en `/api/workspace/read`, `/api/workspace/files` y `read_files`.
  La comparación por prefijo de texto (que aceptaba `proyecto-evil`) se
  sustituyó por ruta resuelta + separador. 10 tests nuevos.
- **Suite de backend en verde:** 266 tests, sin fallos ni errores de colección.
  Los tests de integraciones usan `playwright` (sin claves) y `github` (con
  API key) en lugar de las integraciones `fetch` y `tavily-mcp` eliminadas.
- **Raíz del workspace = carpeta seleccionada.** `WorkspaceContext.build()` ya
  no deriva la raíz de `git rev-parse`: un `.git` en un ancestro (el home) ya no
  amplía el sandbox. Las sesiones y `KODAMA_MEMORY.md` se escriben dentro del
  proyecto y se eliminó el parche de `main.py` que corregía la raíz después de
  crear el agente. 3 tests nuevos (suite: 269).
- **El token de auth ya no se escribe en el log**; solo se registra la ruta del
  archivo `.kodama_token`.
- **Rutas portables:** `filesystem` usa `Path.home()`, `codebase-memory-mcp`
  resuelve el binario por `PATH`/`CODEBASE_MEMORY_BIN` y `rtk.md` usa
  `%KODAMA_RTK_FILTER%` (cmd.exe, el shell de `run_shell`). No queda ninguna
  ruta con nombre de usuario.
- **C3-mínimo:** la guía MCP del prompt ya no cita nombres exactos de
  herramientas; solo familias y la regla de que la lista de herramientas del
  contexto es la fuente de verdad. 441 caracteres menos.
- **Cerrojo de chat:** un turno a la vez. El segundo request concurrente
  recibe 409; el candado lo libera el worker para cubrir desconexiones.
  Guard en `reset`, `workspace/set`, `models/select` y `sessions/switch`.
  3 tests nuevos (suite: 272).
- **Modo Programación como skill:** `backend/skills/programming.md` +
  entrada en `SKILLS_CATALOG`. No hay campo `mode` ni endpoint nuevo: se
  activa desde el panel de skills que ya existía. La UI ahora pasa el
  `checklist` del plan a `ToolCallCard` (antes lo descartaba) y la tarjeta
  del plan nace expandida. 1 test de frontend nuevo.
- **Aprobación atada al perfil:** con Modo Programación activo, las
  herramientas riesgosas piden permiso con botones en la tarjeta
  (`approval_required` + `POST /api/approve`). Reutiliza `approve()` y los
  flags `risky` del motor; 60 s de timeout y rechazo al desconectar.
  3 tests backend + 1 frontend.
- **Diff antes de aprobar:** `_approval_diff()` añade el cambio al evento:
  diff unificado con `difflib` para escritura/edición y el comando para
  `run_shell`, truncado con `clip()`. Sin endpoint ni dependencia nueva.
  5 tests backend + 1 aserción de frontend (suite: 280).
- **Tres ajustes del bucle:** el rechazo de aprobación ya no se reintenta
  (1 solicitud en vez de 4); el planificador no responde de memoria sobre
  archivos (emite `<plan>` y los lee); y un final vacío se sustituye por un
  mensaje explicativo. Todo dentro de bloques existentes, sin funciones ni
  endpoints nuevos. 3 tests (suite: 283).
