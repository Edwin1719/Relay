import { useState, useEffect, useCallback, useRef } from 'react'
import { Folder, File, ChevronRight, ChevronDown, RefreshCw, FolderOpen, FolderInput, Search } from 'lucide-react'
import { twMerge } from 'tailwind-merge'
import { fetchFiles, readFile, pickFolder, fetchWorkspace, type FileEntry, type WorkspaceInfo } from '../api/client'

interface FileExplorerProps {
  onSelectFile?: (path: string, content: string) => void
  projectLoaded?: boolean
  onSetWorkspace?: (path: string) => Promise<{ status: string; root: string; branch: string; cwd?: string } | void>
  onResetProject?: () => void
}

interface TreeNode {
  name: string
  path: string
  type: 'file' | 'dir'
  children?: TreeNode[]
  expanded?: boolean
}

function buildTree(entries: FileEntry[], parentPath: string): TreeNode[] {
  return entries
    .filter((e) => !e.name.startsWith('.') || e.name === '.gitignore')
    .map((e) => ({
      name: e.name,
      path: e.path,
      type: e.type,
      children: e.type === 'dir' ? [] : undefined,
      expanded: false,
    }))
    .sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
}

async function loadChildren(node: TreeNode): Promise<TreeNode[]> {
  try {
    const { entries } = await fetchFiles(node.path)
    return buildTree(entries, node.path)
  } catch {
    return []
  }
}

export function FileExplorer({ onSelectFile, projectLoaded, onSetWorkspace, onResetProject }: FileExplorerProps) {
  const [rootNodes, setRootNodes] = useState<TreeNode[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [pathInput, setPathInput] = useState('')
  const [loadingProject, setLoadingProject] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [workspaceRoot, setWorkspaceRoot] = useState<string>('')

  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadRoot = useCallback(async () => {
    setLoading(true)
    try {
      const [files, ws] = await Promise.all([
        fetchFiles('.'),
        fetchWorkspace().catch(() => null as WorkspaceInfo | null),
      ])
      setRootNodes(buildTree(files.entries, '.'))
      if (ws) setWorkspaceRoot(ws.root)
    } catch {
      setRootNodes([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (projectLoaded) {
      loadRoot()
    }
  }, [projectLoaded, loadRoot])

  const handleLoadProject = async () => {
    if (!pathInput.trim() || !onSetWorkspace || loadingProject) return
    setLoadError(null)
    setLoadingProject(true)
    try {
      const result = await onSetWorkspace(pathInput.trim())
      setPathInput('')
      // Verify the workspace root matches what was requested
      if (result && result.root) {
        console.log('Workspace set response:', result)
        setWorkspaceRoot(result.root)
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Error al cargar proyecto')
    } finally {
      setLoadingProject(false)
    }
  }


  const handleOpenFolderPicker = async () => {
    setLoadError(null)
    try {
      const result = await pickFolder()
      if (!result.canceled && result.path) {
        setPathInput(result.path)
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Error al abrir selector de carpeta')
    }
  }

  const toggleNode = async (node: TreeNode, depth: number) => {
    if (node.type === 'file') {
      setSelectedPath(node.path)
      try {
        const { content } = await readFile(node.path)
        onSelectFile?.(node.path, content)
      } catch {
        onSelectFile?.(node.path, 'Error reading file')
      }
      return
    }

    setRootNodes((prev) => toggleNodeInTree(prev, node.path))
  }

  const renderNode = (node: TreeNode, depth: number) => {
    const isExpanded = node.expanded
    const isSelected = node.path === selectedPath

    return (
      <div key={node.path}>
        <button
          onClick={() => toggleNode(node, depth)}
          className={twMerge(
            'w-full flex items-center gap-2 px-3 py-1.5 text-base rounded hover:bg-bg-hover transition-colors text-left',
            isSelected && 'bg-accent-muted/20 text-accent',
            !isSelected && 'text-fg-muted hover:text-fg'
          )}
          style={{ paddingLeft: `${depth * 20 + 12}px` }}
        >
          {node.type === 'dir' ? (
            <>
              {isExpanded ? (
                <ChevronDown size={14} className="flex-shrink-0" />
              ) : (
                <ChevronRight size={14} className="flex-shrink-0" />
              )}
              {isExpanded ? (
                <FolderOpen size={16} className="flex-shrink-0 text-warning" />
              ) : (
                <Folder size={16} className="flex-shrink-0 text-warning" />
              )}
            </>
          ) : (
            <>
              <span className="w-3 flex-shrink-0" />
              <File size={16} className="flex-shrink-0 text-fg-dim" />
            </>
          )}
          <span className="truncate">{node.name}</span>
        </button>

        {node.type === 'dir' && isExpanded && node.children && (
          <DirectoryContents
            node={node}
            depth={depth + 1}
            renderItem={renderNode}
          />
        )}
      </div>
    )
  }

  // ── Landing screen: no project loaded yet ──
  if (!projectLoaded) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center justify-between px-3 py-2 border-b border-bg-border bg-bg-surface/50">
          <span className="text-xs font-semibold text-fg-muted uppercase tracking-wider">Explorer</span>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          <FolderInput size={40} className="text-fg-dim/40 mb-4" />
          <h2 className="text-sm font-semibold text-fg mb-1">Cargar proyecto</h2>
          <p className="text-xs text-fg-dim mb-4 max-w-[200px] leading-relaxed">
            Ingresa la ruta de la carpeta del proyecto que quieres analizar.
          </p>
          <div className="w-full flex flex-col gap-1.5">
            <div className="flex gap-1.5">
              <input
                type="text"
                value={pathInput}
                onChange={(e) => setPathInput(e.target.value)}
                placeholder="C:/ruta/del/proyecto"
                className="flex-1 min-w-0 px-3 py-2 rounded text-xs bg-bg-surface border border-bg-border text-fg placeholder-fg-dim/50 outline-none focus:border-accent-muted transition-colors"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && pathInput.trim() && !loadingProject) {
                    handleLoadProject()
                  }
                }}
              />
              <button
                onClick={handleLoadProject}
                disabled={!pathInput.trim() || loadingProject}
                className="px-4 py-2 rounded text-xs font-medium bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
              >
                {loadingProject ? 'Cargando...' : 'Cargar'}
              </button>
            </div>
            <button
              onClick={handleOpenFolderPicker}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded text-xs font-medium text-fg-muted hover:text-fg bg-bg-surface border border-bg-border hover:border-accent-muted/30 transition-colors"
            >
              <Search size={12} />
              Seleccionar carpeta
            </button>
          </div>
          {loadError && (
            <p className="text-danger text-xs mt-3 text-left w-full break-all">{loadError}</p>
          )}
        </div>
      </div>
    )
  }

  // ── File tree: project loaded ──
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-bg-border bg-bg-surface/50">
        <div className="flex items-center gap-2 min-w-0 overflow-hidden">
          <FolderOpen size={14} className="text-fg-muted flex-shrink-0" />
          <span className="text-sm text-fg-muted truncate" title={workspaceRoot || 'Explorer'}>
            {workspaceRoot ? workspaceRoot.split(/[/\\]/).pop() : 'Explorer'}
          </span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button onClick={onResetProject} className="btn-ghost p-1.5 text-xs text-fg-dim hover:text-fg" title="Cambiar proyecto">
            <FolderInput size={14} />
          </button>
          <button onClick={loadRoot} className="btn-ghost p-1" title="Refresh">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-0.5">
        {loading && rootNodes.length === 0 ? (
          <div className="text-sm text-fg-dim text-center py-6">Cargando...</div>
        ) : rootNodes.length === 0 ? (
          <div className="text-sm text-fg-dim text-center py-6">Sin archivos</div>
        ) : (
          rootNodes.map((node) => renderNode(node, 0))
        )}
      </div>
    </div>
  )
}

function toggleNodeInTree(nodes: TreeNode[], targetPath: string): TreeNode[] {
  return nodes.map((node) => {
    if (node.path === targetPath && node.type === 'dir') {
      return { ...node, expanded: !node.expanded }
    }
    if (node.children) {
      return { ...node, children: toggleNodeInTree(node.children, targetPath) }
    }
    return node
  })
}

function DirectoryContents({
  node,
  depth,
  renderItem,
}: {
  node: TreeNode
  depth: number
  renderItem: (node: TreeNode, depth: number) => React.ReactNode
}) {
  const [children, setChildren] = useState<TreeNode[]>(node.children || [])
  const [loading, setLoading] = useState(children.length === 0)

  useEffect(() => {
    if (children.length === 0) {
      loadChildren(node).then((result) => {
        setChildren(result)
        setLoading(false)
        node.children = result
      })
    }
  }, [node, children.length])

  if (loading) {
    return (
      <div className="text-sm text-fg-dim text-center py-1" style={{ paddingLeft: `${depth * 20 + 12}px` }}>
        Cargando...
      </div>
    )
  }

  return <>{children.map((child) => renderItem(child, depth))}</>
}
