import { useState } from 'react'
import { Terminal, CheckCircle, XCircle, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { twMerge } from 'tailwind-merge'
import { approveTool } from '../api/client'
import type { ToolStep } from '../hooks/useChat'

interface ToolCallCardProps {
  step: ToolStep
  isLatest: boolean
}

export function ToolCallCard({ step, isLatest }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(
    Array.isArray(step.args.checklist) && step.args.checklist.length > 0
  )
  const [deciding, setDeciding] = useState(false)
  const hasResult = step.result !== undefined
  const needsApproval = Boolean(step.awaitingApproval) && !hasResult

  async function decide(approved: boolean) {
    setDeciding(true)
    try {
      await approveTool(approved)
    } catch {
      // The stream will surface the failure; re-enable so the user can retry.
    } finally {
      setDeciding(false)
    }
  }
  // Detect errors even after Spanish translation: the backend appends
  // "[SYSTEM] Retry N/3..." markers to all tool errors after translating
  // them, so we check for that marker instead of the stripped "error:" prefix.
  const isError = hasResult && (
    step.result!.includes('[SYSTEM]') ||
    step.result!.toLowerCase().startsWith('error')
  )

  return (
    <div
      className={twMerge(
        'border rounded-md text-sm font-mono mb-1 overflow-hidden transition-colors',
        isError
          ? 'border-red-900/50 bg-red-950/20'
          : hasResult
            ? 'border-bg-border bg-bg-surface/50'
            : 'border-accent-muted/30 bg-bg-surface'
      )}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-bg-hover/50 transition-colors text-left"
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Terminal size={12} className="text-fg-muted" />

        {/* Tool name */}
        <span className="text-accent font-semibold">{step.name}</span>

        {/* Args summary */}
        <span className="text-fg-muted truncate flex-1">
          {Object.entries(step.args).filter(([k]) => k !== 'checklist').map(([k, v]) => (
            <span key={k} className="mr-2">
              <span className="text-fg-dim">{k}=</span>
              <span className="text-fg">{String(v).slice(0, 40)}</span>
            </span>
          ))}
        </span>

        {/* Status */}
        <span className="flex-shrink-0">
          {!hasResult ? (
            isLatest ? (
              <Loader2 size={12} className="text-warning animate-spin" />
            ) : (
              <Loader2 size={12} className="text-fg-dim" />
            )
          ) : isError ? (
            <XCircle size={12} className="text-danger" />
          ) : (
            <CheckCircle size={12} className="text-success" />
          )}
        </span>
      </button>

      {/* Expanded body: result or checklist */}
      {expanded && (
        <div className="border-t border-bg-border px-3 py-2 text-fg-muted max-h-48 overflow-auto">
          {step.args.checklist && Array.isArray(step.args.checklist) ? (
            <div className="space-y-1.5">
              {(step.args.checklist as { text: string; done: boolean }[]).map((item, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className={twMerge(
                    'w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 mt-0.5 text-[10px]',
                    item.done
                      ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400'
                      : 'border-bg-border text-fg-dim'
                  )}>
                    {item.done ? '✓' : (i + 1)}
                  </span>
                  <span className={item.done ? 'line-through opacity-60' : 'text-fg'}>
                    {item.text}
                  </span>
                </div>
              ))}
            </div>
          ) : step.result ? (
            <pre className="whitespace-pre-wrap break-all leading-relaxed">
              {step.result}
            </pre>
          ) : null}
        </div>
      )}

      {needsApproval && (
        <div className="border-t border-bg-border px-3 py-2">
          {step.approvalDiff && (
            <pre className="mb-2 max-h-40 overflow-auto text-[11px] leading-relaxed">
              {step.approvalDiff.split('\n').map((line, i) => (
                <div
                  key={i}
                  className={
                    line.startsWith('+')
                      ? 'text-emerald-400'
                      : line.startsWith('-')
                        ? 'text-red-400'
                        : line.startsWith('@@')
                          ? 'text-accent'
                          : 'text-fg-muted'
                  }
                >
                  {line || ' '}
                </div>
              ))}
            </pre>
          )}
          <div className="flex items-center gap-2">
            <span className="text-xs text-warning flex-1">¿Ejecutar esta herramienta?</span>
            <button
              onClick={() => decide(true)}
              disabled={deciding}
              className="px-2 py-1 rounded text-xs bg-emerald-600/80 hover:bg-emerald-600 text-white disabled:opacity-50"
            >
              Aprobar
            </button>
            <button
              onClick={() => decide(false)}
              disabled={deciding}
              className="px-2 py-1 rounded text-xs bg-red-600/80 hover:bg-red-600 text-white disabled:opacity-50"
            >
              Rechazar
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
