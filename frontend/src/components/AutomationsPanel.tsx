import { useState } from 'react'
import {
  Play, Globe, ShieldAlert, MessageSquare, Code, Calendar,
  Puzzle, Brain, Search, Map, Github, FileSearch, Bug,
  RefreshCw, Chrome, Mail, FileCode, Layers, Zap, BookOpen,
  ClipboardList
} from 'lucide-react'
import type { ModelInfo, ModelTier } from '../api/client'

export interface AutomationWorkflow {
  id: string
  title: string
  description: string
  promptTemplate: string
  suggestedModelType: ModelTier | 'any'
  icon: string
  category: 'investigacion' | 'comunicacion' | 'codigo' | 'automatizacion' | 'browser' | 'datos'
  mcpRequirements: string[]
  skillRequirements: string[]
}

const CATEGORIES = {
  investigacion: { label: '🔍 Investigación', color: 'text-blue-400' },
  comunicacion:  { label: '💬 Comunicación', color: 'text-green-400' },
  codigo:        { label: '💻 Código', color: 'text-violet-400' },
  automatizacion:{ label: '⚙️ Automatización', color: 'text-orange-400' },
  browser:       { label: '🌐 Navegador', color: 'text-cyan-400' },
  datos:         { label: '📊 Datos & Archivos', color: 'text-yellow-400' },
}

const AUTOMATIONS: AutomationWorkflow[] = [
  // ── INVESTIGACIÓN ─────────────────────────────────────────────
  {
    id: 'market-report',
    title: 'Reporte de Competencia',
    description: 'Busca información reciente en la web sobre un competidor o tema, redacta un reporte ejecutivo y lo envía por correo.',
    promptTemplate: 'Usa mcp_tavily-mcp_tavily-search para buscar información reciente sobre "[Tema/Competidor]". Con los resultados, redacta un reporte ejecutivo claro con secciones: Resumen, Hallazgos Clave y Conclusiones. Envía el reporte por correo usando mcp_gmail_enviar_correo a [Correo Electrónico] con asunto "Reporte: [Tema/Competidor]".',
    suggestedModelType: 'deep',
    icon: 'globe',
    category: 'investigacion',
    mcpRequirements: ['tavily', 'gmail'],
    skillRequirements: []
  },
  {
    id: 'news-digest',
    title: 'Digest Diario de Noticias',
    description: 'Busca noticias recientes sobre un tema de tu industria y te envía un resumen diario por WhatsApp.',
    promptTemplate: 'Usa mcp_tavily-mcp_tavily-search para buscar las noticias más recientes sobre "[Industria/Tema]" de los últimos 2 días. Resume los 5 hallazgos más importantes en un texto corto y directo. Luego envíalo por WhatsApp usando mcp_whatsapp_enviar_whatsapp al número [Número con código de país, ej: +573001234567] con el texto del resumen.',
    suggestedModelType: 'deep',
    icon: 'bookopen',
    category: 'investigacion',
    mcpRequirements: ['tavily', 'whatsapp'],
    skillRequirements: []
  },
  {
    id: 'library-docs',
    title: 'Consultar Documentación Técnica',
    description: 'Busca la documentación oficial actualizada de cualquier librería o framework (React, FastAPI, etc.).',
    promptTemplate: 'Necesito documentación actualizada sobre "[Librería o Framework, ej: React, FastAPI, LangChain]". Usa mcp_Context7_resolve-library-id para encontrar el ID de la librería y luego mcp_Context7_query-docs para obtener documentación sobre "[Tema específico, ej: hooks, autenticación, streaming]". Responde con ejemplos de código claros.',
    suggestedModelType: 'fast',
    icon: 'bookopen',
    category: 'investigacion',
    mcpRequirements: ['Context7'],
    skillRequirements: []
  },
  {
    id: 'web-extract',
    title: 'Extraer Contenido de una Web',
    description: 'Extrae y resume el contenido de una página web o artículo específico.',
    promptTemplate: 'Visita y extrae el contenido completo de esta URL: [URL de la página]. Usa mcp_fetch_fetch con max_length=5000. Una vez obtenido el contenido, resume los puntos más importantes en forma de lista clara y estructurada.',
    suggestedModelType: 'fast',
    icon: 'filesearch',
    category: 'investigacion',
    mcpRequirements: ['fetch'],
    skillRequirements: []
  },
  {
    id: 'google-maps-search',
    title: 'Buscar Lugares Cercanos',
    description: 'Busca negocios, restaurantes o servicios en una ubicación específica usando Google Maps.',
    promptTemplate: 'Usa mcp_google-maps_search_places para buscar "[Tipo de lugar, ej: restaurantes italianos, farmacias, coworkings]" cerca de "[Ciudad o dirección]". Muestra los resultados en una tabla con nombre, dirección y calificación si está disponible.',
    suggestedModelType: 'any',
    icon: 'map',
    category: 'investigacion',
    mcpRequirements: ['google-maps'],
    skillRequirements: []
  },

  // ── COMUNICACIÓN ──────────────────────────────────────────────
  {
    id: 'whatsapp-bulk',
    title: 'Envío Masivo por WhatsApp',
    description: 'Lee contactos desde un CSV en el workspace y envía un mensaje personalizado a cada uno por WhatsApp.',
    promptTemplate: 'Usa read_file para leer el archivo [nombre_archivo.csv] en el workspace. Extrae la lista de contactos con su nombre y número de teléfono. Usando la skill de Batch Processing para validar los datos de forma segura, envía a cada contacto el siguiente mensaje por WhatsApp usando mcp_whatsapp_enviar_whatsapp: "Hola [Nombre], [Mensaje personalizado]". Reporta cuántos mensajes se enviaron exitosamente.',
    suggestedModelType: 'fast',
    icon: 'message',
    category: 'comunicacion',
    mcpRequirements: ['whatsapp'],
    skillRequirements: ['batch']
  },
  {
    id: 'gmail-summary',
    title: 'Resumen de Correos No Leídos',
    description: 'Revisa tu bandeja de entrada, lista los correos no leídos y te da un resumen de los más importantes.',
    promptTemplate: 'Usa mcp_gmail_revisar_no_leidos para obtener mis correos no leídos. Analiza cada uno y clasifícalos por prioridad (Alta/Media/Baja) según el remitente y el asunto. Presenta los resultados en una tabla markdown con columnas: Prioridad, Remitente, Asunto y Resumen breve.',
    suggestedModelType: 'deep',
    icon: 'mail',
    category: 'comunicacion',
    mcpRequirements: ['gmail'],
    skillRequirements: []
  },
  {
    id: 'gmail-search',
    title: 'Buscar Correos por Remitente',
    description: 'Encuentra todos los correos de un remitente específico y te muestra un resumen.',
    promptTemplate: 'Usa mcp_gmail_buscar_por_remitente para buscar todos los correos enviados por "[Correo o nombre del remitente]". Muestra los 10 más recientes en una lista con fecha, asunto y un resumen de 1 línea de cada uno.',
    suggestedModelType: 'any',
    icon: 'mail',
    category: 'comunicacion',
    mcpRequirements: ['gmail'],
    skillRequirements: []
  },

  // ── CÓDIGO ───────────────────────────────────────────────────
  {
    id: 'security-audit',
    title: 'Auditoría de Seguridad Express',
    description: 'Escanea el código del workspace buscando vulnerabilidades OWASP, secretos expuestos y genera un reporte.',
    promptTemplate: 'Analiza el código en el workspace actual buscando vulnerabilidades de seguridad (OWASP Top 10), secretos o credenciales expuestos en el código, y dependencias desactualizadas. Aplica estrictamente las directrices de la skill de Security Review. Genera un reporte detallado llamado security_report.md con las vulnerabilidades clasificadas por severidad (Crítica/Alta/Media/Baja) y las recomendaciones de corrección.',
    suggestedModelType: 'deep',
    icon: 'shield',
    category: 'codigo',
    mcpRequirements: [],
    skillRequirements: ['security']
  },
  {
    id: 'code-review',
    title: 'Revisión de Código (Code Review)',
    description: 'Realiza una revisión multidimensional del código: correctness, seguridad, calidad, rendimiento y cobertura de tests.',
    promptTemplate: 'Realiza un Code Review completo del archivo [nombre_del_archivo o directorio] en el workspace. Aplica la skill de Code Review para evaluar: correctness, seguridad, calidad del código, rendimiento e impacto en otros archivos. Genera un reporte estructurado con hallazgos, sugerencias de mejora y un resumen ejecutivo.',
    suggestedModelType: 'deep',
    icon: 'clipboardlist',
    category: 'codigo',
    mcpRequirements: [],
    skillRequirements: ['review']
  },
  {
    id: 'tdd-feature',
    title: 'Desarrollo Guiado por TDD',
    description: 'Implementa una funcionalidad nueva aplicando rigurosamente el ciclo Red-Green-Refactor.',
    promptTemplate: 'Necesito implementar la siguiente funcionalidad: [Describir la funcionalidad con detalle]. Aplica estrictamente el ciclo Red-Green-Refactor usando la skill de TDD. Pasos: 1) Escribe los tests unitarios primero, 2) Ejecútalos para ver que fallan (Red), 3) Implementa el código mínimo para pasarlos (Green), 4) Refactoriza. Documenta cada fase claramente.',
    suggestedModelType: 'fast',
    icon: 'code',
    category: 'codigo',
    mcpRequirements: [],
    skillRequirements: ['tdd']
  },
  {
    id: 'debug-session',
    title: 'Sesión de Debugging Sistemático',
    description: 'Analiza un bug o comportamiento inesperado usando el proceso de 4 fases: Root Cause, Pattern Analysis, Hypothesis e Implementation.',
    promptTemplate: 'Tengo el siguiente bug o comportamiento inesperado: "[Describir el problema, el error o el comportamiento]". Aplica la skill de Debug con el proceso de 4 fases: 1) Root Cause Analysis — investiga el código, 2) Pattern Analysis — busca patrones similares en el proyecto, 3) Hypothesis — formula hipótesis del problema, 4) Implementation — propone y aplica el fix. Muestra tu razonamiento en cada fase.',
    suggestedModelType: 'deep',
    icon: 'bug',
    category: 'codigo',
    mcpRequirements: [],
    skillRequirements: ['debug']
  },
  {
    id: 'batch-refactor',
    title: 'Refactorización por Lotes',
    description: 'Aplica una transformación o refactorización a múltiples archivos del workspace de forma segura, validando una muestra primero.',
    promptTemplate: 'Necesito refactorizar todos los archivos [extensión, ej: *.py, *.tsx] del workspace para [describir la transformación, ej: "agregar tipado estricto", "reemplazar console.log por logger", "convertir funciones a async/await"]. Usa la skill de Batch Processing: primero valida la transformación en 1 archivo de muestra, muéstrame el resultado, y si lo apruebo, aplica al resto. Genera un reporte final con los archivos modificados.',
    suggestedModelType: 'deep',
    icon: 'layers',
    category: 'codigo',
    mcpRequirements: [],
    skillRequirements: ['batch']
  },
  {
    id: 'github-pr',
    title: 'Crear Pull Request en GitHub',
    description: 'Revisa los cambios actuales y crea un Pull Request en tu repositorio de GitHub con descripción automática.',
    promptTemplate: 'Usa run_shell con "git diff --stat HEAD" para ver los cambios del proyecto. Analiza los cambios y genera una descripción de PR clara con: qué se cambió, por qué y cómo probarlo. Luego usa mcp_github_create_pr para crear el Pull Request en el repositorio "[owner/repo]" desde la rama "[rama-origen]" hacia "[rama-destino]" con el título "[Título del PR]".',
    suggestedModelType: 'deep',
    icon: 'github',
    category: 'codigo',
    mcpRequirements: ['github'],
    skillRequirements: ['review']
  },
  {
    id: 'github-issues',
    title: 'Gestionar Issues de GitHub',
    description: 'Lista y prioriza los issues abiertos de tu repositorio de GitHub.',
    promptTemplate: 'Usa mcp_github_list_issues para listar todos los issues abiertos del repositorio "[owner/repo]". Analiza cada issue y crea una tabla con: Número, Título, Etiquetas y Prioridad sugerida (Alta/Media/Baja) basada en el título y descripción. Agrupa por prioridad.',
    suggestedModelType: 'any',
    icon: 'github',
    category: 'codigo',
    mcpRequirements: ['github'],
    skillRequirements: []
  },

  // ── NAVEGADOR ────────────────────────────────────────────────
  {
    id: 'browser-scrape',
    title: 'Automatización de Navegador Web',
    description: 'Navega a una web, realiza acciones (clic, formularios, captura) y extrae información usando Playwright.',
    promptTemplate: 'Usa mcp_playwright_navigate para ir a "[URL]". Luego [describe la acción: "haz clic en el botón de Login", "completa el formulario con usuario [user] y contraseña [pass]", "extrae la tabla de precios"]. Usa mcp_playwright_snapshot para capturar el estado de la página en momentos clave. Reporta los resultados obtenidos.',
    suggestedModelType: 'deep',
    icon: 'chrome',
    category: 'browser',
    mcpRequirements: ['playwright'],
    skillRequirements: []
  },
  {
    id: 'screenshot-report',
    title: 'Captura y Reporte Visual Web',
    description: 'Visita una URL, toma capturas de pantalla y genera un reporte sobre el contenido visual de la página.',
    promptTemplate: 'Usa mcp_playwright_navigate para visitar "[URL]". Toma un snapshot con mcp_playwright_snapshot para capturar el estado visual. Analiza el contenido visible y genera un reporte sobre: qué información presenta la página, su estructura principal y cualquier elemento relevante que encuentres.',
    suggestedModelType: 'deep',
    icon: 'chrome',
    category: 'browser',
    mcpRequirements: ['playwright'],
    skillRequirements: []
  },

  // ── AUTOMATIZACIÓN ───────────────────────────────────────────
  {
    id: 'scheduler-task',
    title: 'Programar Tarea Recurrente',
    description: 'Crea un script y lo programa para que se ejecute automáticamente con el programador de Windows.',
    promptTemplate: 'Ayúdame a crear una automatización programada en Windows para: [Describir la tarea con detalle, ej: "generar un backup de la carpeta Documentos"]. Usa la skill de Scheduled Automation para: 1) Crear el script necesario, 2) Configurarlo para que corra [todos los días/cada hora/cada semana] a las [Hora], 3) Registrarlo en el Programador de Tareas de Windows. Confirma que quedó configurado correctamente.',
    suggestedModelType: 'any',
    icon: 'calendar',
    category: 'automatizacion',
    mcpRequirements: [],
    skillRequirements: ['scheduled_automation']
  },
  {
    id: 'filesystem-organizer',
    title: 'Organizar Carpeta de Archivos',
    description: 'Analiza una carpeta externa al proyecto (Descargas, Documentos) y organiza los archivos por tipo o fecha.',
    promptTemplate: 'Usa mcp_filesystem_list_directory para listar el contenido de la carpeta "[Ruta completa, ej: C:\\Users\\TuUsuario\\Downloads]". Analiza los archivos y propone un plan de organización (por tipo de archivo, por fecha o por proyecto). Con mi aprobación, usa mcp_filesystem_move para mover los archivos a subcarpetas organizadas. Genera un reporte de los cambios realizados.',
    suggestedModelType: 'fast',
    icon: 'filecode',
    category: 'automatizacion',
    mcpRequirements: ['filesystem'],
    skillRequirements: ['batch']
  },
]

interface AutomationsPanelProps {
  onSelectAutomation: (prompt: string, suggestedModelType: ModelTier | 'any') => void
  models: ModelInfo[]
  activeModel: string
}

export function AutomationsPanel({ onSelectAutomation, models }: AutomationsPanelProps) {
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState<string>('all')

  const filteredAutomations = AUTOMATIONS.filter((a) => {
    const matchSearch =
      a.title.toLowerCase().includes(search.toLowerCase()) ||
      a.description.toLowerCase().includes(search.toLowerCase())
    const matchCategory = activeCategory === 'all' || a.category === activeCategory
    return matchSearch && matchCategory
  })

  const renderIcon = (type: string) => {
    const size = 15
    const cls = 'text-accent'
    switch (type) {
      case 'globe':       return <Globe size={size} className={cls} />
      case 'shield':      return <ShieldAlert size={size} className={cls} />
      case 'message':     return <MessageSquare size={size} className={cls} />
      case 'code':        return <Code size={size} className={cls} />
      case 'calendar':    return <Calendar size={size} className={cls} />
      case 'map':         return <Map size={size} className={cls} />
      case 'github':      return <Github size={size} className={cls} />
      case 'filesearch':  return <FileSearch size={size} className={cls} />
      case 'bug':         return <Bug size={size} className={cls} />
      case 'chrome':      return <Chrome size={size} className={cls} />
      case 'mail':        return <Mail size={size} className={cls} />
      case 'filecode':    return <FileCode size={size} className={cls} />
      case 'layers':      return <Layers size={size} className={cls} />
      case 'bookopen':    return <BookOpen size={size} className={cls} />
      case 'clipboardlist': return <ClipboardList size={size} className={cls} />
      default:            return <Zap size={size} className={cls} />
    }
  }

  const getSuggestedModelLabel = (type: ModelTier | 'any') => {
    if (type === 'any') {
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border bg-blue-900/30 text-blue-300 border-blue-500/20">
          ⚡ Cualquiera
        </span>
      )
    }
    const available = models.some((m) => m.tier === type)
    const deep = type === 'deep'
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border ${
        available
          ? deep
            ? 'bg-purple-900/30 text-purple-300 border-purple-500/20'
            : 'bg-emerald-900/30 text-emerald-300 border-emerald-500/20'
          : 'bg-bg-hover text-fg-dim border-bg-border'
      }`}>
        {deep ? '🧠 Avanzado' : '⚡ Rápido'} {available ? '✓' : '(No config)'}
      </span>
    )
  }

  return (
    <div className="flex flex-col h-full bg-bg-surface/30">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-bg-border bg-bg-surface">
        <div className="flex items-center gap-2">
          <Play size={15} className="text-accent" />
          <span className="text-sm font-semibold text-fg">Flujos Automáticos</span>
        </div>
        <span className="text-[10px] text-fg-dim px-1.5 py-0.5 rounded bg-bg-hover border border-bg-border">
          {AUTOMATIONS.length} flujos
        </span>
      </div>

      {/* Search bar */}
      <div className="px-3 pt-3 pb-2 border-b border-bg-border bg-bg-surface/50 space-y-2">
        <div className="relative flex items-center">
          <Search size={13} className="absolute left-2.5 text-fg-dim" />
          <input
            type="text"
            placeholder="Buscar flujo..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-bg-base border border-bg-border rounded pl-8 pr-3 py-1.5 text-xs w-full outline-none focus:border-accent transition-colors"
          />
        </div>
        {/* Category filter */}
        <div className="flex flex-wrap gap-1">
          <button
            onClick={() => setActiveCategory('all')}
            className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors border ${
              activeCategory === 'all'
                ? 'bg-accent/20 text-accent border-accent/30'
                : 'bg-bg-base text-fg-dim border-bg-border hover:text-fg'
            }`}
          >
            Todos
          </button>
          {Object.entries(CATEGORIES).map(([key, cat]) => (
            <button
              key={key}
              onClick={() => setActiveCategory(key)}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors border ${
                activeCategory === key
                  ? 'bg-accent/20 text-accent border-accent/30'
                  : 'bg-bg-base text-fg-dim border-bg-border hover:text-fg'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Automations list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {filteredAutomations.length === 0 ? (
          <p className="text-xs text-fg-dim text-center py-8">
            No se encontraron flujos para "{search}".
          </p>
        ) : (
          filteredAutomations.map((auto) => (
            <div
              key={auto.id}
              onClick={() => onSelectAutomation(auto.promptTemplate, auto.suggestedModelType)}
              className="group rounded-lg border border-bg-border bg-bg-surface p-3 cursor-pointer hover:border-accent hover:shadow-lg hover:shadow-accent/5 transition-all duration-200"
            >
              <div className="flex items-start gap-2.5">
                <div className="mt-0.5 p-1.5 rounded bg-accent/5 border border-accent-muted/20 group-hover:bg-accent/10 transition-colors flex-shrink-0">
                  {renderIcon(auto.icon)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-1">
                    <h3 className="text-xs font-semibold text-fg group-hover:text-accent transition-colors leading-tight">
                      {auto.title}
                    </h3>
                    <span className={`text-[9px] font-medium whitespace-nowrap ${CATEGORIES[auto.category].color} opacity-70`}>
                      {CATEGORIES[auto.category].label.split(' ')[0]}
                    </span>
                  </div>
                  <p className="text-[11px] text-fg-muted mt-1 leading-relaxed">
                    {auto.description}
                  </p>
                </div>
              </div>

              {/* Requirements & Model badge */}
              <div className="mt-2.5 flex flex-wrap items-center gap-1 pt-2 border-t border-bg-border/40">
                {getSuggestedModelLabel(auto.suggestedModelType)}

                {auto.mcpRequirements.map((req) => (
                  <span
                    key={req}
                    className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-950/40 text-orange-400 border border-orange-500/20"
                    title={`Requiere servidor MCP: ${req}`}
                  >
                    <Puzzle size={8} />
                    {req}
                  </span>
                ))}

                {auto.skillRequirements.map((req) => (
                  <span
                    key={req}
                    className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-pink-950/40 text-pink-400 border border-pink-500/20"
                    title={`Requiere Skill: ${req}`}
                  >
                    <Brain size={8} />
                    {req}
                  </span>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
