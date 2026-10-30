import { useState, useEffect, useCallback } from 'react'
import {
  Puzzle, PlugZap, Plug, ChevronDown, ChevronRight, Settings, Check, X,
  Eye, EyeOff, ExternalLink, RefreshCw, Loader2,
} from 'lucide-react'
import { twMerge } from 'tailwind-merge'
import {
  fetchIntegrationsCatalog, fetchIntegrations, enableIntegration, disableIntegration,
  type CatalogIntegration, type IntegrationRecord, type ConfigField,
} from '../api/client'

interface IntegrationsPanelProps {
  onRefresh?: () => void
}

interface IntegrationWithStatus extends IntegrationRecord {
  status: 'idle' | 'connecting' | 'connected' | 'error' | 'disabling'
  errorMessage?: string
  toolList?: { name: string; description: string }[]
  expanded?: boolean
  showConfigure?: boolean
}

export function IntegrationsPanel({ onRefresh }: IntegrationsPanelProps) {
  const [catalog, setCatalog] = useState<CatalogIntegration[]>([])
  const [integrations, setIntegrations] = useState<IntegrationWithStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cat, recs] = await Promise.all([
        fetchIntegrationsCatalog(),
        fetchIntegrations(),
      ])
      setCatalog(cat)

      // Merge records with catalog info and add local UI state
      const merged: IntegrationWithStatus[] = recs.map((rec) => ({
        ...rec,
        // If enabled AND MCP server is already connected (set by backend), show as connected
        status: rec.enabled && rec.connected
          ? 'connected' as const
          : rec.error
            ? 'error' as const
            : 'idle' as const,
        expanded: false,
        showConfigure: false,
        toolList: rec.tools ?? [],
        errorMessage: rec.error,
      }))
      setIntegrations(merged)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar integraciones')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const catalogMap = new Map(catalog.map((c) => [c.server_name, c]))

  const handleToggle = async (integration: IntegrationWithStatus) => {
    if (integration.status === 'connecting' || integration.status === 'disabling') return

    if (integration.enabled) {
      // Disable
      setIntegrations((prev) =>
        prev.map((i) =>
          i.server_name === integration.server_name ? { ...i, status: 'disabling' as const } : i
        )
      )
      try {
        const result = await disableIntegration(integration.server_name)
        setIntegrations((prev) =>
          prev.map((i) =>
            i.server_name === integration.server_name
              ? { ...i, enabled: false, status: 'idle' as const, toolList: [] }
              : i
          )
        )
        onRefresh?.()
      } catch (err) {
        setIntegrations((prev) =>
          prev.map((i) =>
            i.server_name === integration.server_name
              ? { ...i, status: 'idle' as const, errorMessage: err instanceof Error ? err.message : 'Error' }
              : i
          )
        )
      }
    } else {
      // Enable — check if it needs API keys
      const catItem = catalogMap.get(integration.server_name)
      const requiredFields = catItem?.config_fields?.filter((f) => f.required) ?? []

      if (requiredFields.length > 0) {
        // Show configure modal/expand
        setIntegrations((prev) =>
          prev.map((i) =>
            i.server_name === integration.server_name ? { ...i, showConfigure: true } : i
          )
        )
        return
      }

      // Enable directly
      await doEnable(integration, catItem)
    }
  }

  const doEnable = async (integration: IntegrationWithStatus, catItem?: CatalogIntegration, apiKeys?: Record<string, string>, config?: Record<string, unknown>) => {
    setIntegrations((prev) =>
      prev.map((i) =>
        i.server_name === integration.server_name ? { ...i, status: 'connecting' as const, errorMessage: undefined } : i
      )
    )
    try {
      const result = await enableIntegration(integration.server_name, apiKeys, config)
      setIntegrations((prev) =>
        prev.map((i) =>
          i.server_name === integration.server_name
            ? {
                ...i,
                enabled: true,
                status: result.status === 'connected' ? 'connected' as const : 'error' as const,
                toolList: result.tools ?? [],
                errorMessage: result.error,
                showConfigure: false,
              }
            : i
        )
      )
      onRefresh?.()
    } catch (err) {
      setIntegrations((prev) =>
        prev.map((i) =>
          i.server_name === integration.server_name
            ? { ...i, status: 'error' as const, errorMessage: err instanceof Error ? err.message : 'Error' }
            : i
        )
      )
    }
  }

  const handleConfigureSubmit = async (integration: IntegrationWithStatus, apiKeys: Record<string, string>, config?: Record<string, unknown>) => {
    const catItem = catalogMap.get(integration.server_name)
    await doEnable(integration, catItem, apiKeys, config)
  }

  const toggleExpanded = (serverName: string) => {
    setIntegrations((prev) =>
      prev.map((i) =>
        i.server_name === serverName ? { ...i, expanded: !i.expanded } : i
      )
    )
  }

  const toggleConfigure = (serverName: string) => {
    setIntegrations((prev) =>
      prev.map((i) =>
        i.server_name === serverName ? { ...i, showConfigure: !i.showConfigure } : i
      )
    )
  }

  const hasApiKeyConfigured = (integration: IntegrationWithStatus): boolean => {
    const catItem = catalogMap.get(integration.server_name)
    if (!catItem?.config_fields) return false
    return catItem.config_fields.some((field) => {
      const key = `_has_${field.env_var ?? field.name}`
      return integration[key] === true
    })
  }

  if (loading && integrations.length === 0) {
    return (
      <div className="flex flex-col h-full">
        <PanelHeader />
        <div className="flex-1 flex items-center justify-center">
          <Loader2 size={20} className="text-fg-dim animate-spin" />
          <span className="ml-2 text-sm text-fg-dim">Cargando integraciones...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader onRefresh={loadAll} />

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {error && (
          <div className="px-3 py-2 rounded-md bg-danger/10 border border-danger/30 text-danger text-sm">
            {error}
          </div>
        )}

        {integrations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <Puzzle size={32} className="text-fg-dim/30 mb-3" />
            <p className="text-base text-fg-muted mb-1">Sin integraciones disponibles</p>
            <p className="text-sm text-fg-dim">No se encontraron integraciones en el catálogo.</p>
          </div>
        ) : (
          integrations.map((integration) => {
            const catItem = catalogMap.get(integration.server_name)
            const isActive = integration.enabled
            const isBusy = integration.status === 'connecting' || integration.status === 'disabling'
            const isConnected = integration.status === 'connected'
            const hasError = integration.status === 'error'
            const toolCount = integration.toolList?.length ?? 0

            return (
              <div
                key={integration.server_name}
                className={twMerge(
                  'rounded-lg border transition-colors',
                  isConnected
                    ? 'border-emerald-800/30 bg-emerald-950/10'
                    : hasError
                      ? 'border-red-800/30 bg-red-950/10'
                      : isActive
                        ? 'border-accent-muted/20 bg-bg-surface/50'
                        : 'border-bg-border bg-bg-surface/30'
                )}
              >
                {/* Main card */}
                <div className="p-3">
                  {/* Title row */}
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={twMerge(
                        'p-1.5 rounded-md flex-shrink-0',
                        isConnected
                          ? 'bg-emerald-900/30 text-emerald-400'
                          : 'bg-bg-hover text-fg-muted'
                      )}>
                        <Puzzle size={16} />
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-base font-semibold text-fg truncate flex items-center gap-1.5">
                          {integration.display_name || integration.server_name}
                          {integration.preflight && (
                            <span
                              className={twMerge(
                                'inline-flex items-center gap-0.5 px-1.5 py-0 rounded text-[10px] font-medium flex-shrink-0',
                                integration.preflight.available
                                  ? 'bg-emerald-900/30 text-emerald-400'
                                  : 'bg-red-900/30 text-red-400'
                              )}
                              title={
                                integration.preflight.available
                                  ? `${integration.preflight.command} disponible`
                                  : `${integration.preflight.command} no encontrado`
                              }
                            >
                              <span className={twMerge(
                                'w-1.5 h-1.5 rounded-full',
                                integration.preflight.available ? 'bg-emerald-400' : 'bg-red-400'
                              )} />
                              {integration.preflight.command}
                            </span>
                          )}
                        </h3>
                        {catItem?.tools_description && (
                          <p className="text-xs text-fg-dim mt-0.5 font-mono">
                            {catItem.tools_description}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Toggle switch */}
                    <button
                      onClick={() => handleToggle(integration)}
                      disabled={isBusy}
                      className={twMerge(
                        'relative w-9 h-5 rounded-full transition-colors flex-shrink-0',
                        'disabled:opacity-50 disabled:cursor-wait',
                        isActive ? 'bg-accent-muted' : 'bg-bg-border'
                      )}
                      title={isActive ? 'Desactivar' : 'Activar'}
                    >
                      <span
                        className={twMerge(
                          'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow-sm',
                          isActive && 'translate-x-4'
                        )}
                      />
                    </button>
                  </div>

                  {/* Description */}
                  <p className="text-sm text-fg-muted leading-relaxed mb-2">
                    {catItem?.description || integration.description || 'Sin descripción'}
                  </p>

                  {/* Status bar */}
                  <div className="flex items-center gap-2 text-sm">
                    {isBusy ? (
                      <span className="flex items-center gap-1 text-warning">
                        <Loader2 size={11} className="animate-spin" />
                        {integration.status === 'connecting' ? 'Conectando...' : 'Desactivando...'}
                      </span>
                    ) : isConnected ? (
                      <span className="flex items-center gap-1 text-success">
                        <PlugZap size={11} />
                        Conectado · {toolCount} tool{toolCount !== 1 ? 's' : ''}
                      </span>
                    ) : hasError ? (
                      <span className="flex items-center gap-1 text-danger">
                        <Plug size={11} />
                        Error · {integration.errorMessage || 'Error de conexión'}
                      </span>
                    ) : isActive ? (
                      <span className="flex items-center gap-1 text-accent">
                        <Loader2 size={11} className="animate-spin" />
                        Conectando...
                      </span>
                    ) : (
                      <span className="text-fg-dim">Inactivo</span>
                    )}

                    {isActive && (
                      <>
                        <span className="text-fg-dim">·</span>
                        <button
                          onClick={() => toggleExpanded(integration.server_name)}
                          className="flex items-center gap-0.5 text-fg-dim hover:text-fg transition-colors"
                        >
                          {integration.expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                          Detalles
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Expanded details */}
                {integration.expanded && (
                  <div className="border-t border-bg-border px-3 py-2 space-y-2">
                    {integration.toolList && integration.toolList.length > 0 && (
                      <div>
                        <p className="text-xs text-fg-dim uppercase tracking-wider mb-1">
                          Herramientas disponibles
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {integration.toolList.map((tool) => (
                            <span
                              key={tool.name}
                              className="px-1.5 py-0.5 rounded text-xs font-mono bg-accent-muted/10 text-accent border border-accent-muted/20"
                              title={tool.description}
                            >
                              {tool.name}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Config button — only for integrations with API key fields */}
                    {catItem && catItem.config_fields && catItem.config_fields.length > 0 && (
                      <button
                        onClick={() => toggleConfigure(integration.server_name)}
                        className="flex items-center gap-1 text-sm text-fg-dim hover:text-fg transition-colors"
                      >
                        <Settings size={11} />
                        {integration.showConfigure ? 'Cancelar' : 'Configurar API keys'}
                      </button>
                    )}
                  </div>
                )}

                {/* Configure modal inline */}
                {integration.showConfigure && catItem && (
                  <ConfigureForm
                    integration={integration}
                    catalogItem={catItem}
                    hasExistingKeys={hasApiKeyConfigured(integration)}
                    onSubmit={(apiKeys, config) => handleConfigureSubmit(integration, apiKeys, config)}
                    onCancel={() => toggleConfigure(integration.server_name)}
                  />
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

// ── Sub-components ──────────────────────────────────────────────

function PanelHeader({ onRefresh }: { onRefresh?: () => void }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-b border-bg-border bg-bg-surface/50">
      <div className="flex items-center gap-2">
        <Puzzle size={15} className="text-fg-muted" />
        <span className="text-sm font-semibold text-fg-muted uppercase tracking-wider">
          Integraciones
        </span>
      </div>
      {onRefresh && (
        <button onClick={onRefresh} className="btn-ghost p-1.5" title="Refrescar">
          <RefreshCw size={14} />
        </button>
      )}
    </div>
  )
}

function ConfigureForm({
  integration, catalogItem, hasExistingKeys, onSubmit, onCancel,
}: {
  integration: IntegrationWithStatus
  catalogItem: CatalogIntegration
  hasExistingKeys: boolean
  onSubmit: (apiKeys: Record<string, string>, config: Record<string, unknown>) => void
  onCancel: () => void
}) {
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)

  const allFields = catalogItem.config_fields ?? []
  const apiKeyFields = allFields.filter((f) => f.type === 'api_key')
  const stringFields = allFields.filter((f) => f.type === 'string')
  const hasApiKeyFields = apiKeyFields.length > 0

  const handleSubmit = async () => {
    // Collect API keys (go to .env) and string config (go to SQLite)
    const apiKeys: Record<string, string> = {}
    const config: Record<string, unknown> = {}

    for (const field of allFields) {
      const key = field.env_var || field.name
      const val = fieldValues[key]?.trim()
      if (!val) continue

      if (field.type === 'api_key') {
        apiKeys[key] = val
      } else if (field.type === 'string') {
        config[field.name] = val
      }
    }

    // If no keys entered but integration has existing keys, reuse them
    if (Object.keys(apiKeys).length === 0 && hasExistingKeys && !hasApiKeyFields) {
      setSaving(true)
      try {
        const result = await enableIntegration(integration.server_name)
        window.location.reload()
      } catch {
        setSaving(false)
      }
      return
    }

    setSaving(true)
    await onSubmit(apiKeys, config)
    setSaving(false)
  }

  const description = hasApiKeyFields
    ? 'Completa los campos requeridos para activar esta integración:'
    : 'Configura los parámetros para esta integración:'

  return (
    <div className="border-t border-bg-border px-3 py-3 space-y-3 bg-bg-base/30">
      <p className="text-sm text-fg-muted font-medium">{description}</p>

      {allFields.map((field) => {
        const key = field.env_var || field.name
        const isVisible = showKeys[key]
        const isApiKey = field.type === 'api_key'

        return (
          <div key={key}>
            <label className="block text-sm text-fg-dim mb-1">
              {field.label}
              {field.required && <span className="text-danger ml-0.5">*</span>}
            </label>
            <div className="flex gap-1">
              <div className="relative flex-1">
                <input
                  type={isApiKey && !isVisible ? 'password' : 'text'}
                  value={fieldValues[key] ?? ''}
                  onChange={(e) => setFieldValues((prev) => ({ ...prev, [key]: e.target.value }))}
                  placeholder={field.placeholder || `Ingresa ${field.label.toLowerCase()}`}
                  className="w-full px-2.5 py-1.5 rounded text-sm bg-bg-surface border border-bg-border text-fg placeholder-fg-dim/50 outline-none focus:border-accent-muted transition-colors pr-7"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !saving) handleSubmit()
                  }}
                />
                {isApiKey && (
                  <button
                    type="button"
                    onClick={() => setShowKeys((prev) => ({ ...prev, [key]: !prev[key] }))}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 text-fg-dim hover:text-fg transition-colors"
                  >
                    {isVisible ? <EyeOff size={12} /> : <Eye size={12} />}
                  </button>
                )}
              </div>
            </div>
          </div>
        )
      })}

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={handleSubmit}
          disabled={saving}
          className="px-3 py-1.5 rounded text-sm font-medium bg-accent text-white hover:bg-accent-dim disabled:opacity-50 disabled:cursor-wait transition-colors flex items-center gap-1"
        >
          {saving ? (
            <><Loader2 size={11} className="animate-spin" /> Conectando...</>
          ) : (
            <><Check size={11} /> Activar</>
          )}
        </button>
        <button
          onClick={onCancel}
          disabled={saving}
          className="px-3 py-1.5 rounded text-sm font-medium text-fg-muted hover:text-fg bg-bg-surface border border-bg-border hover:bg-bg-hover disabled:opacity-50 transition-colors flex items-center gap-1"
        >
          <X size={11} /> Cancelar
        </button>
      </div>
    </div>
  )
}
