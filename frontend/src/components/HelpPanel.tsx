import { useState } from 'react'
import { HelpCircle, BookOpen, Wrench, Code, Zap, Search, FolderPlus, Bot, MessageSquare, Mail, Globe, Cpu, Puzzle, Brain, ShieldCheck, Bug, FileCode } from 'lucide-react'
import { twMerge } from 'tailwind-merge'

type HelpTab = 'guia' | 'problemas' | 'arquitectura'

const TABS: { id: HelpTab; label: string; icon: typeof BookOpen }[] = [
  { id: 'guia', label: 'Guia rapida', icon: BookOpen },
  { id: 'problemas', label: 'Problemas', icon: Wrench },
  { id: 'arquitectura', label: 'Arquitectura', icon: Code },
]

export function HelpPanel() {
  const [tab, setTab] = useState<HelpTab>('guia')

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* Tab bar */}
      <div className="flex border-b border-bg-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={twMerge(
              'flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors border-b-2',
              tab === t.id
                ? 'text-accent border-accent'
                : 'text-fg-muted border-transparent hover:text-fg'
            )}
          >
            <t.icon size={14} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 text-sm leading-relaxed">
        {tab === 'guia' && <GuiaRapida />}
        {tab === 'problemas' && <SolucionProblemas />}
        {tab === 'arquitectura' && <Arquitectura />}
      </div>
    </div>
  )
}

function Section({ icon: Icon, title, children }: { icon: any; title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="text-accent" />
        <h3 className="text-sm font-semibold text-fg">{title}</h3>
      </div>
      <div className="text-fg-muted space-y-1.5">{children}</div>
    </div>
  )
}

function CodeBlock({ children }: { children: string }) {
  return (
    <code className="block px-2.5 py-1.5 mt-1 rounded bg-bg-hover text-xs text-fg font-mono whitespace-pre-wrap break-all">
      {children}
    </code>
  )
}

// ═══════════════════════════════════════════════════════════════
// Tab 1: Guia rapida
// ═══════════════════════════════════════════════════════════════

function GuiaRapida() {
  return (
    <>
      <Section icon={Zap} title="Que es Relay?">
        <p>
          Relay es un <strong className="text-fg">asistente personal de IA con
          capacidades agénticas</strong>: planifica, usa herramientas sobre tu
          proyecto y pide permiso antes de escribir o ejecutar. Elige el modelo
          que más te convenga y se queda con tus datos.
        </p>
      </Section>

      <Section icon={Search} title="Que puede hacer por ti?">
        <ul className="space-y-2">
          <li className="flex items-start gap-2">
            <Search size={14} className="text-blue-400 mt-0.5 flex-shrink-0" />
            <span><strong className="text-fg">Investigar:</strong> buscar informacion actualizada en internet, analizar datos, comparar opciones.</span>
          </li>
          <li className="flex items-start gap-2">
            <FolderPlus size={14} className="text-emerald-400 mt-0.5 flex-shrink-0" />
            <span><strong className="text-fg">Crear proyectos:</strong> generar codigo, apps web, scripts en Python, landing pages.</span>
          </li>
          <li className="flex items-start gap-2">
            <Bot size={14} className="text-purple-400 mt-0.5 flex-shrink-0" />
            <span><strong className="text-fg">Automatizar:</strong> programar tareas, enviar correos, procesar archivos por lotes.</span>
          </li>
          <li className="flex items-start gap-2">
            <MessageSquare size={14} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <span><strong className="text-fg">Chatear:</strong> conversacion libre, brainstorming, asistencia general.</span>
          </li>
          <li className="flex items-start gap-2">
            <Mail size={14} className="text-red-400 mt-0.5 flex-shrink-0" />
            <span><strong className="text-fg">Gestionar correo:</strong> enviar y leer emails de Gmail sin salir de Relay.</span>
          </li>
        </ul>
      </Section>

      <Section icon={Zap} title="Como empezar">
        <ol className="list-decimal list-inside space-y-2 ml-1">
          <li>
            <strong className="text-fg">Escribe tu objetivo</strong> en el chat. Se claro y especifico.
            <p className="text-xs mt-0.5 ml-5">Ejemplo: "Crea un script que organice mis archivos de Descargas por tipo de archivo"</p>
          </li>
          <li>
            <strong className="text-fg">Relay planea y ejecuta</strong>. Veras los pasos que sigue en tiempo real.
          </li>
          <li>
            <strong className="text-fg">Revisa el resultado</strong>. Si algo no quedo bien, pidele ajustes en el chat.
          </li>
        </ol>
      </Section>

      <Section icon={Cpu} title="Modelos de IA disponibles">
        <ul className="space-y-1.5">
          <li className="flex items-start gap-2">
            <Brain size={14} className="text-purple-400 mt-0.5 flex-shrink-0" />
            <span><strong className="text-fg">Avanzados (DeepSeek, APInex):</strong> tareas agenticas de varios pasos — leer, editar y verificar codigo. Requieren API key.</span>
          </li>
          <li className="flex items-start gap-2">
            <Zap size={14} className="text-emerald-400 mt-0.5 flex-shrink-0" />
            <span><strong className="text-fg">Rápidos (Ollama cloud):</strong> tareas cortas y de complejidad media. No descargan modelos al disco.</span>
          </li>
        </ul>
        <p className="text-xs mt-2">Cambia de modelo desde el panel de Configuracion en cualquier momento.</p>
      </Section>

      <Section icon={Puzzle} title="Conectores disponibles">
        <p>Relay se conecta a servicios externos para ampliar sus capacidades:</p>
        <ul className="space-y-1 mt-1.5">
          <li><strong className="text-fg">Busqueda web:</strong> Tavily Search, Web Fetch</li>
          <li><strong className="text-fg">Navegacion:</strong> Playwright, Puppeteer (abren paginas web)</li>
          <li><strong className="text-fg">Documentacion:</strong> Context7 (docs actualizadas de librerias)</li>
          <li><strong className="text-fg">GitHub:</strong> gestionar repos, PRs, issues</li>
          <li><strong className="text-fg">Google Maps:</strong> buscar lugares y direcciones</li>
          <li><strong className="text-fg">Gmail:</strong> enviar y leer correos</li>
        </ul>
        <p className="text-xs mt-2">Activalos desde el panel de Conectores. Algunos requieren claves de API.</p>
      </Section>

      <Section icon={Brain} title="Capacidades especiales">
        <ul className="space-y-1">
          <li><strong className="text-fg">Debug:</strong> encuentra y arregla errores en tu codigo</li>
          <li><strong className="text-fg">Revision de codigo:</strong> analiza calidad, seguridad y mejores practicas</li>
          <li><strong className="text-fg">TDD:</strong> escribe pruebas antes del codigo</li>
          <li><strong className="text-fg">Seguridad:</strong> auditoria de vulnerabilidades</li>
        </ul>
        <p className="text-xs mt-2">Activalas desde el panel de Capacidades.</p>
      </Section>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════
// Tab 2: Solucion de problemas
// ═══════════════════════════════════════════════════════════════

function SolucionProblemas() {
  return (
    <>
      <Section icon={Cpu} title="Ollama no responde">
        <p><strong className="text-fg">Causa:</strong> Relay sirve los modelos cloud de Ollama a traves del servidor local, que no esta corriendo.</p>
        <p className="mt-1"><strong className="text-fg">Solucion:</strong></p>
        <ol className="list-decimal list-inside space-y-1 ml-1 mt-1">
          <li>Abre una terminal y ejecuta: <CodeBlock>ollama serve</CodeBlock></li>
          <li>Verifica que aparece un modelo terminado en <code className="text-xs bg-bg-hover px-1 rounded">-cloud</code>: <CodeBlock>ollama list</CodeBlock></li>
          <li>Reinicia Relay</li>
        </ol>
      </Section>

      <Section icon={Globe} title="El proveedor cloud no funciona">
        <p><strong className="text-fg">Causa:</strong> Falta la API key, no es valida, o el proveedor aplico un limite de peticiones.</p>
        <p className="mt-1"><strong className="text-fg">Solucion:</strong></p>
        <ol className="list-decimal list-inside space-y-1 ml-1 mt-1">
          <li>Abre <code className="text-xs bg-bg-hover px-1 rounded">backend\.env</code></li>
          <li>Agrega tu clave: <CodeBlock>DEEPSEEK_API_KEY=sk-tu-clave-aqui</CodeBlock></li>
          <li>Para APInex: <CodeBlock>APINEX_API_KEY=tu-clave-apinex</CodeBlock></li>
          <li>Reinicia Relay</li>
        </ol>
        <p className="mt-1 text-xs">Los errores 429 (limite de peticiones) se reintentan solos con espera progresiva.</p>
      </Section>

      <Section icon={Puzzle} title="Un conector no se activa">
        <p><strong className="text-fg">Causa:</strong> Falta instalar dependencias (npx, uvx) o la API key.</p>
        <p className="mt-1"><strong className="text-fg">Solucion:</strong></p>
        <ul className="list-disc list-inside space-y-1 ml-1 mt-1">
          <li>Instala Node.js desde <a href="https://nodejs.org" className="text-accent underline" target="_blank">nodejs.org</a> (necesario para npx)</li>
          <li>Instala uv: <CodeBlock>pip install uv</CodeBlock></li>
          <li>Revisa que la API key este en <code className="text-xs bg-bg-hover px-1 rounded">backend\.env</code></li>
          <li>Si el conector muestra <span className="text-red-400"> rojo</span>, la dependencia no esta instalada</li>
        </ul>
      </Section>

      <Section icon={ShieldCheck} title="Error de token de acceso">
        <p><strong className="text-fg">Causa:</strong> El token de autenticacion no coincide.</p>
        <p className="mt-1"><strong className="text-fg">Solucion:</strong></p>
        <ul className="list-disc list-inside space-y-1 ml-1 mt-1">
          <li>El token se genera automaticamente al iniciar Relay</li>
          <li>Si accedes desde otro navegador, inicia con: <CodeBlock>python run.py --no-auth</CodeBlock></li>
          <li>El token esta en el archivo <code className="text-xs bg-bg-hover px-1 rounded">backend\.kodama_token</code></li>
        </ul>
      </Section>

      <Section icon={Bug} title="El chat se quedo pegado o no responde">
        <p><strong className="text-fg">Soluciones:</strong></p>
        <ul className="list-disc list-inside space-y-1 ml-1 mt-1">
          <li>Haz clic en el icono de papelera para reiniciar el chat</li>
          <li>Cambia a otro modelo desde el panel de Configuracion</li>
          <li>Reinicia Relay completamente</li>
          <li>Si usas motor local, verifica que Ollama este corriendo</li>
        </ul>
      </Section>

      <Section icon={FileCode} title="Error al leer o escribir archivos">
        <p><strong className="text-fg">Causa:</strong> Relay solo puede acceder a archivos dentro de tu proyecto.</p>
        <p className="mt-1"><strong className="text-fg">Solucion:</strong></p>
        <ul className="list-disc list-inside space-y-1 ml-1 mt-1">
          <li>Asegurate de que el archivo este dentro de la carpeta del proyecto</li>
          <li>Cambia el workspace desde el panel de Configuracion</li>
          <li>Verifica que el archivo exista y no este bloqueado por otro programa</li>
        </ul>
      </Section>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════
// Tab 3: Arquitectura (para developers)
// ═══════════════════════════════════════════════════════════════

function Arquitectura() {
  return (
    <>
      <Section icon={Code} title="Stack tecnologico">
        <ul className="space-y-1">
          <li><strong className="text-fg">Backend:</strong> Python 3.10+ con FastAPI en puerto 8000</li>
          <li><strong className="text-fg">Frontend:</strong> React 18 + TypeScript + Vite + Tailwind CSS en puerto 5173</li>
          <li><strong className="text-fg">Base de datos:</strong> SQLite (sesiones, configuraciones, salud MCP)</li>
          <li><strong className="text-fg">IA:</strong> DeepSeek + APInex (avanzados) y Ollama Cloud (rapidos)</li>
          <li><strong className="text-fg">Conectores:</strong> MCP SDK (Model Context Protocol) via stdio</li>
        </ul>
      </Section>

      <Section icon={Zap} title="Flujo de datos">
        <ol className="list-decimal list-inside space-y-2 ml-1">
          <li>
            <strong className="text-fg">El usuario escribe</strong> en el chat del frontend
          </li>
          <li>
            <strong className="text-fg">POST /api/chat</strong> envia el mensaje al backend via SSE
          </li>
          <li>
            <strong className="text-fg">El agente planifica</strong> (KodamaAgent + build_system_prompt)
          </li>
          <li>
            <strong className="text-fg">Ejecuta herramientas</strong> (leer archivos, buscar, shell, MCP)
          </li>
          <li>
            <strong className="text-fg">El modelo genera respuesta</strong> (segun el proveedor activo)
          </li>
          <li>
            <strong className="text-fg">Streaming SSE</strong> envia cada paso al frontend en tiempo real
          </li>
        </ol>
      </Section>

      <Section icon={FileCode} title="Estructura de archivos clave">
        <div className="space-y-1.5 text-xs">
          <div><strong className="text-fg">backend/</strong></div>
          <div className="ml-3"><code>main.py</code> — FastAPI, endpoints REST + SSE</div>
          <div className="ml-3"><code>agent_core.py</code> — motor del agente (vendorizado)</div>
          <div className="ml-3"><code>agent_stream.py</code> — streaming, planificacion, prompt builder</div>
          <div className="ml-3"><code>providers.py</code> — catalogo de proveedores y modelos</div>
          <div className="ml-3"><code>model_clients.py</code> — cliente OpenAI-compatible + Ollama</div>
          <div className="ml-3"><code>mcp_manager.py</code> — gestion de servidores MCP</div>
          <div className="ml-3"><code>integrations_manager.py</code> — marketplace de conectores</div>
          <div className="ml-3"><code>skills_manager.py</code> — sistema de capacidades</div>
          <div className="ml-3"><code>session_db.py</code> — SQLite (sesiones, settings, salud)</div>
          <div className="mt-2"><strong className="text-fg">frontend/src/</strong></div>
          <div className="ml-3"><code>App.tsx</code> — layout 3 columnas + tabs</div>
          <div className="ml-3"><code>hooks/useChat.ts</code> — streaming SSE + estado</div>
          <div className="ml-3"><code>api/client.ts</code> — cliente HTTP tipado</div>
          <div className="ml-3"><code>components/</code> — ChatPanel, FileExplorer, IntegrationsPanel, etc.</div>
        </div>
      </Section>

      <Section icon={Puzzle} title="Como agregar un conector">
        <ol className="list-decimal list-inside space-y-1.5 ml-1">
          <li>
            Agrega una entrada en <code className="text-xs bg-bg-hover px-1 rounded">integrations_manager.py &gt; CATALOG</code>
          </li>
          <li>
            Define: <code className="text-xs bg-bg-hover px-1 rounded">server_name, command, default_args, config_fields</code>
          </li>
          <li>
            Si requiere API key, agregala en <code className="text-xs bg-bg-hover px-1 rounded">backend\.env</code>
          </li>
          <li>El conector aparece automaticamente en el panel de Conectores</li>
        </ol>
        <div className="mt-2 p-2.5 rounded bg-bg-hover/50 border border-bg-border">
          <div className="text-xs text-fg-dim mb-1">Ejemplo:</div>
          <pre className="text-xs text-fg font-mono whitespace-pre overflow-x-auto">{`{
  "server_name": "mi-conector",
  "display_name": "Mi Servicio",
  "command": "npx",
  "default_args": ["-y", "mi-servicio-mcp"],
  "config_fields": [
    {"name": "API_KEY", "type": "api_key", "env_var": "MI_API_KEY", "required": true}
  ]
}`}</pre>
        </div>
      </Section>

      <Section icon={Brain} title="Como agregar una capacidad (skill)">
        <ol className="list-decimal list-inside space-y-1.5 ml-1">
          <li>Crea un archivo <code className="text-xs bg-bg-hover px-1 rounded">.md</code> en <code className="text-xs bg-bg-hover px-1 rounded">backend/skills/</code></li>
          <li>Agrega una entrada en <code className="text-xs bg-bg-hover px-1 rounded">skills_manager.py &gt; SKILLS_CATALOG</code></li>
          <li>El contenido del archivo .md se inyecta en el system prompt del agente</li>
        </ol>
      </Section>

      <Section icon={Globe} title="Endpoints principales">
        <div className="space-y-1 text-xs">
          <div><code className="text-fg">GET /api/status</code> — estado del agente + MCP</div>
          <div><code className="text-fg">POST /api/chat</code> — chat con streaming SSE</div>
          <div><code className="text-fg">GET /api/models</code> — modelos disponibles</div>
          <div><code className="text-fg">GET /api/workspace/*</code> — explorador de archivos</div>
          <div><code className="text-fg">GET /api/sessions/*</code> — gestion de sesiones</div>
          <div><code className="text-fg">GET /api/integrations/*</code> — marketplace MCP</div>
          <div><code className="text-fg">GET /api/skills</code> — capacidades</div>
          <div><code className="text-fg">POST /api/mcp/reset</code> — reactivar conector bloqueado</div>
          <div><code className="text-fg">GET /api/onboarding/*</code> — estado del wizard</div>
          <div><code className="text-fg">GET /api/auth-token</code> — token de acceso</div>
        </div>
      </Section>
    </>
  )
}
