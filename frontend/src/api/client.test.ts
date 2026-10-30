import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  initAuth,
  fetchStatus,
  fetchModels,
  selectModel,
  setWorkspace,
  chatFetch,
  fetchSessions,
  createSession,
  deleteSession,
  switchSession,
} from './client'

// ── Helpers ────────────────────────────────────────────────────────

function mockFetch(response: Partial<Response>) {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response as Response)
}

function mockFetchOk(data: unknown) {
  mockFetch({
    ok: true,
    json: async () => data,
    text: async () => JSON.stringify(data),
  })
}

function mockFetchError(status: number, body?: string) {
  mockFetch({
    ok: false,
    status,
    text: async () => body ?? `Error ${status}`,
  })
}

function createSSEStream(events: string[]): ReadableStream<Uint8Array> {
  const body = events.map((e) => `data: ${e}\n\n`).join('') + 'data: [DONE]\n\n'
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(body))
      controller.close()
    },
  })
}

function createSSEResponse(events: string[]): Response {
  return {
    ok: true,
    body: createSSEStream(events) as unknown as ReadableStream<Uint8Array>,
  } as Response
}

// ── Init Auth ──────────────────────────────────────────────────────

describe('initAuth', () => {
  it('returns true and stores token when auth is enabled', async () => {
    mockFetchOk({ auth_enabled: true, token: 'test-token-123' })

    const result = await initAuth()
    expect(result).toBe(true)

    // Verify token is used in subsequent requests
    mockFetchOk({ model: 'test' })
    await fetchStatus()
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/status',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token-123',
        }),
      })
    )
  })

  it('returns false when auth is disabled', async () => {
    mockFetchOk({ auth_enabled: false, token: null })
    const result = await initAuth()
    expect(result).toBe(false)
  })

  it('returns false on network error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'))
    const result = await initAuth()
    expect(result).toBe(false)
  })
})

// ── Basic API wrappers ─────────────────────────────────────────────

describe('fetchStatus', () => {
  it('returns status info', async () => {
    const statusData = {
      session_id: 's1',
      current_session_id: 'cs1',
      workspace: '/tmp',
      branch: 'main',
      model: 'qwen3.5:4b',
      provider: 'ollama',
      approval: 'auto',
      max_steps: 6,
      mcp_available: true,
      mcp_servers: [],
      version: '0.3.0',
    }
    mockFetchOk(statusData)
    const result = await fetchStatus()
    expect(result).toEqual(statusData)
  })

  it('throws on error status', async () => {
    mockFetchError(500)
    await expect(fetchStatus()).rejects.toThrow('status: 500')
  })
})

describe('fetchModels', () => {
  it('returns models array', async () => {
    mockFetchOk({ models: [{ name: 'qwen3.5:4b', type: 'local' }] })
    const result = await fetchModels()
    expect(result).toEqual([{ name: 'qwen3.5:4b', type: 'local' }])
  })

  it('returns empty array when models is missing', async () => {
    mockFetchOk({})
    const result = await fetchModels()
    expect(result).toEqual([])
  })
})

describe('selectModel', () => {
  it('sends POST with model name', async () => {
    mockFetchOk({})
    await selectModel('deepseek-v4-flash')

    expect(fetch).toHaveBeenCalledWith(
      '/api/models/select',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'deepseek-v4-flash' }),
      })
    )
  })

  it('throws on error', async () => {
    mockFetchError(400)
    await expect(selectModel('bad')).rejects.toThrow('select model: 400')
  })
})

describe('setWorkspace', () => {
  it('returns root and branch on success', async () => {
    mockFetchOk({ status: 'ok', root: '/home/project', branch: 'main' })
    const result = await setWorkspace('/home/project')
    expect(result.root).toBe('/home/project')
    expect(result.branch).toBe('main')
  })

  it('throws with error body text', async () => {
    mockFetchError(400, 'Directory not found')
    await expect(setWorkspace('/nonexistent')).rejects.toThrow('Directory not found')
  })
})

// ── Session CRUD ───────────────────────────────────────────────────

describe('fetchSessions', () => {
  it('returns sessions array', async () => {
    const sessions = [
      { id: '1', name: 'test', workspace: '/tmp', model: 'qwen', provider: 'ollama' },
    ]
    mockFetchOk({ sessions })
    const result = await fetchSessions()
    expect(result).toEqual(sessions)
  })

  it('returns empty array when sessions is missing', async () => {
    mockFetchOk({})
    const result = await fetchSessions()
    expect(result).toEqual([])
  })
})

describe('createSession', () => {
  it('sends POST with options', async () => {
    const session = { id: 'new', name: 'test', workspace: '/tmp' }
    mockFetchOk({ session })
    const result = await createSession({ name: 'test' })
    expect(result).toEqual(session)
  })
})

describe('deleteSession', () => {
  it('sends DELETE request', async () => {
    mockFetchOk({})
    await deleteSession('my-session-id')
    expect(fetch).toHaveBeenCalledWith(
      '/api/sessions/my-session-id',
      expect.objectContaining({ method: 'DELETE' })
    )
  })
})

describe('switchSession', () => {
  it('returns session info on switch', async () => {
    const data = { status: 'ok', session: { id: '1' }, workspace: '/tmp', model: 'qwen' }
    mockFetchOk(data)
    const result = await switchSession('1')
    expect(result).toEqual(data)
  })
})

// ── chatFetch (SSE streaming) ──────────────────────────────────────

describe('chatFetch', () => {
  it('yields SSE events in order', async () => {
    const events = [
      JSON.stringify({ type: 'start', data: { max_steps: 6 } }),
      JSON.stringify({ type: 'plan', data: { steps: '1. Read file\n2. Fix it' } }),
      JSON.stringify({ type: 'model_response', data: { chunk: 'Sure,' } }),
      JSON.stringify({ type: 'model_response', data: { chunk: ' let me help.' } }),
      JSON.stringify({ type: 'tool_call', data: { name: 'read_file', args: { path: 'test.py' } } }),
      JSON.stringify({ type: 'tool_result', data: { name: 'read_file', result: 'print("hello")' } }),
      JSON.stringify({ type: 'final', data: { content: 'Done!' } }),
    ]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(createSSEResponse(events))

    const received: unknown[] = []
    for await (const event of chatFetch('hello')) {
      received.push(event)
    }

    expect(received).toHaveLength(7)
    expect(received[0]).toEqual({ type: 'start', data: { max_steps: 6 } })
    expect(received[3]).toEqual({ type: 'model_response', data: { chunk: ' let me help.' } })
    expect(received[6]).toEqual({ type: 'final', data: { content: 'Done!' } })
  })

  it('passes images parameter correctly', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(createSSEResponse([]))
    const images = ['base64img1', 'base64img2']

    // consume the generator
    for await (const _ of chatFetch('describe', images)) { void _ }

    expect(fetch).toHaveBeenCalledWith(
      '/api/chat',
      expect.objectContaining({
        body: JSON.stringify({ message: 'describe', images }),
      })
    )
  })

  it('passes undefined images when not provided', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(createSSEResponse([]))

    for await (const _ of chatFetch('hello')) { void _ }

    expect(fetch).toHaveBeenCalledWith(
      '/api/chat',
      expect.objectContaining({
        body: JSON.stringify({ message: 'hello', images: [] }),
      })
    )
  })

  it('handles partial lines in chunks (buffer management)', async () => {
    // Simulate a ReadableStream that sends data in arbitrary chunk boundaries
    const encoder = new TextEncoder()
    const fullText = 'data: {"type":"start","data":{}}\n\ndata: {"type":"final","data":{"content":"ok"}}\n\ndata: [DONE]\n\n'

    // Split into 3 uneven chunks
    const chunk1 = encoder.encode(fullText.slice(0, 50))
    const chunk2 = encoder.encode(fullText.slice(50, 90))
    const chunk3 = encoder.encode(fullText.slice(90))

    let chunkIndex = 0
    const chunks = [chunk1, chunk2, chunk3]

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (chunkIndex < chunks.length) {
              const value = chunks[chunkIndex++]
              return { done: false, value }
            }
            return { done: true, value: undefined }
          },
        }),
      },
    } as unknown as Response)

    const received: unknown[] = []
    for await (const event of chatFetch('hello')) {
      received.push(event)
    }

    expect(received).toHaveLength(2)
    expect(received[0]).toEqual({ type: 'start', data: {} })
    expect(received[1]).toEqual({ type: 'final', data: { content: 'ok' } })
  })

  it('throws on non-ok response', async () => {
    mockFetchError(500, 'Internal server error')
    await expect(
      (async () => {
        for await (const _ of chatFetch('hello')) { void _ }
      })()
    ).rejects.toThrow('chat error: 500')
  })

  it('throws when response has no body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      body: null,
    } as Response)

    await expect(
      (async () => {
        for await (const _ of chatFetch('hello')) { void _ }
      })()
    ).rejects.toThrow('No response body')
  })

  it('skips invalid JSON lines without throwing', async () => {
    // Include an invalid JSON line between valid ones
    const events = [
      JSON.stringify({ type: 'start', data: {} }),
      'not-valid-json{{{',
      JSON.stringify({ type: 'final', data: { content: 'still works' } }),
    ]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(createSSEResponse(events))

    const received: unknown[] = []
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    for await (const event of chatFetch('hello')) {
      received.push(event)
    }
    warnSpy.mockRestore()

    expect(received).toHaveLength(2)
    expect(received[0]).toEqual({ type: 'start', data: {} })
    expect(received[1]).toEqual({ type: 'final', data: { content: 'still works' } })
  })

  it('stops at [DONE] sentinel', async () => {
    const events = [
      JSON.stringify({ type: 'start', data: {} }),
      // After [DONE], more data should be ignored
    ]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(createSSEResponse(events))

    const received: unknown[] = []
    for await (const event of chatFetch('hello')) {
      received.push(event)
    }

    expect(received).toHaveLength(1)
  })
})

// ── Cleanup ────────────────────────────────────────────────────────

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})
