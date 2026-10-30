import { useState, useCallback } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check, X, FileCode } from 'lucide-react'
import { twMerge } from 'tailwind-merge'

interface FilePreviewProps {
  path: string
  content: string
  onClose?: () => void
}

const EXTENSION_MAP: Record<string, string> = {
  py: 'python',
  pyw: 'python',
  js: 'javascript',
  jsx: 'jsx',
  ts: 'typescript',
  tsx: 'tsx',
  html: 'html',
  css: 'css',
  scss: 'scss',
  json: 'json',
  xml: 'xml',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'toml',
  md: 'markdown',
  mdx: 'mdx',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  ps1: 'powershell',
  bat: 'batch',
  cmd: 'batch',
  c: 'c',
  cpp: 'cpp',
  h: 'c',
  hpp: 'cpp',
  cs: 'csharp',
  java: 'java',
  rs: 'rust',
  go: 'go',
  rb: 'ruby',
  php: 'php',
  swift: 'swift',
  kt: 'kotlin',
  dart: 'dart',
  lua: 'lua',
  r: 'r',
  sql: 'sql',
  graphql: 'graphql',
  vue: 'vue',
  svelte: 'svelte',
  dockerfile: 'dockerfile',
  env: 'properties',
  gitignore: 'ignore',
  csv: 'csv',
  lock: 'json',
}

const LANGUAGE_COLORS: Record<string, string> = {
  python: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  javascript: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  typescript: 'bg-blue-600/15 text-blue-300 border-blue-600/30',
  jsx: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
  tsx: 'bg-blue-600/15 text-blue-300 border-blue-600/30',
  html: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  css: 'bg-pink-500/15 text-pink-400 border-pink-500/30',
  json: 'bg-green-500/15 text-green-400 border-green-500/30',
  markdown: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  bash: 'bg-gray-500/15 text-gray-300 border-gray-500/30',
  rust: 'bg-orange-600/15 text-orange-300 border-orange-600/30',
  go: 'bg-cyan-600/15 text-cyan-300 border-cyan-600/30',
  sql: 'bg-red-500/15 text-red-400 border-red-500/30',
  yaml: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
}

function detectLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  const filename = path.split(/[/\\]/).pop()?.toLowerCase() || ''

  // Handle special filenames
  if (filename === 'dockerfile') return 'dockerfile'
  if (filename === '.gitignore') return 'ignore'
  if (filename === '.env') return 'properties'
  if (filename === 'makefile' || filename === 'makefile') return 'makefile'

  return EXTENSION_MAP[ext] || ext || 'text'
}

function countLines(text: string): number {
  if (!text) return 0
  return text.split('\n').length
}

export function FilePreview({ path, content, onClose }: FilePreviewProps) {
  const [copied, setCopied] = useState(false)

  const language = detectLanguage(path)
  const lineCount = countLines(content)
  const langDisplay = language === 'text' ? extFromPath(path) : language
  const langColor = LANGUAGE_COLORS[language] || 'bg-gray-500/15 text-gray-400 border-gray-500/30'

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }, [content])

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-bg-border bg-bg-surface/50 select-none">
        <div className="flex items-center gap-2.5 min-w-0 overflow-hidden">
          <FileCode size={15} className="text-fg-muted flex-shrink-0" />
          <span className="text-sm font-medium text-fg truncate">
            {path.split('/').pop() || path}
          </span>
          <span
            className={twMerge(
              'px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider border flex-shrink-0',
              langColor
            )}
          >
            {langDisplay}
          </span>
          <span className="text-[11px] text-fg-dim flex-shrink-0">
            {lineCount} líneas
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleCopy}
            className="btn-ghost p-1.5"
            title="Copiar contenido"
          >
            {copied ? <Check size={14} className="text-success" /> : <Copy size={14} />}
          </button>
          {onClose && (
            <button onClick={onClose} className="btn-ghost p-1.5" title="Cerrar">
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Code */}
      <div className="flex-1 overflow-auto text-[13px] leading-relaxed">
        <SyntaxHighlighter
          language={language}
          style={oneDark}
          showLineNumbers
          wrapLines
          customStyle={{
            margin: 0,
            padding: '16px 0',
            borderRadius: 0,
            height: '100%',
            fontSize: '13px',
            lineHeight: '1.6',
            background: '#1a1b26',
          }}
          lineNumberStyle={{
            minWidth: '3em',
            paddingRight: '1em',
            color: '#4a4b5a',
            textAlign: 'right',
            userSelect: 'none',
            borderRight: '1px solid #2a2b3a',
            marginRight: '1em',
          }}
          codeTagProps={{
            style: {
              fontFamily: '"JetBrains Mono", "Cascadia Code", Consolas, monospace',
            },
          }}
        >
          {content}
        </SyntaxHighlighter>
      </div>
    </div>
  )
}

function extFromPath(path: string): string {
  const ext = path.split('.').pop() || ''
  return ext.toUpperCase() || 'TEXT'
}
