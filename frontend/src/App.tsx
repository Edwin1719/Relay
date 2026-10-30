import { useState, useCallback, useEffect } from 'react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import { Zap, PanelRightClose, PanelRightOpen, Cpu, Globe, Puzzle, History, Settings, Brain, Play, HelpCircle } from 'lucide-react'
import { ChatPanel } from './components/ChatPanel'
import { FileExplorer } from './components/FileExplorer'
import { SettingsPanel } from './components/SettingsPanel'
import { FilePreview } from './components/FilePreview'
import { SessionList } from './components/SessionList'
import { IntegrationsPanel } from './components/IntegrationsPanel'
import { SkillsPanel } from './components/SkillsPanel'
import { AutomationsPanel } from './components/AutomationsPanel'
import { OnboardingWizard } from './components/OnboardingWizard'
import { CommandPalette } from './components/CommandPalette'
import { HelpPanel } from './components/HelpPanel'
import { useChat } from './hooks/useChat'
import type { ModelInfo, ModelTier } from './api/client'

type SidebarTab = 'explorer' | 'sessions' | 'integrations' | 'skills' | 'settings' | 'auto' | 'help'

export default function App() {
  const {
    messages, streaming, status, models, activeModel, mcpServers, currentSessionId,
    hasUnsavedMessages,
    error, stuckWarning, backgroundTasks,
    sendMessage, stopAgent, clearChat, switchModel, setWorkspace, restoreSession, projectLoaded, resetProject,
    loadModels,
  } = useChat()
  const [activeTab, setActiveTab] = useState<SidebarTab>('explorer')
  const [previewContent, setPreviewContent] = useState<string | null>(null)
  const [previewPath, setPreviewPath] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [prefilledPrompt, setPrefilledPrompt] = useState<string | undefined>(undefined)
  const [showPalette, setShowPalette] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setShowPalette(p => !p)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handlePaletteNavigate = useCallback((tab: SidebarTab) => {
    setActiveTab(tab)
  }, [])

  const handleFileSelect = useCallback((path: string, content: string) => {
    setPreviewPath(path)
    setPreviewContent(content)
    setShowPreview(true)
  }, [])

  const handleSessionSwitch = useCallback(async () => {
    await restoreSession()
  }, [restoreSession])

  const handleSessionCreated = useCallback(async () => {
    await restoreSession()
  }, [restoreSession])

  const handleSelectAutomation = useCallback((prompt: string, suggestedModelType: ModelTier | 'any') => {
    setPrefilledPrompt(prompt)
    if (suggestedModelType !== 'any') {
      const match = models.find((m: ModelInfo) => m.tier === suggestedModelType)
      if (match && match.name !== activeModel) {
        switchModel(match.name)
      }
    }
  }, [models, activeModel, switchModel])

  const currentModel = models.find((m: ModelInfo) => m.name === activeModel)

  return (
    <div className="h-screen w-screen flex flex-col bg-bg-base text-fg overflow-hidden">
      {/* Title bar */}
      <header className="flex items-center justify-between px-5 py-2.5 border-b border-bg-border bg-bg-surface select-none">
        <div className="flex items-center gap-2.5">
          <Zap size={20} className="text-accent" />
          <span className="text-base font-bold tracking-tight">Relay</span>
        </div>
        <div className="flex items-center gap-3 text-sm text-fg-muted">
          {status ? (
            <>
              {/* Model badge */}
              <div className="flex items-center gap-1.5">
                {currentModel ? (
                  <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded ${
                    currentModel.tier === 'deep'
                      ? 'bg-purple-900/30 text-purple-300'
                      : 'bg-emerald-900/30 text-emerald-300'
                  }`}>
                    {currentModel.tier === 'deep'
                      ? <Globe size={10} />
                      : <Zap size={10} />
                    }
                    {activeModel}
                  </span>
                ) : (
                  <span className="flex items-center gap-1">
                    <Cpu size={10} />
                    {activeModel || status.model}
                  </span>
                )}
              </div>

              <span className="text-fg-dim">·</span>
              <span>{status.branch}</span>
              <span className="text-fg-dim">·</span>

              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-success" />
                Online
              </span>

              {/* MCP badge */}
              {mcpServers.length > 0 && (
                <>
                  <span className="text-fg-dim">·</span>
                  <span className="text-fg-muted flex items-center gap-1">
                    <Puzzle size={10} />
                    {mcpServers.filter(s => s.status === 'connected').length}/{mcpServers.length} MCP
                  </span>
                </>
              )}

              {/* Background task indicator */}
              {backgroundTasks > 0 && (
                <>
                  <span className="text-fg-dim">·</span>
                  <span className="text-accent flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                    {backgroundTasks} tarea{backgroundTasks > 1 ? 's' : ''} en fondo
                  </span>
                </>
              )}
            </>
          ) : (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-danger" />
              Backend desconectado
            </span>
          )}
        </div>
      </header>

      {/* Main content */}
      <PanelGroup direction="horizontal" className="flex-1 overflow-hidden">
        {/* Left sidebar */}
        <Panel defaultSize={20} minSize={15} maxSize={35}>
          <div className="h-full flex flex-col">
            <div className="flex border-b border-bg-border">
              <button
                onClick={() => setActiveTab('explorer')}
                className={`flex-1 px-3 py-2.5 text-base font-medium transition-colors ${
                  activeTab === 'explorer'
                    ? 'text-accent border-b-2 border-accent bg-bg-hover/30'
                    : 'text-fg-muted hover:text-fg hover:bg-bg-hover/20'
                }`}
              >
                Explorador
              </button>
              <button
                onClick={() => setActiveTab('sessions')}
                className={`flex items-center justify-center gap-1 flex-1 px-3 py-2.5 text-base font-medium transition-colors ${
                  activeTab === 'sessions'
                    ? 'text-accent border-b-2 border-accent bg-bg-hover/30'
                    : 'text-fg-muted hover:text-fg hover:bg-bg-hover/20'
                }`}
              >
                <History size={14} />
                Sesiones
              </button>
              <button
                onClick={() => setActiveTab('integrations')}
                className={`flex items-center justify-center gap-1 flex-1 px-3 py-2.5 text-base font-medium transition-colors ${
                  activeTab === 'integrations'
                    ? 'text-accent border-b-2 border-accent bg-bg-hover/30'
                    : 'text-fg-muted hover:text-fg hover:bg-bg-hover/20'
                }`}
              >
                <Puzzle size={14} />
                Integra.
              </button>
              <button
                onClick={() => setActiveTab('skills')}
                className={`flex items-center justify-center gap-1 flex-1 px-3 py-2.5 text-base font-medium transition-colors ${
                  activeTab === 'skills'
                    ? 'text-accent border-b-2 border-accent bg-bg-hover/30'
                    : 'text-fg-muted hover:text-fg hover:bg-bg-hover/20'
                }`}
                title="Skills"
              >
                <Brain size={14} />
              </button>
              <button
                onClick={() => setActiveTab('auto')}
                className={`flex items-center justify-center gap-1 flex-1 px-3 py-2.5 text-base font-medium transition-colors ${
                  activeTab === 'auto'
                    ? 'text-accent border-b-2 border-accent bg-bg-hover/30'
                    : 'text-fg-muted hover:text-fg hover:bg-bg-hover/20'
                }`}
                title="Auto"
              >
                <Play size={14} />
              </button>
              <button
                onClick={() => setActiveTab('help')}
                className={`flex items-center justify-center gap-1 flex-1 px-3 py-2.5 text-base font-medium transition-colors ${
                  activeTab === 'help'
                    ? 'text-accent border-b-2 border-accent bg-bg-hover/30'
                    : 'text-fg-muted hover:text-fg hover:bg-bg-hover/20'
                }`}
                title="Ayuda"
              >
                <HelpCircle size={16} />
              </button>
              <button
                onClick={() => setActiveTab('settings')}
                className={`flex items-center justify-center gap-1 flex-1 px-3 py-2.5 text-base font-medium transition-colors ${
                  activeTab === 'settings'
                    ? 'text-accent border-b-2 border-accent bg-bg-hover/30'
                    : 'text-fg-muted hover:text-fg hover:bg-bg-hover/20'
                }`}
                title="Configuración"
              >
                <Settings size={16} />
              </button>
            </div>

            <div className="flex-1 overflow-hidden">
              {activeTab === 'explorer' ? (
                <FileExplorer
                  onSelectFile={handleFileSelect}
                  projectLoaded={projectLoaded}
                  onSetWorkspace={setWorkspace}
                  onResetProject={resetProject}
                />
              ) : activeTab === 'sessions' ? (
                <SessionList
                  currentSessionId={currentSessionId}
                  hasUnsavedMessages={hasUnsavedMessages}
                  onSessionSwitch={handleSessionSwitch}
                  onSessionCreated={handleSessionCreated}
                />
              ) : activeTab === 'integrations' ? (
                <IntegrationsPanel />
              ) : activeTab === 'skills' ? (
                <SkillsPanel />
              ) : activeTab === 'auto' ? (
                <AutomationsPanel
                  onSelectAutomation={handleSelectAutomation}
                  models={models}
                  activeModel={activeModel}
                />
              ) : activeTab === 'help' ? (
                <HelpPanel />
              ) : (
                <SettingsPanel
                  status={status}
                  models={models}
                  activeModel={activeModel}
                  onRefresh={loadModels}
                  onSwitchModel={switchModel}
                  onSetWorkspace={setWorkspace}
                />
              )}
            </div>
          </div>
        </Panel>

        <PanelResizeHandle className="w-[3px] bg-bg-border hover:bg-accent-muted transition-colors cursor-col-resize" />

        {/* Chat panel */}
        <Panel defaultSize={45} minSize={30}>
          <ChatPanel
            messages={messages}
            streaming={streaming}
            error={error}
            stuckWarning={stuckWarning}
            onSend={sendMessage}
            onClear={clearChat}
            onStop={stopAgent}
            prefilledInput={prefilledPrompt}
            onPrefillClear={() => setPrefilledPrompt(undefined)}
          />
        </Panel>

        {showPreview && (
          <>
            <PanelResizeHandle className="w-[3px] bg-bg-border hover:bg-accent-muted transition-colors cursor-col-resize" />
            <Panel defaultSize={30} minSize={15}>
              {previewContent !== null ? (
                <FilePreview
                  path={previewPath || 'preview'}
                  content={previewContent}
                  onClose={() => setShowPreview(false)}
                />
              ) : (
                <div className="h-full flex flex-col">
                  <div className="flex items-center justify-between px-4 py-2.5 border-b border-bg-border bg-bg-surface/50">
                    <span className="text-sm font-semibold text-fg-muted">Vista previa</span>
                    <button
                      onClick={() => setShowPreview(false)}
                      className="btn-ghost p-1.5"
                      title="Cerrar vista previa"
                    >
                      <PanelRightClose size={14} />
                    </button>
                  </div>
                  <div className="flex-1 flex flex-col items-center justify-center text-fg-dim text-center p-6">
                    <PanelRightOpen size={32} className="text-fg-dim/30 mb-3" />
                    <p className="text-sm">Selecciona un archivo del explorador</p>
                    <p className="text-xs mt-1">para previsualizar su contenido</p>
                  </div>
                </div>
              )}
            </Panel>
          </>
        )}
      </PanelGroup>

      {showPalette && (
        <CommandPalette
          models={models}
          activeModel={activeModel}
          onNavigate={handlePaletteNavigate}
          onSwitchModel={switchModel}
          onClearChat={clearChat}
          onStopAgent={stopAgent}
          onClose={() => setShowPalette(false)}
        />
      )}

      <OnboardingWizard
        models={models}
        activeModel={activeModel}
        onComplete={(suggestion) => {
          if (suggestion) setPrefilledPrompt(suggestion)
        }}
      />
    </div>
  )
}
