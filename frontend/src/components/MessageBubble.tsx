import { User, Bot, Info } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { twMerge } from 'tailwind-merge'
import { ToolCallCard } from './ToolCallCard'
import type { Message } from '../hooks/useChat'

interface MessageBubbleProps {
  message: Message
  isLatestAssistant?: boolean
}

export function MessageBubble({ message, isLatestAssistant }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  const isTool = message.role === 'tool'

  if (isTool) return null // Tools are rendered inline inside assistant messages

  if (isSystem) {
    return (
      <div className="flex items-center justify-center py-3">
        <div className="flex items-center gap-2 px-5 py-2 rounded-full bg-bg-surface border border-bg-border">
          <Info size={16} className="text-fg-muted" />
          <span className="text-base text-fg-muted">{message.content}</span>
        </div>
      </div>
    )
  }

  return (
    <div className={twMerge('flex gap-3 px-5 py-3', isUser ? 'justify-end' : 'justify-start')}>
      {/* Avatar */}
      {!isUser && (
        <div className="flex-shrink-0 w-9 h-9 rounded-full bg-accent-muted/20 border border-accent-muted/30 flex items-center justify-center">
          <Bot size={18} className="text-accent" />
        </div>
      )}

      {/* Content */}
      <div className={twMerge('max-w-[80%]', isUser ? 'order-1' : 'order-1')}>
        {/* Message body */}
        <div
          className={twMerge(
            'rounded-lg px-4 py-3 text-base leading-relaxed',
            isUser
              ? 'bg-accent-dim/20 border border-accent-dim/30 text-fg'
              : 'bg-bg-surface border border-bg-border text-fg'
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : message.content ? (
            <div className="prose prose-invert prose-base max-w-none
                          [&_table]:w-full [&_table]:border-collapse [&_table]:my-3
                          [&_thead_th]:bg-bg-hover [&_thead_th]:text-fg [&_thead_th]:font-semibold [&_thead_th]:px-3 [&_thead_th]:py-2 [&_thead_th]:border [&_thead_th]:border-bg-border [&_thead_th]:text-left
                          [&_tbody_td]:px-3 [&_tbody_td]:py-2 [&_tbody_td]:border [&_tbody_td]:border-bg-border
                          [&_tbody_tr:hover]:bg-bg-hover/50
                          [&_hr]:border-bg-border [&_hr]:my-4
                          [&_h1]:text-xl [&_h1]:font-bold [&_h1]:mt-4 [&_h1]:mb-2
                          [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:mt-3 [&_h2]:mb-2
                          [&_h3]:text-base [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1
                          [&_code]:bg-bg-hover [&_code]:text-accent [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-base
                          [&_pre_code]:bg-transparent [&_pre_code]:p-0
                          [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2
                          [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2
                          [&_li]:my-1">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            </div>
          ) : message.toolSteps && message.toolSteps.length > 0 ? null : (
            <span className="text-fg-muted italic">Pensando...</span>
          )}
        </div>

        {/* Tool steps (only for assistant) */}
        {!isUser && message.toolSteps && message.toolSteps.length > 0 && (
          <div className="mt-2 space-y-1">
            {message.toolSteps.map((step, i) => (
              <ToolCallCard
                key={`${step.name}-${i}`}
                step={step}
                isLatest={isLatestAssistant === true && i === message.toolSteps!.length - 1}
              />
            ))}
          </div>
        )}
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-dim/30 flex items-center justify-center">
          <User size={16} className="text-accent" />
        </div>
      )}
    </div>
  )
}
