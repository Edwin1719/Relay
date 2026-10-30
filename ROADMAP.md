# Relay — Plan de Mejora

> Última actualización: 2026-10-29 — reordenado por impacto real, no por inspiración.
> Estado verificado contra el código (ver *Limitaciones conocidas* en README/AGENTS).
> Prioridad: 🔴 Alta · 🟡 Media · 🟢 Baja · 🗑️ Descartado

---

## 🚀 Visión Estratégica

Relay es un **producto instalable de asistencia IA** para desarrolladores técnicos
y no técnicos, con datos locales e inferencia en la nube.

**Propuesta de valor:**
- Almacenamiento local: sesiones, memoria y workspace en la máquina del usuario.
- Multi-proveedor sin lock-in: Ollama Cloud, DeepSeek y APInex (`providers.py`).
- Investigación web sin API keys: Wigolo + `ddgs`, $0 por consulta.
- Interfaz en español pensada para quien no vive en una terminal.
- Extensible vía MCP (10 integraciones) y skills basadas en prompts.

### 🔷 Estado real (2026-10-29)

- **283 tests backend + 49 frontend** en verde; `tsc` limpio.
- **Modo Programación** con aprobación y diff antes de escribir o ejecutar.
- Un chat a la vez (409 en el segundo); planificador que no responde de memoria.
- Documentación sincronizada con el código, incluidas las limitaciones.
- Medición de contexto: 41 herramientas MCP = 8.980 caracteres (~2.245 tokens),
  27,7% de un prompt de ~8.100 tokens.

### 🔷 Benchmark Nanobot — qué aplica y qué no

**Fortalezas propias:** búsqueda web superior (18 adaptadores + reranking),
Windows-first, y una UI en español frente a configuraciones en inglés.

**Brechas que sí importan:** memoria viva (Dream), API compatible con OpenAI,
automatización real (cron/triggers), y canales más allá de la WebUI.

**Lo que no se copia:** el catálogo de 15+ proveedores (Relay prioriza 3 bien
integrados), los 16 canales y el marketplace. Ver **Descartado** al final.

### 🔷 Memoria Dream — memoria viva

`KODAMA_MEMORY.md` es un archivo estático que solo cambia cuando el usuario dice
"recuerda esto". El objetivo es que aprenda del historial:

- **Fase 1 — Consolidator:** resume mensajes viejos en `memory/history.jsonl`.
- **Fase 2 — Dream:** job que fusiona duplicados y olvida lo obsoleto.
- **Fase 3 — GitStore:** versiona la memoria para inspección y restauración.
- **Fase 4 (opcional):** embeddings cuando la memoria supere el contexto.

**Impacto:** menos presión de contexto y conocimiento acumulado del proyecto.

### 🔷 Multi-Agente

- ✅ Fase 1 — delegación multi-turn con escritura y conciencia de tier.
- ✅ Fase 2 — hasta 3 subagentes en paralelo (`ThreadPoolExecutor`).
- ⏳ Fase 3 — planificador jerárquico y grafo de ejecución en la UI.

---

## ✅ Completado

| # | Tarea | Fecha |
|---|-------|-------|
| 6 | Streaming word-level (asyncio.Queue bridge) | 2026-05-25 |
| 9 | Tests de frontend (Vitest, hoy 49) | 2026-05-25 |
| 19 | Manejo de errores avanzado en UI (banner, stop, loops) | 2026-05-25 |
| 1 | Keep-alive HTTP (OpenerDirector compartido) | 2026-05-25 |
| 2 | Debounce SSE (buffer 50ms) | 2026-05-25 |
| 3 | Lazy load MCP (solo servidores activados) | 2026-05-25 |
| 14 | Drag & drop de archivos | 2026-05-25 |
| — | Validación post-herramienta (`verify_tool_result`) | 2026-05-25 |
| — | Restauración de historial de sesiones (3 fixes) | 2026-05-25 |
| — | Fix MCP Python path (`sys.executable` para `run.bat`) | 2026-05-25 |
| — | Fix Ollama streaming `system_prefix` | 2026-05-25 |
| — | 🌐 Búsqueda web nativa (DuckDuckGo fallback) | 2026-06-28 |
| — | 📄 `KODAMA_MEMORY.md` (memoria entre sesiones) | 2026-06-28 |
| — | 🧩 Multi-agente Fase 1 (delegación multi-turn) | 2026-06-28 |
| — | 🧩 Multi-agente Fase 2 (delegación paralela) | 2026-06-28 |
| **12** | **⌨️ Command Palette (Ctrl+K)** | **2026-06-30** |
| — | 🐛 Fix FilePreview / árbol de archivos / background tasks / catch blocks | 2026-06-30 |
| — | 🧹 Limpieza de dependencias y código muerto | 2026-06-30 |

### Sesión 2026-10-29 — robustez y confianza

| Cambio | Detalle |
|---|---|
| `edit_file` registrada | Se eliminaron 4 entradas falsas y el `KeyError` que abortaba el turno |
| Guard del prompt | Los nombres de herramientas del prompt ⊆ registro (test C4) |
| Sin nombres fantasma | Ni `mcp_tavily-mcp_*` ni `mcp_fetch_*`; la lista del contexto manda |
| Raíz = carpeta elegida | Un `.git` en un ancestro ya no amplía el sandbox |
| Frontera unificada | `is_within_root()` en workspace, `read_files` y el diff |
| Rutas portables | `Path.home()`, `PATH`/`CODEBASE_MEMORY_BIN`, `%KODAMA_RTK_FILTER%` |
| Token fuera del log | Solo se registra la ruta de `.kodama_token` |
| Cerrojo de chat | Un turno a la vez; 409 en el segundo; libera el worker |
| Modo Programación | Perfil + checklist del plan pintado como pasos |
| Aprobación con diff | `write_file`/`patch_file`/`edit_file`/`run_shell` piden permiso |
| Bucle más honesto | Rechazo sin reintento, planificador sin memoria de archivos, final vacío explicado |
| Docs sincronizadas | README con limitaciones reales; AGENTS al día; 283/49 en verde |

---

## 🎯 Pendiente

### 🔴 ALTA — lo que bloquea el salto de calidad

#### 🧠 Mensajes con roles + tool calling nativo
El motor envía **un solo mensaje `user`** y pide las herramientas por texto
(`<tool>{...}</tool>`). Los proveedores OpenAI ofrecen `tools`/`tool_calls`, pero
sin mensajes `assistant`/`tool` el modelo repite la misma llamada hasta agotar
los pasos — probado y revertido. Es el prerrequisito de todo lo demás.

**Esfuerzo:** 3-4 días (refactor del historial + cliente + bucle + tests).
**Riesgo:** alto sin tests de integración → hacer primero el punto siguiente.

#### 🧪 Tests de integración del bucle con respuestas grabadas
La suite usa modelos falsos; el fallo de native tools lo demostró. Grabar
respuestas reales de DeepSeek y reproducirlas permitiría detectar bucles,
reintentos y finales vacíos sin gastar API.

**Esfuerzo:** 1-2 días. **Dependencia:** ninguna.

#### 🛡️ `run_shell` con confirmación fuera del perfil
Hoy solo el Modo Programación pide permiso. Fuera de él, el agente ejecuta
shell sin preguntar. Es el requisito para que alguien más lo use.

**Esfuerzo:** 1 día (reutiliza el canal `approval_required` ya construido).

#### 📑 Tabs de chat
Varias conversaciones simultáneas en pestañas. Es la carencia más visible para
un usuario técnico que compara dos hilos.

**Esfuerzo:** 3-5 días. **Dependencia:** el cerrojo actual es por proceso, no por
sesión; habría que decidir si se permite concurrencia real.

#### 💰 Coste visible
Tokens por turno, tamaño del prompt y cupo restante de APInex en la interfaz.
Hoy el usuario no sabe cuánto gasta ni cuánto le queda.

**Esfuerzo:** 2 días. **Dato ya disponible:** `estimate_prompt_tokens()`.

### 🟡 MEDIA — siguiente release

#### 📦 Instalador nativo para Windows
Python portable + Node portable + acceso directo, sin abrir terminal.

**Esfuerzo:** ~1 semana. **Dependencia:** empaquetado de dependencias.

#### 🌐 API compatible con OpenAI
`POST /v1/chat/completions` que traduzca al agente. Cualquier app con SDK de
OpenAI (Cursor, Continue.dev, scripts) funcionaría con Relay.

**Esfuerzo:** 2-3 días. **Dependencia:** ninguna (el catálogo ya existe).

#### 🐈📉 Auto-Compact + Memoria Dream (fases 1-2)
Consolidar sesiones largas y editar la memoria long-term. Reduce latencia y
presión de contexto en sesiones de 50+ mensajes.

**Esfuerzo:** ~2 semanas en total; empezar por Consolidator.

#### 🐈⏰ Cron + Triggers reales
Sustituir la skill `scheduled_automation.md` (basada en prompts) por trabajos
persistidos en SQLite, con panel de automatizaciones.

**Esfuerzo:** ~1 semana.

#### 🔗 Integración git en la UI
Estado del repo, diff de cambios y commit desde la interfaz. El agente ya lee el
estado; falta la superficie para revisarlo y confirmarlo.

**Esfuerzo:** ~1 semana. **Nota:** no confundir con versionar el proyecto Relay;
esto es una función del producto.

#### 📋 Exportar logs para soporte
Logs rotativos + botón que empaqueta todo en un `.zip`.

**Esfuerzo:** 2 días.

### 🟢 BAJA — cuando haya razones

- 🔄 **Auto-updater** — después del instalador (~1 semana).
- 🐈📦 **Python SDK** — depende de la API OpenAI (~3-4 días).
- 🪝 **Hooks system** — `on_tool_start`/`on_tool_end`; podría sustituir
  `verify_tool_result` (~2 días).
- ⚡ **Virtual scrolling** y **file watcher cache** — rendimiento, no bloquean
  (~2 días cada uno).
- 🌐 **i18n** — el español es el diferenciador; el inglés puede esperar (~3-5 días).
- 🔗 **IDE integration (VS Code)** — alcance alto, valor incierto (~2-3 semanas).
- 📦 **Migración de sesiones antiguas** — las de `~/.mini-coding-agent/` no se
  migran a `<proyecto>/.mini-coding-agent/` (~2 horas).
- 📄 **Atribución MIT del upstream** en `LICENSE` — el motor está vendorizado de
  `mini-coding-agent` (~10 minutos, pero es legal).

### 🗑️ Descartado — no hacer (y por qué)

| Tema | Motivo |
|---|---|
| ⌨️ **Modo CLI nativo** | La WebUI es el producto; añade superficie sin demanda validada |
| 🚀 **Onboarding / Easy Setup con modelo local** | Los modelos locales están excluidos por diseño (ventana 4K) |
| 🏢 **Modo servidor multiusuario** | Contradice local-first y el modelo de un chat a la vez |
| 🛒 **Marketplace de skills** | Requiere backend y negocio; no aporta al uso actual |
| 🐈🔧 **Tool Registry** | El motor ya usa `agent.tools` (dict) y MCP registra ahí; refactor sin beneficio |
| 🐈🔄 **AgentLoop / Runner split** | Refactor de código vendorizado: mucho riesgo, valor interno bajo |
| 🐈📱 **Canal Telegram** | Es otro producto (canales), no un agente de código |
| 🔑 **Licencias offline** | Prematuro sin release ni distribución |
| 🧰 **Selección de herramientas por tarea** | Medido: 41 tools = 8.980 chars (27,7%). Ahorra 1-2k tokens frente al riesgo de ocultar una herramienta necesaria. Se controla **desactivando integraciones** (ver README) |

---

## 📋 Resumen

| Prioridad | Tarea | Esfuerzo |
|---|---|---|
| 🔴 Alta | Mensajes con roles + native tool calling | 3-4 d |
| 🔴 Alta | Tests de integración con respuestas grabadas | 1-2 d |
| 🔴 Alta | Confirmación de `run_shell` fuera del perfil | 1 d |
| 🔴 Alta | Tabs de chat | 3-5 d |
| 🔴 Alta | Coste visible (tokens/cupo) | 2 d |
| 🟡 Media | Instalador Windows | 1 sem |
| 🟡 Media | API compatible con OpenAI | 2-3 d |
| 🟡 Media | Auto-Compact + Memoria Dream | 2 sem |
| 🟡 Media | Cron + Triggers reales | 1 sem |
| 🟡 Media | Git en la UI | 1 sem |
| 🟡 Media | Exportar logs | 2 d |
| 🟢 Baja | Auto-updater | 1 sem |
| 🟢 Baja | Python SDK | 3-4 d |
| 🟢 Baja | Hooks system | 2 d |
| 🟢 Baja | Virtual scrolling / file watcher | 4 d |
| 🟢 Baja | i18n | 3-5 d |
| 🟢 Baja | IDE integration | 2-3 sem |
| 🟢 Baja | Migración de sesiones antiguas | 2 h |
| 🟢 Baja | Atribución MIT upstream | 10 min |

---

## 🎯 Próximos pasos

1. 🧪 **Tests de integración con respuestas grabadas** — la red de seguridad que
   falta antes de tocar el motor.
2. 🧠 **Mensajes con roles + native tool calling** — el mayor salto de fiabilidad.
3. 🛡️ **Confirmación de `run_shell` fuera del perfil** — para que sea usable por
   terceros.
4. 💰 **Coste visible** — deja de ser una caja negra.
5. 📑 **Tabs de chat** — la carencia más visible para un usuario técnico.
