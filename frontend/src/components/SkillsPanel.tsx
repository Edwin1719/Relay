import { useState, useEffect } from 'react'
import { Brain, ToggleLeft, ToggleRight, Loader2 } from 'lucide-react'
import { twMerge } from 'tailwind-merge'

interface SkillInfo {
  name: string
  display_name: string
  description: string
  enabled: boolean
}

// Auth headers (same pattern as client.ts — avoids circular dependency)
let _authToken: string | null = null

async function initAuthToken() {
  try {
    const res = await fetch('/api/auth-token')
    if (res.ok) {
      const data = await res.json()
      if (data.auth_enabled && data.token) {
        _authToken = data.token
      }
    }
  } catch { /* ignore */ }
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (_authToken) headers['Authorization'] = `Bearer ${_authToken}`
  return headers
}

export function SkillsPanel() {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [toggling, setToggling] = useState<string | null>(null)

  useEffect(() => {
    initAuthToken().then(() => fetchSkills())
  }, [])

  async function fetchSkills() {
    try {
      const res = await fetch('/api/skills', { headers: authHeaders() })
      const data = await res.json()
      setSkills(data.skills || [])
    } catch (e) {
      console.error('Failed to fetch skills', e)
    } finally {
      setLoading(false)
    }
  }

  async function handleToggle(name: string) {
    setToggling(name)
    try {
      const res = await fetch('/api/skills/toggle', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ name }),
      })
      const data = await res.json()
      if (data.status === 'ok') {
        setSkills(prev =>
          prev.map(s => (s.name === name ? { ...s, enabled: data.enabled } : s))
        )
      }
    } catch (e) {
      console.error('Failed to toggle skill', e)
    } finally {
      setToggling(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={20} className="animate-spin text-fg-muted" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-bg-border">
        <Brain size={16} className="text-accent" />
        <span className="text-base font-semibold text-fg">Skills</span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {skills.length === 0 && (
          <p className="text-sm text-fg-dim text-center py-8">
            No skills available.
          </p>
        )}

        {skills.map(skill => (
          <div
            key={skill.name}
            className={twMerge(
              'rounded-lg border p-3 transition-colors',
              skill.enabled
                ? 'border-accent-muted bg-accent/5'
                : 'border-bg-border bg-bg-surface'
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex-1 min-w-0">
                <h3 className="text-base font-medium text-fg truncate">
                  {skill.display_name}
                </h3>
                <p className="text-sm text-fg-muted mt-0.5 line-clamp-2">
                  {skill.description}
                </p>
              </div>
              <button
                onClick={() => handleToggle(skill.name)}
                disabled={toggling === skill.name}
                className={twMerge(
                  'flex-shrink-0 p-1 rounded transition-colors',
                  skill.enabled
                    ? 'text-accent hover:text-accent-dim'
                    : 'text-fg-dim hover:text-fg-muted'
                )}
                title={skill.enabled ? 'Disable' : 'Enable'}
              >
                {toggling === skill.name ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : skill.enabled ? (
                  <ToggleRight size={18} />
                ) : (
                  <ToggleLeft size={18} />
                )}
              </button>
            </div>

            {skill.enabled && (
              <div className="mt-2 flex items-center gap-1.5">
                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-900/30 text-emerald-300">
                  Active
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
