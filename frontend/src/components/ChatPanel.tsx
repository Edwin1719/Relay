import { useState, useRef, useEffect } from 'react'
import { Send, Trash2, Terminal, Paperclip, X, File, Image, Square, AlertTriangle } from 'lucide-react'
import { MessageBubble } from './MessageBubble'
import type { Message } from '../hooks/useChat'

// ── Types ────────────────────────────────────────────────────

export interface AttachedFile {
  name: string
  content: string
  type: 'text' | 'image'
}

interface ChatPanelProps {
  messages: Message[]
  streaming: boolean
  error: string | null
  stuckWarning: string | null
  onSend: (message: string, files?: AttachedFile[]) => void
  onClear: () => void
  onStop: () => void
  prefilledInput?: string
  onPrefillClear?: () => void
}

const ACCEPTED_TEXT_EXTENSIONS =
  '.txt,.py,.pyw,.js,.jsx,.ts,.tsx,.html,.css,.scss,.json,.xml,.yaml,.yml,.toml,.md,.csv,.sh,.bat,.ps1,.c,.cpp,.h,.hpp,.cs,.java,.rs,.go,.rb,.php,.swift,.kt,.dart,.lua,.r,.sql,.graphql,.env,.gitignore,.dockerfile,.cfg,.ini,.conf,.log,.env.example'

const ACCEPTED_IMAGE_EXTENSIONS = '.png,.jpg,.jpeg,.gif,.webp,.svg'

export function ChatPanel({
  messages,
  streaming,
  error,
  stuckWarning,
  onSend,
  onClear,
  onStop,
  prefilledInput,
  onPrefillClear,
}: ChatPanelProps) {
  const [input, setInput] = useState('')
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])
  const [dragOver, setDragOver] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Prefill input on prop change
  useEffect(() => {
    if (prefilledInput) {
      setInput(prefilledInput)
      // Focus the textarea and set cursor at the end
      if (inputRef.current) {
        inputRef.current.focus()
        inputRef.current.selectionStart = prefilledInput.length
        inputRef.current.selectionEnd = prefilledInput.length
      }
      onPrefillClear?.()
    }
  }, [prefilledInput, onPrefillClear])

  const handleSend = () => {
    const trimmed = input.trim()
    if ((!trimmed && attachedFiles.length === 0) || streaming) return
    setInput('')
    const files = [...attachedFiles]
    setAttachedFiles([])
    onSend(trimmed, files)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ── File attachment helpers ────────────────────────────────

  const readFileAsText = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = () => reject(new Error(`Error reading ${file.name}`))
      reader.readAsText(file)
    })
  }

  const handleFilePick = async (accept: string, type: 'text' | 'image') => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = accept
    input.multiple = true

    input.onchange = async () => {
      if (!input.files?.length) return
      const newFiles: AttachedFile[] = []

      for (const file of Array.from(input.files)) {
        if (type === 'image') {
          // For images, store as base64 data URL
          const dataUrl = await new Promise<string>((resolve) => {
            const r = new FileReader()
            r.onload = () => resolve(r.result as string)
            r.readAsDataURL(file)
          })
          newFiles.push({ name: file.name, content: dataUrl, type: 'image' })
        } else {
          const content = await readFileAsText(file)
          newFiles.push({ name: file.name, content, type: 'text' })
        }
      }

      setAttachedFiles((prev) => [...prev, ...newFiles])
    }

    input.click()
  }

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index))
  }

  // ── Drag & drop ───────────────────────────────────────────

  const processDroppedFiles = async (files: FileList) => {
    const newFiles: AttachedFile[] = []
    for (const file of Array.from(files)) {
      if (file.type.startsWith('image/')) {
        const dataUrl = await new Promise<string>((resolve) => {
          const r = new FileReader()
          r.onload = () => resolve(r.result as string)
          r.readAsDataURL(file)
        })
        newFiles.push({ name: file.name, content: dataUrl, type: 'image' })
      } else {
        const content = await readFileAsText(file)
        newFiles.push({ name: file.name, content, type: 'text' })
      }
    }
    setAttachedFiles((prev) => [...prev, ...newFiles])
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) {
      await processDroppedFiles(e.dataTransfer.files)
    }
  }

  const hasAttachments = attachedFiles.length > 0

  return (
    <div
      className="flex flex-col h-full relative"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {dragOver && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-accent/10 border-2 border-accent border-dashed rounded-lg pointer-events-none">
          <div className="flex flex-col items-center gap-2 text-accent">
            <Image size={40} strokeWidth={1.5} />
            <span className="text-sm font-semibold">Suelta archivos aquí</span>
          </div>
        </div>
      )}
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-bg-border bg-bg-surface/50">
        <div className="flex items-center gap-2.5">
          <Terminal size={18} className="text-accent" />
          <span className="text-base font-semibold text-fg">Chat</span>
          {hasAttachments && (
            <span className="text-xs text-fg-muted bg-bg-hover rounded-full px-2 py-0.5">
              {attachedFiles.length} adjunto{attachedFiles.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <button
          onClick={onClear}
          className="btn-ghost p-1.5"
          title="Limpiar chat"
        >
          <Trash2 size={16} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {/* Error banner */}
        {error && (
          <div className="mx-3 mt-2 flex items-start gap-2.5 px-3 py-2.5 rounded-md bg-danger/10 border border-danger/30 text-sm">
            <AlertTriangle size={16} className="text-danger flex-shrink-0 mt-0.5" />
            <span className="text-fg flex-1">{error}</span>
            <button
              onClick={() => onClear()}
              className="btn-ghost p-0.5 rounded flex-shrink-0 text-fg-muted hover:text-fg"
              title="Cerrar"
            >
              <X size={14} />
            </button>
          </div>
        )}

        {/* Stuck warning */}
        {stuckWarning && (
          <div className="mx-3 mt-2 flex items-start gap-2.5 px-3 py-2.5 rounded-md bg-warning/10 border border-warning/30 text-sm">
            <AlertTriangle size={16} className="text-warning flex-shrink-0 mt-0.5" />
            <span className="text-fg flex-1">{stuckWarning}</span>
            <button
              onClick={onStop}
              className="btn-primary px-3 py-1 rounded-md text-xs flex-shrink-0 bg-danger/80 hover:bg-danger"
            >
              Detener
            </button>
          </div>
        )}

        {messages.length === 1 && messages[0].id === 'system-welcome' ? (
          /* Welcome card — shown when chat is fresh */
          <div className="flex flex-col items-center justify-center h-full px-8 text-center">
            {/* Glow ring */}
            <div className="relative mb-8">
              <div className="absolute inset-0 rounded-full bg-accent/20 blur-2xl scale-150" />
              <div className="relative w-20 h-20 rounded-2xl bg-gradient-to-br from-accent to-accent-muted flex items-center justify-center shadow-lg shadow-accent/25 ring-1 ring-white/10">
                <Terminal size={34} className="text-white" />
              </div>
            </div>

            <h1 className="text-3xl font-black text-fg tracking-tight mb-3">
              Relay listo
            </h1>

            <p className="text-base text-fg-muted max-w-sm leading-relaxed mb-6">
              Soy tu asistente personal de IA. Planifico, uso herramientas en tu
              proyecto y te pido permiso antes de escribir o ejecutar.
            </p>

            <div className="flex flex-wrap justify-center gap-2.5">
              {[
                ['Buscar en internet', 'text-blue-300 bg-blue-500/10 border-blue-500/20'],
                ['Leer y editar archivos', 'text-emerald-300 bg-emerald-500/10 border-emerald-500/20'],
                ['Crear codigo', 'text-purple-300 bg-purple-500/10 border-purple-500/20'],
                ['Automatizar tareas', 'text-amber-300 bg-amber-500/10 border-amber-500/20'],
              ].map(([label, color]) => (
                <span key={label} className={`px-3 py-1.5 rounded-lg text-sm font-medium border ${color}`}>
                  {label}
                </span>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isLatestAssistant={
                msg.role === 'assistant' && i === messages.length - 1
              }
            />
          ))
        )}
        {streaming && messages[messages.length - 1]?.role === 'assistant' &&
          !messages[messages.length - 1]?.content &&
          !messages[messages.length - 1]?.toolSteps?.length && (
            <div className="flex gap-3 px-4 py-3">
              <div className="w-8 h-8 rounded-full bg-accent-muted/20 border border-accent-muted/30 flex items-center justify-center">
                <BotIndicator />
              </div>
              <div className="bg-bg-surface border border-bg-border rounded-lg px-4 py-3">
                <div className="flex gap-1">
                  <span className="w-2 h-2 rounded-full bg-fg-muted animate-pulse-dot" />
                  <span className="w-2 h-2 rounded-full bg-fg-muted animate-pulse-dot" style={{ animationDelay: '0.2s' }} />
                  <span className="w-2 h-2 rounded-full bg-fg-muted animate-pulse-dot" style={{ animationDelay: '0.4s' }} />
                </div>
              </div>
            </div>
          )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-bg-border p-3">
        {/* Attached files chips */}
        {hasAttachments && (
          <div className="flex flex-wrap gap-1.5 mb-2 px-1">
            {attachedFiles.map((file, i) => (
              <div
                key={`${file.name}-${i}`}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs bg-accent-muted/15 border border-accent-muted/30 text-accent group"
              >
                {file.type === 'image' ? (
                  <Image size={12} className="flex-shrink-0" />
                ) : (
                  <File size={12} className="flex-shrink-0" />
                )}
                <span className="truncate max-w-[140px]">{file.name}</span>
                <button
                  onClick={() => removeFile(i)}
                  className="ml-0.5 p-0.5 rounded hover:bg-accent-muted/30 transition-colors opacity-60 group-hover:opacity-100"
                >
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Textarea + toolbar */}
        <div className="flex items-end gap-2 panel px-3 py-2">
          <div className="flex flex-col flex-1 min-w-0">
            {/* Toolbar */}
            <div className="flex items-center gap-0.5 pb-1.5 border-b border-bg-border/50 mb-1.5">
              <button
                onClick={() => handleFilePick(ACCEPTED_TEXT_EXTENSIONS, 'text')}
                className="btn-ghost p-1 rounded text-fg-dim hover:text-accent transition-colors"
                title="Adjuntar archivo"
              >
                <Paperclip size={14} />
              </button>
              <button
                onClick={() => handleFilePick(ACCEPTED_IMAGE_EXTENSIONS, 'image')}
                className="btn-ghost p-1 rounded text-fg-dim hover:text-accent transition-colors"
                title="Adjuntar imagen"
              >
                <Image size={14} />
              </button>
              <span className="flex-1" />
              <span className="text-xs text-fg-dim/60">
                {streaming ? 'Procesando...' : 'Ctrl+Enter'}
              </span>
            </div>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                hasAttachments
                  ? 'Describe qué quieres hacer con los archivos adjuntos...'
                  : 'Envía un mensaje al agente...'
              }
              rows={2}
              className="w-full bg-transparent text-base text-fg placeholder:text-fg-dim resize-none outline-none py-0.5 max-h-40"
              disabled={streaming}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={(!input.trim() && attachedFiles.length === 0) || streaming}
            className="btn-primary p-2 flex-shrink-0 self-end"
            title="Enviar"
          >
            <Send size={16} />
          </button>
          {streaming && (
            <button
              onClick={onStop}
              className="btn-primary p-2 flex-shrink-0 self-end bg-danger/80 hover:bg-danger"
              title="Detener agente"
            >
              <Square size={16} />
            </button>
          )}
        </div>
        <p className="text-sm text-fg-dim mt-1.5 px-1">
          Enter para enviar · Shift+Enter para nueva línea · {hasAttachments ? `📎 ${attachedFiles.length} archivo(s) adjunto(s)` : '📎 Adjunta archivos con el botón'}
        </p>
      </div>
    </div>
  )
}

function BotIndicator() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-accent">
      <rect x="3" y="11" width="18" height="10" rx="2" />
      <circle cx="12" cy="16" r="2" />
      <path d="M9 11V7a3 3 0 0 1 6 0v4" />
    </svg>
  )
}
