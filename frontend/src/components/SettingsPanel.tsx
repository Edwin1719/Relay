import { useState, useEffect, useCallback } from 'react'
import { Settings, RefreshCw, Info, Cpu, FolderOpen, Search, Zap, Brain, KeyRound, Check } from 'lucide-react'
import {
  fetchWorkspace, pickFolder, fetchProviders, configureProvider,
  type StatusInfo, type WorkspaceInfo, type ModelInfo, type ModelTier, type ProviderInfo,
} from '../api/client'

interface SettingsPanelProps {
  status: StatusInfo | null
  models: ModelInfo[]
  activeModel: string
  onRefresh: () => void
  onSwitchModel: (name: string) => void
  onSetWorkspace: (path: string) => Promise<{ status: string; root: string; branch: string }>
}

export function SettingsPanel({ status, models, activeModel, onRefresh, onSwitchModel, onSetWorkspace }: SettingsPanelProps) {
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null)
  const [switching, setSwitching] = useState(false)
  const [workspaceInput, setWorkspaceInput] = useState('')
  const [settingWorkspace, setSettingWorkspace] = useState(false)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [savingProvider, setSavingProvider] = useState<string | null>(null)

  const loadProviders = useCallback(() => {
    fetchProviders()
      .then(setProviders)
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadProviders()
  }, [loadProviders, status])

  const handleSaveProvider = async (name: string, apiKey: string) => {
    setSavingProvider(name)
    try {
      await configureProvider(name, apiKey)
      loadProviders()
      onRefresh()
    } finally {
      setSavingProvider(null)
    }
  }

  useEffect(() => {
    fetchWorkspace()
      .then(setWorkspace)
      .catch(() => {})
  }, [status])

  const handleModelChange = async (name: string) => {
    setSwitching(true)
    await onSwitchModel(name)
    setSwitching(false)
  }


  const handleSetWorkspace = async () => {
    if (!workspaceInput.trim() || settingWorkspace) return
    setSettingWorkspace(true)
    try {
      await onSetWorkspace(workspaceInput.trim())
      setWorkspaceInput('')
      // Refresh workspace info
      const ws = await fetchWorkspace()
      setWorkspace(ws)
    } catch {
      // error is handled by the hook
    } finally {
      setSettingWorkspace(false)
    }
  }

  const handleOpenFolderPicker = async () => {
    try {
      const result = await pickFolder()
      if (!result.canceled && result.path) {
        setWorkspaceInput(result.path)
      }
    } catch {
      // error silently — user can still type path manually
    }
  }

  const fastModels = models.filter((m) => m.tier === 'fast')
  const deepModels = models.filter((m) => m.tier === 'deep')
  const currentModelInfo = models.find((m) => m.name === activeModel)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-bg-border bg-bg-surface/50">
        <div className="flex items-center gap-2.5">
          <Settings size={16} className="text-fg-muted" />
          <span className="text-sm font-semibold text-fg-muted uppercase tracking-wider">Config</span>
        </div>
        <button onClick={onRefresh} className="btn-ghost p-1.5" title="Refrescar">
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 text-sm">

        {/* Model selector */}
        <div>
          <h3 className="text-fg-muted font-semibold mb-3 flex items-center gap-2">
            <Cpu size={14} />
            Modelo activo
          </h3>

          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <span className="text-fg text-base font-medium break-all">{activeModel || '—'}</span>
            {currentModelInfo && (
              <>
                <TierBadge tier={currentModelInfo.tier} />
                <span className="text-xs text-fg-dim">{currentModelInfo.provider_label}</span>
              </>
            )}
          </div>

          <TierGroup
            tier="deep"
            models={deepModels}
            activeModel={activeModel}
            switching={switching}
            onSelect={handleModelChange}
          />
          <TierGroup
            tier="fast"
            models={fastModels}
            activeModel={activeModel}
            switching={switching}
            onSelect={handleModelChange}
          />

          {models.length === 0 && (
            <p className="text-fg-dim italic">
              No hay modelos disponibles. Configura DEEPSEEK_API_KEY o APINEX_API_KEY
              en <code className="text-xs">backend/.env</code>.
            </p>
          )}
        </div>

        <div className="border-t border-bg-border" />

        {/* Providers */}
        <div>
          <h3 className="text-fg-muted font-semibold mb-2 flex items-center gap-1.5">
            <KeyRound size={12} />
            Proveedores
          </h3>
          <div className="space-y-2">
            {providers.map((p) => (
              <ProviderCard
                key={p.name}
                provider={p}
                saving={savingProvider === p.name}
                onSave={handleSaveProvider}
              />
            ))}
          </div>
          <p className="text-fg-dim/70 text-[11px] mt-2 leading-relaxed">
            Las claves se guardan en <code>backend/.env</code> y nunca salen de tu equipo.
            Los modelos de APInex se verifican contra su catálogo público: solo se
            muestran los que siguen siendo gratuitos y aceptan herramientas.
          </p>
        </div>

        <div className="border-t border-bg-border" />

        {/* Connection */}
        <div>
          <h3 className="text-fg-muted font-semibold mb-2 flex items-center gap-1.5">
            <Info size={12} />
            Conexión
          </h3>
          <div className="space-y-1.5">
            <Row label="Estado" value={status ? 'Conectado' : 'Desconectado'} />
            <Row label="Max Steps" value={String(status?.max_steps ?? '—')} />
            <Row label="Approval" value={status?.approval || '—'} />
          </div>
        </div>

        <div className="border-t border-bg-border" />

        {/* Workspace */}
        <div>
          <h3 className="text-fg-muted font-semibold mb-2 flex items-center gap-1.5">
            <FolderOpen size={12} />
            Workspace
          </h3>
          {workspace ? (
            <div className="space-y-1.5">
              <Row label="Root" value={workspace.root} />
              <Row label="Branch" value={workspace.branch} />
              <Row
                label="Status"
                value={
                  workspace.status === 'clean'
                    ? 'Clean ✓'
                    : `${workspace.status.slice(0, 60)}...`
                }
              />
            </div>
          ) : (
            <p className="text-fg-dim">Cargando...</p>
          )}

          {/* Workspace setter */}
          <div className="mt-2 flex gap-1">
            <input
              type="text"
              value={workspaceInput}
              onChange={(e) => setWorkspaceInput(e.target.value)}
              placeholder="Ruta del proyecto..."
              className="flex-1 min-w-0 px-2 py-1.5 rounded text-sm bg-bg-surface border border-bg-border text-fg placeholder-fg-dim/50 outline-none focus:border-accent-muted transition-colors"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && workspaceInput.trim() && !settingWorkspace) {
                  handleSetWorkspace()
                }
              }}
            />
            <button
              onClick={handleOpenFolderPicker}
              title="Seleccionar carpeta"
              className="px-2 py-1.5 rounded text-sm bg-bg-surface border border-bg-border text-fg-muted hover:text-fg hover:border-accent-muted/30 transition-colors"
            >
              <Search size={14} />
            </button>
            <button
              onClick={handleSetWorkspace}
              disabled={!workspaceInput.trim() || settingWorkspace}
              className="px-2 py-1.5 rounded text-sm font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {settingWorkspace ? '...' : 'Cambiar'}
            </button>
          </div>
        </div>

        <div className="border-t border-bg-border" />

        {/* Session */}
        <div>
          <h3 className="text-fg-muted font-semibold mb-2">Sesión</h3>
          <Row label="ID" value={status?.session_id?.slice(0, 20) || '—'} />
        </div>

        <div className="border-t border-bg-border" />
        <p className="text-fg-dim leading-relaxed">
          Relay v0.3.0 · Agentes cloud (DeepSeek, APInex) + Ollama Cloud + MCP.
          Configura claves y modelos desde este panel.
        </p>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-start gap-2">
      <span className="text-fg-dim whitespace-nowrap">{label}</span>
      <span className="text-fg text-right break-all max-w-[180px]">{value}</span>
    </div>
  )
}

const TIER_META: Record<ModelTier, {
  label: string
  hint: string
  icon: typeof Brain
  badge: string
}> = {
  deep: {
    label: 'Avanzados',
    hint: 'Tareas agenticas de varios pasos',
    icon: Brain,
    badge: 'bg-purple-900/40 text-purple-300 border-purple-800/50',
  },
  fast: {
    label: 'Rápidos',
    hint: 'Tareas cortas y de complejidad media',
    icon: Zap,
    badge: 'bg-emerald-900/40 text-emerald-300 border-emerald-800/50',
  },
}

function TierBadge({ tier }: { tier: ModelTier }) {
  const meta = TIER_META[tier]
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium border ${meta.badge}`}>
      {meta.label}
    </span>
  )
}

function TierGroup({
  tier,
  models,
  activeModel,
  switching,
  onSelect,
}: {
  tier: ModelTier
  models: ModelInfo[]
  activeModel: string
  switching: boolean
  onSelect: (name: string) => void
}) {
  if (models.length === 0) return null
  const meta = TIER_META[tier]
  const Icon = meta.icon
  return (
    <div className="mb-3">
      <p className="text-fg-dim text-xs uppercase tracking-wider mb-0.5 flex items-center gap-1.5">
        <Icon size={12} /> {meta.label}
      </p>
      <p className="text-fg-dim/60 text-[11px] mb-1.5">{meta.hint}</p>
      <div className="space-y-0.5">
        {models.map((m) => (
          <ModelOption
            key={m.name}
            model={m}
            active={m.name === activeModel}
            loading={switching}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  )
}

function ModelOption({
  model,
  active,
  loading,
  onSelect,
}: {
  model: ModelInfo
  active: boolean
  loading: boolean
  onSelect: (name: string) => void
}) {
  return (
    <div className={`flex items-center px-3 py-2 rounded text-sm transition-colors ${
      active
        ? 'bg-accent-muted/20 text-accent border border-accent-muted/30'
        : 'text-fg-muted hover:bg-bg-hover border border-transparent'
    }`}>
      <button
        onClick={() => onSelect(model.name)}
        disabled={loading || active}
        className="flex-1 flex items-center justify-between min-w-0 disabled:opacity-60 text-left"
        title={`${model.name} · ${model.context_limit.toLocaleString()} tokens de contexto`}
      >
        <span className="font-medium truncate mr-2">{model.label || model.name}</span>
        <span className="text-xs text-fg-dim whitespace-nowrap">{model.provider_label}</span>
      </button>
    </div>
  )
}

function ProviderCard({
  provider,
  saving,
  onSave,
}: {
  provider: ProviderInfo
  saving: boolean
  onSave: (name: string, apiKey: string) => Promise<void>
}) {
  const [key, setKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const needsKey = provider.requires_key

  const submit = async () => {
    const value = key.trim()
    if (!value) return
    setError(null)
    try {
      await onSave(provider.name, value)
      setKey('')
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'No se pudo guardar la clave')
    }
  }

  const disconnect = async () => {
    setError(null)
    try {
      await onSave(provider.name, '')
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'No se pudo desconectar')
    }
  }

  return (
    <div className="px-3 py-2 rounded bg-bg-surface/60 border border-bg-border">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-fg truncate">{provider.label}</span>
        <span className="flex items-center gap-1 text-[11px] whitespace-nowrap">
          {provider.configured ? (
            <span className="flex items-center gap-1 text-emerald-400">
              <Check size={11} /> {provider.models.length} modelos
            </span>
          ) : (
            <span className="text-amber-400">Sin configurar</span>
          )}
        </span>
      </div>

      <p className="text-[11px] text-fg-dim/70 truncate mt-0.5" title={provider.base_url}>
        {provider.base_url}
      </p>

      {needsKey && (
        <div className="mt-1.5 flex gap-1">
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
            placeholder={provider.configured ? 'Reemplazar clave…' : `${provider.env_key}`}
            disabled={saving}
            autoComplete="off"
            className="flex-1 min-w-0 px-2 py-1 rounded text-xs bg-bg-base border border-bg-border text-fg placeholder-fg-dim/50 outline-none focus:border-accent-muted transition-colors"
          />
          <button
            onClick={submit}
            disabled={!key.trim() || saving}
            className="px-2 py-1 rounded text-xs font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? '...' : 'Guardar'}
          </button>
          {provider.configured && (
            <button
              onClick={disconnect}
              disabled={saving}
              title="Eliminar la clave"
              className="px-2 py-1 rounded text-xs bg-bg-base border border-bg-border text-fg-dim hover:text-red-400 hover:border-red-900/50 disabled:opacity-50 transition-colors"
            >
              Quitar
            </button>
          )}
        </div>
      )}

      {provider.docs_url && !provider.configured && (
        <a
          href={provider.docs_url}
          target="_blank"
          rel="noreferrer"
          className="inline-block mt-1 text-[11px] text-accent hover:underline"
        >
          Obtener clave →
        </a>
      )}

      {error && <p className="mt-1 text-[11px] text-red-400 break-all">{error}</p>}
    </div>
  )
}
