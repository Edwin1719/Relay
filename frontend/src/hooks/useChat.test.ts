import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import type { AttachedFile } from '../components/ChatPanel'

// ── Mock the client module ─────────────────────────────────────────

// We spy on useChat's internal formatAttachedFiles by re-importing it
// from the module itself (it's a private function but we can test it indirectly
// via sendMessage behavior)

const mockChatFetch = vi.fn()
const mockFetchStatus = vi.fn()
const mockFetchModels = vi.fn()
const mockSelectModel = vi.fn()
const mockSetWorkspace = vi.fn()
const mockFetchMCPStatus = vi.fn()
const mockInitAuth = vi.fn()

vi.mock('../api/client', () => ({
  initAuth: (...args: unknown[]) => mockInitAuth(...args),
  chatFetch: (...args: unknown[]) => mockChatFetch(...args),
  fetchStatus: (...args: unknown[]) => mockFetchStatus(...args),
  fetchModels: (...args: unknown[]) => mockFetchModels(...args),
  selectModel: (...args: unknown[]) => mockSelectModel(...args),
  setWorkspace: (...args: unknown[]) => mockSetWorkspace(...args),
  fetchMCPStatus: (...args: unknown[]) => mockFetchMCPStatus(...args),
}))

import { useChat } from '../hooks/useChat'

// ── Helpers ────────────────────────────────────────────────────────

function makeSSEGenerator(events: Array<{ type: string; data: Record<string, unknown> }>) {
  async function* gen() {
    for (const e of events) {
      yield e as { type: string; data: Record<string, unknown> }
    }
  }
  return gen()
}

function makeTextFile(name: string, content: string): AttachedFile {
  return { name, content, type: 'text' }
}

function makeImageFile(name: string, base64: string): AttachedFile {
  return { name, content: `data:image/jpeg;base64,${base64}`, type: 'image' }
}

// ── Initial state ──────────────────────────────────────────────────

describe('useChat — initial state', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockInitAuth.mockResolvedValue(true)
    mockFetchStatus.mockResolvedValue({ model: '', mcp_servers: [], current_session_id: null })
    mockFetchModels.mockResolvedValue([])
    mockFetchMCPStatus.mockResolvedValue({ servers: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('starts with a welcome message', () => {
    const { result } = renderHook(() => useChat())
    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].role).toBe('system')
    expect(result.current.messages[0].content).toContain('Relay conectado')
  })

  it('starts with streaming=false', () => {
    const { result } = renderHook(() => useChat())
    expect(result.current.streaming).toBe(false)
  })

  it('starts with projectLoaded=false', () => {
    const { result } = renderHook(() => useChat())
    expect(result.current.projectLoaded).toBe(false)
  })

  it('calls initAuth on mount', () => {
    renderHook(() => useChat())
    expect(mockInitAuth).toHaveBeenCalled()
  })

  it('loads status, models, and MCP on mount', () => {
    renderHook(() => useChat())
    expect(mockFetchStatus).toHaveBeenCalled()
    expect(mockFetchModels).toHaveBeenCalled()
    expect(mockFetchMCPStatus).toHaveBeenCalled()
  })
})

// ── sendMessage — SSE event loop ──────────────────────────────────

describe('useChat — sendMessage', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockInitAuth.mockResolvedValue(true)
    mockFetchStatus.mockResolvedValue({ model: '', mcp_servers: [], current_session_id: null })
    mockFetchModels.mockResolvedValue([])
    mockFetchMCPStatus.mockResolvedValue({ servers: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('adds user message and assistant placeholder on send', async () => {
    mockChatFetch.mockReturnValue(makeSSEGenerator([]))

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Hola')
    })

    const msgs = result.current.messages
    expect(msgs).toHaveLength(3) // welcome + user + assistant
    expect(msgs[1].role).toBe('user')
    expect(msgs[1].content).toBe('Hola')
    expect(msgs[2].role).toBe('assistant')
    expect(msgs[2].content).toBe('')
  })

  it('accumulates model_response chunks', async () => {
    mockChatFetch.mockReturnValue(
      makeSSEGenerator([
        { type: 'model_response', data: { chunk: 'Hello' } },
        { type: 'model_response', data: { chunk: ' world' } },
        { type: 'model_response', data: { chunk: '!' } },
      ])
    )

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Hi')
    })

    const assistant = result.current.messages[2]
    expect(assistant.content).toBe('Hello world!')
  })

  it('handles plan event with steps as result', async () => {
    mockChatFetch.mockReturnValue(
      makeSSEGenerator([
        { type: 'plan', data: { steps: '1. Search code\n2. Apply fix' } },
      ])
    )

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Fix the bug')
    })

    const assistant = result.current.messages[2]
    expect(assistant.toolSteps).toHaveLength(1)
    expect(assistant.toolSteps![0].name).toBe('📋 Plan')
    expect(assistant.toolSteps![0].result).toBe('1. Search code\n2. Apply fix')
  })

  it('passes the plan checklist through to the card', async () => {
    mockChatFetch.mockReturnValue(
      makeSSEGenerator([
        {
          type: 'plan',
          data: {
            steps: '1. Read\n2. Edit',
            checklist: [
              { text: 'Read the file', done: false },
              { text: 'Edit the file', done: false },
            ],
          },
        },
      ])
    )

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Fix the bug')
    })

    const plan = result.current.messages[2].toolSteps![0]
    expect(plan.args.checklist).toHaveLength(2)
  })

  it('marks the tool step as awaiting approval', async () => {
    mockChatFetch.mockReturnValue(
      makeSSEGenerator([
        { type: 'tool_call', data: { name: 'write_file', args: { path: 'a.txt' } } },
        {
          type: 'approval_required',
          data: { tool: 'write_file', diff: '--- a/a.txt\n+++ b/a.txt\n+hola' },
        },
      ])
    )

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Escribe a.txt')
    })

    const step = result.current.messages[2].toolSteps![0]
    expect(step.awaitingApproval).toBe(true)
    expect(step.approvalDiff).toContain('+hola')
  })

  it('tracks tool_call and tool_result steps', async () => {
    mockChatFetch.mockReturnValue(
      makeSSEGenerator([
        { type: 'tool_call', data: { name: 'read_file', args: { path: 'a.py' } } },
        { type: 'tool_result', data: { name: 'read_file', result: 'print("ok")' } },
      ])
    )

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Read a.py')
    })

    const assistant = result.current.messages[2]
    expect(assistant.toolSteps).toHaveLength(1)
    expect(assistant.toolSteps![0].name).toBe('read_file')
    expect(assistant.toolSteps![0].result).toBe('print("ok")')
  })

  it('matches tool_result to correct step by name', async () => {
    mockChatFetch.mockReturnValue(
      makeSSEGenerator([
        { type: 'tool_call', data: { name: 'read_a', args: {} } },
        { type: 'tool_call', data: { name: 'read_b', args: {} } },
        { type: 'tool_result', data: { name: 'read_b', result: 'content B' } },
        { type: 'tool_result', data: { name: 'read_a', result: 'content A' } },
      ])
    )

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Read files')
    })

    const steps = result.current.messages[2].toolSteps!
    expect(steps).toHaveLength(2)
    expect(steps[0].name).toBe('read_a')
    expect(steps[0].result).toBe('content A')
    expect(steps[1].name).toBe('read_b')
    expect(steps[1].result).toBe('content B')
  })

  it('overwrites content with final event (appending pending chunk buffer)', async () => {
    mockChatFetch.mockReturnValue(
      makeSSEGenerator([
        { type: 'model_response', data: { chunk: 'Let me think...' } },
        { type: 'final', data: { content: 'The answer is 42.' } },
      ])
    )

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('What is the answer?')
    })

    // The debounce buffer from model_response gets flushed + final content appended
    expect(result.current.messages[2].content).toBe('Let me think...The answer is 42.')
  })

  it('sets error on error event', async () => {
    mockChatFetch.mockReturnValue(
      makeSSEGenerator([
        { type: 'error', data: { message: 'Something went wrong' } },
      ])
    )

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Do something')
    })

    expect(result.current.error).toBe('Something went wrong')
    expect(result.current.messages[2].content).toBe('Error: Something went wrong')
  })

  it('sets error on thrown exception', async () => {
    // mockRejectedValue causes for-await-of to throw TypeError (not async iterable)
    // before reaching the catch block. Use an async generator that throws instead.
    mockChatFetch.mockImplementation(async function* () {
      throw new Error('Network failure')
    })

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Do something')
    })

    expect(result.current.error).toBe('Network failure')
    expect(result.current.messages[2].content).toBe('Error: Network failure')
  })

  it('sets streaming=false after completion', async () => {
    mockChatFetch.mockReturnValue(makeSSEGenerator([]))

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Hi')
    })

    expect(result.current.streaming).toBe(false)
  })

  it('sets streaming=false after error', async () => {
    mockChatFetch.mockRejectedValue(new Error('Boom'))

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Hi')
    })

    expect(result.current.streaming).toBe(false)
  })
})

// ── sendMessage — file attachments ────────────────────────────────

describe('useChat — file attachments', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockInitAuth.mockResolvedValue(true)
    mockFetchStatus.mockResolvedValue({ model: '', mcp_servers: [], current_session_id: null })
    mockFetchModels.mockResolvedValue([])
    mockFetchMCPStatus.mockResolvedValue({ servers: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('wraps text file content in code fences', async () => {
    mockChatFetch.mockReturnValue(makeSSEGenerator([]))
    const file = makeTextFile('readme.md', '# Hello World')

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Analyze this', [file])
    })

    const userMsg = result.current.messages[1]
    expect(userMsg.content).toContain('[Archivo adjunto: readme.md]')
    expect(userMsg.content).toContain('```')
    expect(userMsg.content).toContain('# Hello World')
    expect(userMsg.attachments).toEqual([file])
  })

  it('strips data URL prefix from images', async () => {
    mockChatFetch.mockReturnValue(makeSSEGenerator([]))
    const img = makeImageFile('photo.jpg', 'abc123base64')

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Describe this', [img])
    })

    const userMsg = result.current.messages[1]
    expect(userMsg.content).toContain('[Imagen adjunta: photo.jpg]')

    // Verify chatFetch was called with raw base64 (no data: prefix)
    expect(mockChatFetch).toHaveBeenCalledWith(
      expect.stringContaining('[Imagen adjunta: photo.jpg]'),
      ['abc123base64']
    )
  })

  it('handles multiple text files with plural prompt', async () => {
    mockChatFetch.mockReturnValue(makeSSEGenerator([]))
    const files = [makeTextFile('a.ts', '// a'), makeTextFile('b.ts', '// b')]

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('', files) // empty content, auto-generated prompt
    })

    const userMsg = result.current.messages[1]
    // Note: source has typo "esteos" from 'os archivos' (should be 's archivos')
    expect(userMsg.content).toContain('Analiza esteos archivos adjuntos')
    expect(userMsg.content).toContain('[Archivo adjunto: a.ts]')
    expect(userMsg.content).toContain('[Archivo adjunto: b.ts]')
  })

  it('handles single text file with singular prompt', async () => {
    mockChatFetch.mockReturnValue(makeSSEGenerator([]))
    const files = [makeTextFile('config.json', '{}')]

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('', files)
    })

    const userMsg = result.current.messages[1]
    expect(userMsg.content).toContain('Analiza este archivo adjunto')
  })
})

// ── switchModel / setWorkspace / clearChat ────────────────────────

describe('useChat — actions', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockInitAuth.mockResolvedValue(true)
    mockFetchStatus.mockResolvedValue({ model: '', mcp_servers: [], current_session_id: null })
    mockFetchModels.mockResolvedValue([])
    mockFetchMCPStatus.mockResolvedValue({ servers: [] })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('switchModel calls selectModel and adds system message', async () => {
    mockSelectModel.mockResolvedValue(undefined)

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.switchModel('deepseek-v4-flash')
    })

    expect(mockSelectModel).toHaveBeenCalledWith('deepseek-v4-flash')
    expect(result.current.activeModel).toBe('deepseek-v4-flash')
    expect(result.current.messages[1].role).toBe('system')
    expect(result.current.messages[1].content).toContain('Modelo cambiado a deepseek-v4-flash')
  })

  it('switchModel sets error on failure', async () => {
    mockSelectModel.mockRejectedValue(new Error('Model not found'))

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.switchModel('bad-model')
    })

    expect(result.current.error).toBe('Model not found')
  })

  it('setWorkspace sets projectLoaded and adds system message', async () => {
    mockSetWorkspace.mockResolvedValue({ root: '/home/project', branch: 'main' })

    const { result } = renderHook(() => useChat())

    let workspace: unknown
    await act(async () => {
      workspace = await result.current.setWorkspace('/home/project')
    })

    expect(result.current.projectLoaded).toBe(true)
    expect(result.current.messages[1].content).toContain('Workspace cambiado a: /home/project')
  })

  it('clearChat resets messages to one welcome', async () => {
    mockChatFetch.mockReturnValue(makeSSEGenerator([]))

    const { result } = renderHook(() => useChat())

    await act(async () => {
      await result.current.sendMessage('Hello')
    })
    expect(result.current.messages).toHaveLength(3) // welcome + user + assistant

    await act(async () => {
      result.current.clearChat()
    })
    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].content).toContain('Chat reiniciado')
  })
})
