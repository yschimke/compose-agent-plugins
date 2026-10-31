export type Finding = {
  level: string
  type: string
  message: string
  view?: string
}

export type PreviewShot = {
  id: string
  uri?: string
  label: string
  pngPath?: string
  /** A copy of the previous render's PNG, taken before this one replaced it. */
  beforePath?: string
  width?: number
  height?: number
  sha?: string
  changed?: boolean
  findings: Finding[]
  error?: string
  /** Its picture predates the latest edit: it is re-rendered when the person selects it. */
  stale?: boolean
  /** Edit to pixels, in milliseconds, when this render followed an edit. */
  ms?: number
}

export type RenderState = {
  file?: string
  status: 'idle' | 'rendering' | 'done' | 'error'
  message?: string
  /** Who produced the shots: this mod over MCP, the CLI, or the agent's own call. */
  via?: 'mcp' | 'cli' | 'agent'
  at?: number
  shots: PreviewShot[]
}

export type SimState = {
  status: 'off' | 'starting' | 'running' | 'reloading' | 'error'
  simulator?: string
  target?: string
  package?: string
  screenshot?: string
  /** Bumped per screenshot so a redraw reads the new file under the same name. */
  frame: number
  message?: string
  at?: number
}

export type PaneUi = {
  tab: 'previews' | 'app'
  index: number
  show: 'after' | 'before'
}

declare module 'claude-code' {
  interface PluginState {
    'compose-preview-pane': {
      render: Shaped<RenderState>
      sim: Shaped<SimState>
      ui: Shaped<PaneUi>
      /** The MCP server that answered last, or 'cli'. */
      backend: string
      /** A scratch folder for before-copies and simulator screenshots. */
      scratch: string
    }
  }
}
