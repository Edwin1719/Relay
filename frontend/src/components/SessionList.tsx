import { useState, useEffect, useCallback } from 'react'
import {
  Plus, History, Clock, Folder, Trash2, MessageSquare, Cpu, Globe, ChevronRight,
  Zap, Brain,
} from 'lucide-react'
import { twMerge } from 'tailwind-merge'
import {
  fetchSessions, createSession, deleteSession, switchSession,
  type SessionInfo,
} from '../api/client'

interface SessionListProps {
  currentSessionId?: string | null
  hasUnsavedMessages?: boolean
  onSessionSwitch?: (session: SessionInfo) => void
  onSessionCreated?: (session: SessionInfo) => void
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'ahora'
  if (mins < 60) return `hace ${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `hace ${hrs}h`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `hace ${days}d`
  return new Date(iso).toLocaleDateString()
}

const PROVIDER_ICONS: Record<string, typeof Cpu> = {
  ollama: Zap,
  deepseek: Globe,
  apinex: Brain,
}

export function SessionList({ currentSessionId, hasUnsavedMessages, onSessionSwitch, onSessionCreated }: SessionListProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [saveName, setSaveName] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const list = await fetchSessions()
      setSessions(list)
    } catch {
      console.warn('SessionList: operation failed')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleCreate = async () => {
    if (creating) return

    // If there are unsaved messages, ask for a session name first
    if (hasUnsavedMessages) {
      setSaveName('')
      setShowSaveDialog(true)
      return
    }

    setCreating(true)
    try {
      const session = await createSession()
      setSessions((prev) => [session, ...prev])
      onSessionCreated?.(session)
    } catch {
      console.warn('SessionList: operation failed')
    } finally {
      setCreating(false)
    }
  }

  const handleSaveWithName = async () => {
    setShowSaveDialog(false)
    setCreating(true)
    try {
      const name = saveName.trim() || `Sesión ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
      // Passing a name preserves the current agent's conversation history
      const session = await createSession({ name })
      setSessions((prev) => [session, ...prev])
      onSessionCreated?.(session)
    } catch {
      console.warn('SessionList: operation failed')
    } finally {
      setCreating(false)
    }
  }

  const handleSwitch = async (session: SessionInfo) => {
    if (session.id === currentSessionId) return
    try {
      await switchSession(session.id)
      onSessionSwitch?.(session)
    } catch {
      console.warn('SessionList: failed to switch session')
    }
  }

  const handleDelete = async (id: string) => {
    setDeletingId(id)
    try {
      await deleteSession(id)
      setSessions((prev) => prev.filter((s) => s.id !== id))
    } catch {
      console.warn('SessionList: operation failed')
    } finally {
      setDeletingId(null)
      setShowDeleteConfirm(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-bg-border bg-bg-surface/50">
        <div className="flex items-center gap-2">
          <History size={15} className="text-fg-muted" />
          <span className="text-xs font-semibold text-fg-muted uppercase tracking-wider">Sesiones</span>
        </div>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="btn-ghost p-1.5 text-fg-dim hover:text-accent transition-colors"
          title="Nueva sesión"
        >
          <Plus size={15} />
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-1">
        {loading && sessions.length === 0 ? (
          <div className="text-sm text-fg-dim text-center py-8">Cargando...</div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 px-6 text-center">
            <History size={28} className="text-fg-dim/30 mb-3" />
            <p className="text-sm text-fg-muted mb-1">Sin sesiones</p>
            <p className="text-xs text-fg-dim leading-relaxed">
              Crea una nueva sesión para empezar a trabajar.
            </p>
          </div>
        ) : (
          <div className="space-y-0.5 px-1">
            {sessions.map((session) => {
              const isActive = session.id === currentSessionId
              const ProviderIcon = PROVIDER_ICONS[session.provider] || Cpu
              const folderName = session.workspace
                ? session.workspace.split(/[/\\]/).pop() || session.workspace
                : '(sin proyecto)'

              return (
                <div key={session.id} className="relative group">
                  <button
                    onClick={() => handleSwitch(session)}
                    className={twMerge(
                      'w-full text-left px-3 py-2.5 rounded-md transition-all text-sm',
                      isActive
                        ? 'bg-accent-muted/15 border border-accent-muted/30 text-accent'
                        : 'hover:bg-bg-hover border border-transparent text-fg-muted hover:text-fg'
                    )}
                  >
                    {/* Top row: name + timestamp */}
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="flex items-center gap-1.5 min-w-0 overflow-hidden">
                        <MessageSquare size={12} className="flex-shrink-0 text-fg-dim" />
                        <span className="font-medium truncate">{session.name}</span>
                      </div>
                      <span className="text-[10px] text-fg-dim whitespace-nowrap flex-shrink-0">
                        {timeAgo(session.updated_at)}
                      </span>
                    </div>

                    {/* Bottom row: workspace + model */}
                    <div className="flex items-center gap-2 text-[11px] text-fg-dim">
                      <span className="flex items-center gap-1 min-w-0 overflow-hidden">
                        <Folder size={10} className="flex-shrink-0" />
                        <span className="truncate">{folderName}</span>
                      </span>
                      {session.model && (
                        <>
                          <span>·</span>
                          <span className="flex items-center gap-1 flex-shrink-0">
                            <ProviderIcon size={10} />
                            {session.model}
                          </span>
                        </>
                      )}
                      {session.message_count > 0 && (
                        <>
                          <span>·</span>
                          <span>{session.message_count} msgs</span>
                        </>
                      )}
                    </div>

                    {/* Last message preview */}
                    {session.last_message && (
                      <p className="text-[11px] text-fg-dim/60 mt-1 truncate">
                        {session.last_message}
                      </p>
                    )}
                  </button>

                  {/* Delete button (visible on hover) */}
                  {!isActive && (
                    <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      {showDeleteConfirm === session.id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDelete(session.id) }}
                            disabled={deletingId === session.id}
                            className="px-2 py-0.5 rounded text-[10px] font-medium bg-danger/20 text-danger hover:bg-danger/30 transition-colors"
                          >
                            {deletingId === session.id ? '...' : 'Eliminar'}
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(null) }}
                            className="px-2 py-0.5 rounded text-[10px] text-fg-dim hover:text-fg transition-colors"
                          >
                            Cancelar
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(session.id) }}
                          className="p-1 rounded text-fg-dim hover:text-danger hover:bg-danger/10 transition-colors"
                          title="Eliminar sesión"
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Save dialog — shown when "+" is clicked with unsaved messages */}
      {showSaveDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setShowSaveDialog(false)}
        >
          <div
            className="bg-bg-surface border border-bg-border rounded-lg shadow-xl p-5 w-80"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-semibold text-fg mb-1">Guardar conversación</h3>
            <p className="text-xs text-fg-muted mb-3">
              Tienes mensajes sin guardar. Asígnale un nombre a la sesión para conservarlos.
            </p>
            <input
              autoFocus
              type="text"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSaveWithName() }}
              placeholder="Nombre de la sesión..."
              className="w-full px-3 py-2 rounded-md border border-bg-border bg-bg-base text-sm text-fg placeholder:text-fg-dim/50 outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 mb-3"
            />
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setShowSaveDialog(false)}
                className="px-3 py-1.5 rounded text-xs text-fg-muted hover:text-fg hover:bg-bg-hover transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleSaveWithName}
                disabled={creating}
                className="px-3 py-1.5 rounded text-xs font-medium bg-accent text-white hover:bg-accent/90 transition-colors disabled:opacity-50"
              >
                {creating ? 'Guardando...' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
