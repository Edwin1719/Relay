import { useState, useRef, useCallback, useEffect } from 'react'
import {
  initAuth,
  chatFetch,
  fetchStatus,
  fetchModels,
  selectModel,
  fetchMCPStatus,
  setWorkspace,
  resetSession,
  fetchSessionHistory,
  type SSEEvent,
  type StatusInfo,
  type ModelInfo,
  type MCPServerStatus,
} from '../api/client'
import type { AttachedFile } from '../components/ChatPanel'

export interface ToolStep {
  name: string
  args: Record<string, unknown>
  result?: string
  awaitingApproval?: boolean
  approvalDiff?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  toolSteps?: ToolStep[]
  timestamp: Date
  attachments?: AttachedFile[]
}

function formatAttachedFiles(files: AttachedFile[]): { text: string; images: string[] } {
  const images: string[] = []
  const parts = files.map((f) => {
    if (f.type === 'image') {
      // Strip data URL prefix (e.g. "data:image/jpeg;base64,") — Ollama expects raw base64
      const b64 = f.content.replace(/^data:image\/\w+;base64,/, '')
      images.push(b64)
      return [
        `---`,
        `[Imagen adjunta: ${f.name}]`,
        `---`,
      ].join('\n')
    }
    return [
      `---`,
      `[Archivo adjunto: ${f.name}]`,
      `\`\`\``,
      f.content,
      `\`\`\``,
      `---`,
    ].join('\n')
  })
  return { text: parts.join('\n\n'), images }
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'system-welcome',
      role: 'system',
      content: 'Relay conectado. Envía un mensaje para empezar.',
      timestamp: new Date(),
    },
  ])
  const [streaming, setStreaming] = useState(false)
  const [status, setStatus] = useState<StatusInfo | null>(null)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [activeModel, setActiveModel] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [mcpServers, setMcpServers] = useState<MCPServerStatus[]>([])
  const [projectLoaded, setProjectLoaded] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [stuckWarning, setStuckWarning] = useState<string | null>(null)
  const [backgroundTasks, setBackgroundTasks] = useState(0)

  const stoppedRef = useRef(false)
  const lastChunkTimeRef = useRef<number>(0)

  const resetProject = useCallback(() => {
    setProjectLoaded(false)
  }, [])

  const loadStatus = useCallback(async () => {
    try {
      const s = await fetchStatus()
      setStatus(s)
      if (s.model) setActiveModel(s.model)
      if (s.mcp_servers) setMcpServers(s.mcp_servers)
      if (s.current_session_id) setCurrentSessionId(s.current_session_id)
    } catch {
      // Backend might not be ready yet
    }
  }, [])

  const loadMCPStatus = useCallback(async () => {
    try {
      const { servers } = await fetchMCPStatus()
      setMcpServers(servers)
    } catch {
      // ignore
    }
  }, [])

  const loadModels = useCallback(async () => {
    try {
      const m = await fetchModels()
      setModels(m)
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    initAuth()  // fetch auth token before API calls
    loadStatus()
    loadModels()
    loadMCPStatus()
    const interval = setInterval(() => {
      loadStatus()
      loadModels()
      loadMCPStatus()
    }, 10000)
    return () => clearInterval(interval)
  }, [loadStatus, loadModels, loadMCPStatus])

  const handleSwitchModel = useCallback(async (name: string) => {
    try {
      setError(null)
      await selectModel(name)
      setActiveModel(name)
      setMessages((prev) => [
        ...prev,
        {
          id: `system-model-${Date.now()}`,
          role: 'system',
          content: `Modelo cambiado a ${name}`,
          timestamp: new Date(),
        },
      ])
      await loadStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error switching model')
    }
  }, [loadStatus])

  const handleSetWorkspace = useCallback(async (path: string) => {
    try {
      setError(null)
      const result = await setWorkspace(path)
      setMessages((prev) => [
        ...prev,
        {
          id: `system-workspace-${Date.now()}`,
          role: 'system',
          content: `Workspace cambiado a: ${result.root}`,
          timestamp: new Date(),
        },
      ])
      setProjectLoaded(true)
      await loadStatus()
      return result
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error setting workspace')
      throw err
    }
  }, [loadStatus])

  const sendMessage = useCallback(async (content: string, files?: AttachedFile[]) => {
    setError(null)
    setStuckWarning(null)
    stoppedRef.current = false
    lastChunkTimeRef.current = Date.now()

    // Build the user message with file context
    let fullContent = content
    const hasFiles = files && files.length > 0
    const textFiles = files?.filter((f) => f.type === 'text') || []

    let imageB64: string[] = []
    if (hasFiles) {
      const { text: fileContext, images } = formatAttachedFiles(files!)
      imageB64 = images
      fullContent = content
        ? `${fileContext}\n\n${content}`
        : `${fileContext}\n\nAnaliza este${textFiles.length > 1 ? 'os archivos' : ' archivo'} adjunto${textFiles.length > 1 ? 's' : ''}.`
    }

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: fullContent,
      timestamp: new Date(),
      attachments: hasFiles ? files : undefined,
    }
    setMessages((prev) => [...prev, userMsg])
    setStreaming(true)

    const assistantId = `assistant-${Date.now()}`
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      toolSteps: [],
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, assistantMsg])

    let currentToolSteps: ToolStep[] = []

    // ── Debounce: buffer model_response chunks, flush every 50ms ──
    let chunkBuffer = ''
    let flushTimer: ReturnType<typeof setTimeout> | null = null

    const flushChunks = () => {
      if (!chunkBuffer) return
      const chunk = chunkBuffer
      chunkBuffer = ''
      flushTimer = null
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, content: (m.content || '') + chunk } : m
        )
      )
    }

    try {
      for await (const event of chatFetch(fullContent, imageB64.length > 0 ? imageB64 : undefined)) {
        switch (event.type) {
          case 'start':
            break

          case 'background_start': {
            setBackgroundTasks(n => n + 1)
            break
          }

          case 'background_result': {
            setBackgroundTasks(n => Math.max(0, n - 1))
            break
          }

          case 'plan': {
            const { steps, checklist } = event.data as {
              steps: string
              checklist?: { text: string; done: boolean }[]
            }
            // Show plan as a pseudo-tool-step with the plan text as result
            // so it appears with a green checkmark (hasResult = true) instead of a spinner
            currentToolSteps = [{ name: '📋 Plan', args: { steps, checklist }, result: steps }]
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, toolSteps: [...currentToolSteps] } : m
              )
            )
            break
          }

          case 'model_response': {
            const data = event.data as { chunk?: string }
            if (data.chunk) {
              lastChunkTimeRef.current = Date.now()
              chunkBuffer += data.chunk
              if (!flushTimer) {
                flushTimer = setTimeout(flushChunks, 50)
              }
            }
            break
          }

          case 'tool_call': {
            const { name, args } = event.data as { name: string; args: Record<string, unknown> }
            currentToolSteps = [...currentToolSteps, { name, args }]
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, toolSteps: [...currentToolSteps] } : m
              )
            )
            break
          }

          case 'approval_required': {
            const { tool, diff } = event.data as { tool: string; diff?: string }
            currentToolSteps = currentToolSteps.map((s, i) =>
              i === currentToolSteps.length - 1 && s.name === tool
                ? { ...s, awaitingApproval: true, approvalDiff: diff }
                : s
            )
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, toolSteps: [...currentToolSteps] } : m
              )
            )
            break
          }

          case 'tool_result': {
            const { name, result } = event.data as { name: string; result: string }
            currentToolSteps = currentToolSteps.map((step) =>
              step.name === name && !step.result ? { ...step, result } : step
            )
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, toolSteps: [...currentToolSteps] } : m
              )
            )
            break
          }

          case 'final': {
            // Flush any buffered chunks before applying final content
            if (flushTimer) {
              clearTimeout(flushTimer)
              flushTimer = null
            }
            const pending = chunkBuffer
            chunkBuffer = ''
            const { content: finalContent } = event.data as { content: string }
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: (m.content || '') + pending + (finalContent as string) }
                  : m
              )
            )
            break
          }

          case 'error': {
            const { message } = event.data as { message: string }
            setError(message)
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: `Error: ${message}` } : m
              )
            )
            break
          }
        }
      }
    } catch (err) {
      // If user clicked "Stop", don't show the abort as an error
      if (stoppedRef.current) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && !m.content && (!m.toolSteps || m.toolSteps.length === 0)
              ? { ...m, content: 'Agente detenido por el usuario.' }
              : m
          )
        )
      } else {
        const msg = err instanceof Error ? err.message : 'Unknown error'
        setError(msg)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: `Error: ${msg}` } : m
          )
        )
      }
    } finally {
      // Flush any remaining buffered chunks before marking stream complete
      if (flushTimer) {
        clearTimeout(flushTimer)
        flushTimer = null
      }
      if (chunkBuffer) {
        const chunk = chunkBuffer
        chunkBuffer = ''
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: (m.content || '') + chunk } : m
          )
        )
      }
      setStreaming(false)
    }
  }, [])

  const stopAgent = useCallback(async () => {
    stoppedRef.current = true
    setStuckWarning(null)
    // Fire-and-forget: kill the backend agent loop
    try {
      await resetSession()
    } catch {
      // ignore — the SSE connection abort will take care of it
    }
    setStreaming(false)
  }, [])

  // ── Stuck detection: warn if no content for 60s during streaming ──
  useEffect(() => {
    if (!streaming) {
      setStuckWarning(null)
      return
    }
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastChunkTimeRef.current
      if (elapsed > 60000) {
        setStuckWarning(
          'El agente parece estar atascado. Puedes detenerlo con el botón "Detener".'
        )
      }
    }, 5000)
    return () => clearInterval(interval)
  }, [streaming])

  const clearChat = useCallback(() => {
    setMessages([
      {
        id: 'system-welcome',
        role: 'system',
        content: 'Chat reiniciado. Envía un mensaje para empezar.',
        timestamp: new Date(),
      },
    ])
    setError(null)
  }, [])

  // True when there are real user/assistant messages but no active session
  const hasUnsavedMessages = !currentSessionId && messages.length > 1

  const restoreSession = useCallback(async () => {
    setError(null)

    // Check whether the switched session has a real workspace.
    // Chat-only sessions (saved via the "+" dialog) have no workspace,
    // so the file explorer should remain in "select a folder" state.
    let hasWorkspace = false
    try {
      const s = await fetchStatus()
      setStatus(s)
      if (s.model) setActiveModel(s.model)
      if (s.mcp_servers) setMcpServers(s.mcp_servers)
      setCurrentSessionId(s.current_session_id ?? null)
      hasWorkspace = !!s.session_workspace
    } catch {
      // If status fetch fails, keep default values
    }

    if (hasWorkspace) {
      setProjectLoaded(true)
    } else {
      setProjectLoaded(false)
    }

    // Try to restore chat history from the backend
    try {
      const historyMsgs = await fetchSessionHistory()
      if (historyMsgs.length > 0) {
        const restored: Message[] = historyMsgs.map((m) => ({
          id: m.id,
          role: m.role as Message['role'],
          content: m.content,
          timestamp: new Date(m.timestamp || Date.now()),
        }))
        // Prepend a system message indicating restoration
        setMessages([
          {
            id: 'system-restored',
            role: 'system',
            content: `Sesion restaurada (${restored.length} mensajes).`,
            timestamp: new Date(),
          },
          ...restored,
        ])
      } else {
        clearChat()
      }
    } catch {
      // If history fetch fails, fall back to empty chat
      clearChat()
    }
  }, [clearChat])

  return {
    messages,
    hasUnsavedMessages,
    streaming,
    status,
    models,
    activeModel,
    mcpServers,
    error,
    stuckWarning,
    currentSessionId,
    backgroundTasks,
    sendMessage,
    stopAgent,
    clearChat,
    loadStatus,
    loadModels,
    switchModel: handleSwitchModel,
    setWorkspace: handleSetWorkspace,
    restoreSession,
    projectLoaded,
    resetProject,
  }
}
