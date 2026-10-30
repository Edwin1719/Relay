import { useState, useEffect, useRef, useCallback } from 'react'
import { Search, ArrowRight, Cpu, Globe, Trash2, Square, FileText, History, Puzzle, Brain, Play, HelpCircle, Settings, Zap } from 'lucide-react'
import type { ModelInfo } from '../api/client'

type SidebarTab = 'explorer' | 'sessions' | 'integrations' | 'skills' | 'auto' | 'help' | 'settings'

interface Command {
  id: string
  label: string
  desc: string
  icon: React.ReactNode
  action: () => void
}

interface Props {
  models: ModelInfo[]
  activeModel: string
  onNavigate: (tab: SidebarTab) => void
  onSwitchModel: (name: string) => void
  onClearChat: () => void
  onStopAgent: () => void
  onClose: () => void
}

const TAB_ICONS: Record<SidebarTab, React.ReactNode> = {
  explorer: <FileText size={14} />,
  sessions: <History size={14} />,
  integrations: <Puzzle size={14} />,
  skills: <Brain size={14} />,
  auto: <Play size={14} />,
  help: <HelpCircle size={14} />,
  settings: <Settings size={14} />,
}

const TAB_LABELS: Record<SidebarTab, string> = {
  explorer: 'Explorador',
  sessions: 'Sesiones',
  integrations: 'Integraciones',
  skills: 'Skills',
  auto: 'Automationes',
  help: 'Ayuda',
  settings: 'Configuración',
}

export function CommandPalette({ models, activeModel, onNavigate, onSwitchModel, onClearChat, onStopAgent, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const buildCommands = useCallback((): Command[] => {
    const cmds: Command[] = []

    // Navigation commands
    for (const tab of Object.keys(TAB_LABELS) as SidebarTab[]) {
      cmds.push({
        id: `nav-${tab}`,
        label: `> ${TAB_LABELS[tab]}`,
        desc: `Ir a ${TAB_LABELS[tab]}`,
        icon: TAB_ICONS[tab],
        action: () => onNavigate(tab),
      })
    }

    // Model commands
    for (const m of models) {
      cmds.push({
        id: `model-${m.name}`,
        label: `: ${m.name}`,
        desc: `Cambiar a ${m.name}`,
        icon: m.tier === 'deep' ? <Globe size={14} /> : <Zap size={14} />,
        action: () => onSwitchModel(m.name),
      })
    }

    // Action commands
    cmds.push({
      id: 'act-clear',
      label: '! clear',
      desc: 'Limpiar conversación',
      icon: <Trash2 size={14} />,
      action: () => { onClearChat(); onClose() },
    })
    cmds.push({
      id: 'act-stop',
      label: '! stop',
      desc: 'Detener agente',
      icon: <Square size={14} />,
      action: () => { onStopAgent(); onClose() },
    })

    return cmds
  }, [models, onNavigate, onSwitchModel, onClearChat, onStopAgent, onClose])

  const filtered = buildCommands().filter(cmd => {
    const q = query.toLowerCase()
    const prefix = q.slice(0, 1)
    const rest = q.slice(1).trim()
    // Only show commands whose label starts with the matching prefix
    if (prefix === '>') return cmd.label.startsWith('>') && (!rest || cmd.label.toLowerCase().includes(rest) || cmd.desc.toLowerCase().includes(rest))
    if (prefix === ':') return cmd.label.startsWith(':') && (!rest || cmd.label.toLowerCase().includes(rest))
    if (prefix === '!') return cmd.label.startsWith('!') && (!rest || cmd.label.toLowerCase().includes(rest))
    if (prefix === '/') return false
    return cmd.label.toLowerCase().includes(q) || cmd.desc.toLowerCase().includes(q)
  })

  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIndex(i => Math.min(i + 1, filtered.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIndex(i => Math.max(i - 1, 0)) }
    if (e.key === 'Enter') { if (filtered[selectedIndex]) filtered[selectedIndex].action(); onClose() }
    if (e.key === 'Escape') onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-md mx-4 bg-bg-surface border border-bg-border rounded-xl shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-bg-border">
          <Search size={16} className="text-fg-dim shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="> navegar · : modelo · ! accion"
            className="flex-1 bg-transparent text-sm text-fg placeholder:text-fg-dim outline-none"
          />
          <kbd className="text-[10px] text-fg-dim bg-bg-hover px-1.5 py-0.5 rounded font-mono">Esc</kbd>
        </div>

        {filtered.length > 0 && (
          <div className="max-h-64 overflow-y-auto py-1">
            {filtered.slice(0, 12).map((cmd, i) => (
              <button
                key={cmd.id}
                className={`w-full flex items-center gap-3 px-4 py-2 text-left transition-colors ${
                  i === selectedIndex ? 'bg-accent/10 text-fg' : 'text-fg-muted hover:bg-bg-hover'
                }`}
                onClick={() => { cmd.action(); onClose() }}
                onMouseEnter={() => setSelectedIndex(i)}
              >
                <span className="shrink-0">{cmd.icon}</span>
                <span className="flex-1 text-sm font-medium">{cmd.label}</span>
                <span className="text-xs text-fg-dim truncate max-w-[180px]">{cmd.desc}</span>
                {i === selectedIndex && <ArrowRight size={12} className="shrink-0 text-accent" />}
              </button>
            ))}
          </div>
        )}

        {query && filtered.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-fg-dim">
            Ningún comando coincide con <span className="font-mono text-fg-muted">{query}</span>
          </div>
        )}
      </div>
    </div>
  )
}
