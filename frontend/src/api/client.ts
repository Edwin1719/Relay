const API_BASE = '/api'

// ── Auth token ───────────────────────────────────────────────────
let AUTH_TOKEN: string | null = null

export async function initAuth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth-token`)
    if (!res.ok) return false
    const data = await res.json()
    if (data.auth_enabled && data.token) {
      AUTH_TOKEN = data.token
      return true
    }
    return false
  } catch {
    return false
  }
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (AUTH_TOKEN) {
    headers['Authorization'] = `Bearer ${AUTH_TOKEN}`
  }
  return headers
}

function authHeadersNoContent(): Record<string, string> {
  const headers: Record<string, string> = {}
  if (AUTH_TOKEN) {
    headers['Authorization'] = `Bearer ${AUTH_TOKEN}`
  }
  return headers
}

function authHeadersGet(): Record<string, string> {
  return authHeadersNoContent()
}

export interface StatusInfo {
  session_id: string
  current_session_id: string | null
  workspace: string
  session_workspace: string | null
  branch: string
  model: string
  provider: string
  approval: string
  max_steps: number
  mcp_available: boolean
  mcp_servers: MCPServerStatus[]
  version: string
}

export interface MCPServerStatus {
  server: string
  status: 'connected' | 'error' | 'disconnected' | 'broken'
  tools?: { name: string; description: string }[]
  error?: string
  consecutive_failures?: number
  broken?: boolean
  last_error?: string
}

export interface FileEntry {
  name: string
  path: string
  type: 'file' | 'dir'
}

export interface WorkspaceInfo {
  root: string
  cwd: string
  branch: string
  status: string
}

export interface SSEEvent {
  type: 'start' | 'plan' | 'model_response' | 'tool_call' | 'tool_result' | 'final' | 'error' | 'approval_required' | 'background_start' | 'background_result'
  data: Record<string, unknown>
}

export async function fetchStatus(): Promise<StatusInfo> {
  const res = await fetch(`${API_BASE}/status`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`status: ${res.status}`)
  return res.json()
}

export async function fetchWorkspace(): Promise<WorkspaceInfo> {
  const res = await fetch(`${API_BASE}/workspace`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`workspace: ${res.status}`)
  return res.json()
}

export async function fetchFiles(path = '.'): Promise<{ path: string; entries: FileEntry[] }> {
  const res = await fetch(`${API_BASE}/workspace/files?path=${encodeURIComponent(path)}`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`files: ${res.status}`)
  return res.json()
}

export async function readFile(path: string): Promise<{ path: string; content: string }> {
  const res = await fetch(`${API_BASE}/workspace/read?path=${encodeURIComponent(path)}`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`read: ${res.status}`)
  return res.json()
}

export async function setWorkspace(path: string): Promise<{ status: string; root: string; branch: string }> {
  const res = await fetch(`${API_BASE}/workspace/set`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ path }),
  })
  if (!res.ok) {
    if (res.status === 409) {
      throw new Error('No puedes cambiar de workspace mientras el agente responde.')
    }
    const err = await res.text()
    throw new Error(err || `workspace set: ${res.status}`)
  }
  return res.json()
}

export async function resetSession(): Promise<void> {
  await fetch(`${API_BASE}/reset`, { method: 'POST', headers: authHeadersNoContent() })
}

export type ModelTier = 'fast' | 'deep'

export interface ModelInfo {
  name: string
  /** Human-readable name from the provider, when it publishes one. */
  label: string
  provider: string
  provider_label: string
  /** ``fast`` = short/medium tasks (Ollama cloud); ``deep`` = multi-step agentic. */
  tier: ModelTier
  context_limit: number
  size: string
  modified: string
}

export interface ProviderInfo {
  name: string
  label: string
  backend: 'ollama' | 'openai'
  base_url: string
  /** Env var the key is stored under. Empty for keyless providers. */
  env_key: string
  requires_key: boolean
  configured: boolean
  docs_url: string
  tier: ModelTier
  models: string[]
}

export async function fetchModels(): Promise<ModelInfo[]> {
  const res = await fetch(`${API_BASE}/models`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`models: ${res.status}`)
  const data = await res.json()
  return data.models ?? []
}

export async function approveTool(approved: boolean): Promise<void> {
  const res = await fetch(`${API_BASE}/approve`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ approved }),
  })
  if (!res.ok) throw new Error(`approve: ${res.status}`)
}

export async function selectModel(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/models/select`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ name }),
  })
  if (res.status === 409) {
    throw new Error('No puedes cambiar de modelo mientras el agente responde.')
  }
  if (!res.ok) throw new Error(`select model: ${res.status}`)
}

export async function fetchProviders(): Promise<ProviderInfo[]> {
  const res = await fetch(`${API_BASE}/providers`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`providers: ${res.status}`)
  const data = await res.json()
  return data.providers ?? []
}

/**
 * Save (or clear, with an empty key) a provider credential.
 * Returns the freshly rebuilt model list.
 */
export async function configureProvider(name: string, apiKey: string): Promise<ModelInfo[]> {
  const res = await fetch(`${API_BASE}/providers/configure`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ name, api_key: apiKey }),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(detail || `configure provider: ${res.status}`)
  }
  const data = await res.json()
  return data.models ?? []
}

export async function fetchMCPStatus(): Promise<{ available: boolean; servers: MCPServerStatus[] }> {
  const res = await fetch(`${API_BASE}/mcp/status`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`mcp status: ${res.status}`)
  return res.json()
}

export async function reconnectMCP(): Promise<{ status: string; servers: MCPServerStatus[] }> {
  const res = await fetch(`${API_BASE}/mcp/reconnect`, { method: 'POST', headers: authHeadersNoContent() })
  if (!res.ok) throw new Error(`mcp reconnect: ${res.status}`)
  return res.json()
}

export async function resetMCPServer(serverName: string): Promise<{ status: string; server: string }> {
  const res = await fetch(`${API_BASE}/mcp/reset`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ server_name: serverName }),
  })
  if (!res.ok) throw new Error(`mcp reset: ${res.status}`)
  return res.json()
}

// ── Onboarding ───────────────────────────────────────────────────

export async function onboardingStatus(): Promise<boolean> {
  const res = await fetch(`${API_BASE}/onboarding/status`, { headers: authHeadersGet() })
  if (!res.ok) return true  // assume complete on error
  const data = await res.json()
  return data.completed === true
}

export async function onboardingComplete(): Promise<void> {
  await fetch(`${API_BASE}/onboarding/complete`, { method: 'POST', headers: authHeadersNoContent() })
}

export async function pickFolder(): Promise<{ path: string | null; canceled: boolean }> {
  const res = await fetch(`${API_BASE}/workspace/pick`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`pick folder: ${res.status}`)
  return res.json()
}

export async function fetchSessionHistory(): Promise<Array<{ id: string; role: string; content: string; timestamp: string }>> {
  const res = await fetch(`${API_BASE}/session/history`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`session history: ${res.status}`)
  const data = await res.json()
  return data.messages ?? []
}


// ── Session types & API ─────────────────────────────────────

export interface SessionInfo {
  id: string
  name: string
  workspace: string
  model: string
  provider: string
  last_message: string
  message_count: number
  created_at: string
  updated_at: string
}

export async function fetchSessions(): Promise<SessionInfo[]> {
  const res = await fetch(`${API_BASE}/sessions`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`sessions: ${res.status}`)
  const data = await res.json()
  return data.sessions ?? []
}

export async function createSession(opts?: { name?: string; workspace?: string; model?: string }): Promise<SessionInfo> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(opts ?? {}),
  })
  if (!res.ok) throw new Error(`create session: ${res.status}`)
  const data = await res.json()
  return data.session
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: authHeadersNoContent(),
  })
  if (!res.ok) throw new Error(`delete session: ${res.status}`)
}

export async function switchSession(sessionId: string): Promise<{ status: string; session: SessionInfo; workspace: string; model: string }> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/switch`, {
    method: 'POST',
    headers: authHeadersNoContent(),
  })
  if (!res.ok) throw new Error(`switch session: ${res.status}`)
  return res.json()
}

export async function* chatFetch(message: string, images?: string[]): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ message, images: images || [] }),
  })

  if (!res.ok) {
    if (res.status === 409) {
      throw new Error('Ya hay una respuesta en curso. Espera o pulsa Detener.')
    }
    throw new Error(`chat error: ${res.status}`)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || !trimmed.startsWith('data: ')) continue
      const payload = trimmed.slice(6)
      if (payload === '[DONE]') return
      try {
        const event = JSON.parse(payload) as SSEEvent
        yield event
      } catch {
        console.warn('Failed to parse SSE event:', payload)
      }
    }
  }
}


// ── Integrations / Marketplace ──────────────────────────────

export interface ConfigField {
  name: string
  label: string
  type: 'api_key' | 'string'
  env_var?: string
  required: boolean
  placeholder?: string
}

export interface CatalogIntegration {
  server_name: string
  display_name: string
  description: string
  tools_description: string
  config_fields: ConfigField[]
}

export interface IntegrationRecord {
  server_name: string
  enabled: boolean  // true if integration is active
  connected?: boolean  // true if MCP server is actually running
  error?: string  // last recorded connection failure (when not connected)
  tools?: { name: string; description: string }[]
  config: string   // JSON string
  updated_at: string
  // Enriched by API:
  display_name?: string
  description?: string
  tools_description?: string
  config_fields?: ConfigField[]
  preflight?: {
    command: string
    available: boolean
    path: string
    chrome_available?: boolean
    chrome_path?: string
  }
  [key: string]: unknown  // _has_* fields for API key presence
}

export interface IntegrationStatus {
  server: string
  status: 'connected' | 'error' | 'disabled'
  tools?: { name: string; description: string }[]
  error?: string
  config?: Record<string, unknown>
}

export async function fetchIntegrationsCatalog(): Promise<CatalogIntegration[]> {
  const res = await fetch(`${API_BASE}/integrations/catalog`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`integrations catalog: ${res.status}`)
  const data = await res.json()
  return data.catalog ?? []
}

export async function fetchIntegrations(): Promise<IntegrationRecord[]> {
  const res = await fetch(`${API_BASE}/integrations`, { headers: authHeadersGet() })
  if (!res.ok) throw new Error(`integrations: ${res.status}`)
  const data = await res.json()
  const records: IntegrationRecord[] = (data.integrations ?? []).map((r: Record<string, unknown>) => ({
    ...r,
    enabled: Boolean(r.enabled),
  })) as IntegrationRecord[]
  return records
}

export async function enableIntegration(
  serverName: string,
  apiKeys?: Record<string, string>,
  config?: Record<string, unknown>,
): Promise<IntegrationStatus> {
  const res = await fetch(`${API_BASE}/integrations/enable`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ server_name: serverName, api_keys: apiKeys ?? {}, config: config ?? {} }),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `enable integration: ${res.status}`)
  }
  return res.json()
}

export async function disableIntegration(serverName: string): Promise<IntegrationStatus> {
  const res = await fetch(`${API_BASE}/integrations/disable`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ server_name: serverName }),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `disable integration: ${res.status}`)
  }
  return res.json()
}

export async function configureIntegration(
  serverName: string,
  apiKeys?: Record<string, string>,
  config?: Record<string, unknown>,
): Promise<IntegrationStatus> {
  const res = await fetch(`${API_BASE}/integrations/configure`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ server_name: serverName, api_keys: apiKeys ?? {}, config: config ?? {} }),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `configure integration: ${res.status}`)
  }
  return res.json()
}
