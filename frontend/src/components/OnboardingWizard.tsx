import { useState, useEffect } from 'react'
import { Zap, Search, FolderPlus, Bot, MessageSquare, ArrowRight, Check, Cpu, Globe, Puzzle, Brain } from 'lucide-react'
import { onboardingStatus, onboardingComplete, type ModelInfo } from '../api/client'

type WizardStep = 1 | 2 | 3
type UserGoal = 'research' | 'create' | 'automate' | 'chat' | null

interface OnboardingWizardProps {
  models: ModelInfo[]
  activeModel: string
  onComplete: (suggestedPrompt?: string) => void
}

const GOALS = [
  {
    id: 'research' as const,
    icon: Search,
    title: 'Investigar',
    description: 'Buscar información, analizar datos, comparar opciones',
    color: 'bg-blue-900/30 text-blue-400 border-blue-800/40 hover:border-blue-600/60',
  },
  {
    id: 'create' as const,
    icon: FolderPlus,
    title: 'Crear proyecto',
    description: 'Generar código, crear apps, sitios web o scripts desde cero',
    color: 'bg-emerald-900/30 text-emerald-400 border-emerald-800/40 hover:border-emerald-600/60',
  },
  {
    id: 'automate' as const,
    icon: Bot,
    title: 'Automatizar tareas',
    description: 'Programar tareas, enviar correos, procesar archivos automáticamente',
    color: 'bg-purple-900/30 text-purple-400 border-purple-800/40 hover:border-purple-600/60',
  },
  {
    id: 'chat' as const,
    icon: MessageSquare,
    title: 'Chatear',
    description: 'Conversación libre, preguntas, brainstorming, asistencia general',
    color: 'bg-amber-900/30 text-amber-400 border-amber-800/40 hover:border-amber-600/60',
  },
]

const SUGGESTIONS: Record<string, string[]> = {
  research: [
    'Busca en internet las últimas noticias sobre inteligencia artificial',
    'Investiga y compárame React vs Vue para un proyecto nuevo',
    'Analiza el archivo README.md y dime de qué trata este proyecto',
  ],
  create: [
    'Crea un proyecto FastAPI con autenticación JWT',
    'Genera un componente React con un formulario de contacto',
    'Escribe un script en Python para procesar archivos CSV',
  ],
  automate: [
    'Configura una tarea para enviarme un resumen diario por correo',
    'Crea un script que organice mis archivos de descargas por tipo',
    'Procesa todos los archivos de la carpeta y genera un informe',
  ],
  chat: [
    '¿Qué puedes hacer por mí?',
    'Explícame cómo funciona Relay',
    'Ayúdame a entender la estructura de este proyecto',
  ],
}

export function OnboardingWizard({ models, activeModel, onComplete }: OnboardingWizardProps) {
  const [visible, setVisible] = useState(false)
  const [step, setStep] = useState<WizardStep>(1)
  const [goal, setGoal] = useState<UserGoal>(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    onboardingStatus().then((completed) => {
      if (!completed) {
        setVisible(true)
      }
      setChecking(false)
    })
  }, [])

  const handleGoalSelect = (g: UserGoal) => {
    setGoal(g)
    setStep(2)
  }

  const handleFinish = async () => {
    const prompts = goal ? SUGGESTIONS[goal] : SUGGESTIONS.chat
    const suggestion = prompts[Math.floor(Math.random() * prompts.length)]
    await onboardingComplete()
    setVisible(false)
    onComplete(suggestion)
  }

  const activeModelInfo = models.find((m) => m.name === activeModel)

  if (checking || !visible) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg mx-4 bg-bg-surface border border-bg-border rounded-xl shadow-2xl overflow-hidden">
        <div className="px-6 pt-6 pb-4 border-b border-bg-border">
          <div className="flex items-center gap-2.5 mb-3">
            <Zap size={22} className="text-accent" />
            <span className="text-lg font-bold tracking-tight">Relay</span>
          </div>
          <div className="flex items-center gap-2">
            {([1, 2, 3] as WizardStep[]).map((s) => (
              <div key={s} className="flex items-center gap-2">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                    step >= s
                      ? 'bg-accent text-white'
                      : 'bg-bg-hover text-fg-dim'
                  }`}
                >
                  {step > s ? <Check size={14} /> : s}
                </div>
                {s < 3 && (
                  <div
                    className={`w-8 h-0.5 rounded transition-colors ${
                      step > s ? 'bg-accent' : 'bg-bg-border'
                    }`}
                  />
                )}
              </div>
            ))}
            <span className="text-xs text-fg-dim ml-2">
              {step === 1 ? 'Objetivo' : step === 2 ? 'Configuración' : 'Empezar'}
            </span>
          </div>
        </div>

        <div className="px-6 py-5">
          {step === 1 && (
            <>
              <h2 className="text-base font-semibold text-fg mb-1">
                ¿Qué quieres hacer?
              </h2>
              <p className="text-sm text-fg-muted mb-4">
                Elige tu objetivo para que Relay se adapte a ti.
              </p>
              <div className="grid grid-cols-2 gap-2.5">
                {GOALS.map((g) => (
                  <button
                    key={g.id}
                    onClick={() => handleGoalSelect(g.id)}
                    className={`flex flex-col items-start gap-2 p-3.5 rounded-lg border text-left transition-all ${g.color}`}
                  >
                    <g.icon size={20} />
                    <div>
                      <div className="text-sm font-semibold">{g.title}</div>
                      <div className="text-xs opacity-70 mt-0.5 leading-tight">
                        {g.description}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <h2 className="text-base font-semibold text-fg mb-1">
                Esto es lo que tienes listo
              </h2>
              <p className="text-sm text-fg-muted mb-4">
                Relay detecta automáticamente lo que está disponible en tu sistema.
              </p>

              <div className="space-y-3">
                <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-hover/50 border border-bg-border">
                  {activeModelInfo?.tier === 'deep' ? (
                    <Globe size={18} className="text-purple-400" />
                  ) : (
                    <Cpu size={18} className="text-emerald-400" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-fg">
                      {activeModelInfo?.tier === 'deep' ? 'Motor avanzado' : 'Motor rápido'}
                    </div>
                    <div className="text-xs text-fg-muted truncate">
                      {activeModel || 'No detectado'}
                    </div>
                  </div>
                  <span className={`w-2 h-2 rounded-full ${activeModel ? 'bg-emerald-400' : 'bg-red-400'}`} />
                </div>

                <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-hover/50 border border-bg-border">
                  <Puzzle size={18} className="text-fg-muted" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-fg">
                      Herramientas web
                    </div>
                    <div className="text-xs text-fg-muted">
                      Búsqueda, navegación, extracción de contenido
                    </div>
                  </div>
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                </div>

                <div className="flex items-center gap-3 p-3 rounded-lg bg-bg-hover/50 border border-bg-border">
                  <Brain size={18} className="text-fg-muted" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-fg">
                      Capacidades activas
                    </div>
                    <div className="text-xs text-fg-muted">
                      Debug, revisión de código, testing, seguridad
                    </div>
                  </div>
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                </div>
              </div>

              <button
                onClick={() => setStep(3)}
                className="mt-5 w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-accent text-white rounded-lg text-sm font-semibold hover:bg-accent-hover transition-colors"
              >
                Continuar
                <ArrowRight size={16} />
              </button>
            </>
          )}

          {step === 3 && (
            <>
              <h2 className="text-base font-semibold text-fg mb-1">
                Todo listo
              </h2>
              <p className="text-sm text-fg-muted mb-4">
                {goal === 'research' && 'Relay buscará, analizará y te presentará la información que necesitas.'}
                {goal === 'create' && 'Relay generará código, creará proyectos y te ayudará a construir.'}
                {goal === 'automate' && 'Relay programará tareas, enviará correos y procesará datos por ti.'}
                {goal === 'chat' && 'Relay está listo para conversar, responder preguntas y ayudarte.'}
                {!goal && 'Relay está listo para lo que necesites.'}
              </p>

              <div className="p-4 rounded-lg bg-bg-hover/50 border border-bg-border mb-4">
                <div className="text-xs text-fg-dim mb-1.5 font-medium uppercase tracking-wide">
                  Sugerencia para empezar
                </div>
                <div className="text-sm text-fg leading-relaxed">
                  {goal ? SUGGESTIONS[goal][0] : SUGGESTIONS.chat[0]}
                </div>
              </div>

              <button
                onClick={handleFinish}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-accent text-white rounded-lg text-sm font-semibold hover:bg-accent-hover transition-colors"
              >
                <Zap size={16} />
                Comenzar
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
