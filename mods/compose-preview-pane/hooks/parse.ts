// Pure helpers: reading compose-preview's MCP and CLI answers, which this mod
// treats as loosely shaped JSON so a server or CLI release that adds fields
// (or moves one) degrades to "no findings" rather than a failed hook.

import type { Finding, PreviewShot } from '../types'

type Json = unknown
type Obj = Record<string, unknown>

const isObj = (v: Json): v is Obj =>
  typeof v === 'object' && v !== null && !Array.isArray(v)
const str = (v: Json): string | undefined =>
  typeof v === 'string' ? v : undefined
const num = (v: Json): number | undefined =>
  typeof v === 'number' ? v : undefined

export const isKotlin = (path: string) => /\.kts?$/.test(path) && !path.endsWith('.gradle.kts')

/** An MCP result's payload: structuredContent, else the first text block that parses. */
export function mcpPayload(result: {
  content: readonly { type: string; text?: string }[]
  structuredContent?: unknown
}): Json {
  if (result.structuredContent !== undefined) return result.structuredContent
  for (const block of result.content) {
    if (block.type !== 'text' || block.text === undefined) continue
    try {
      return JSON.parse(block.text)
    } catch {
      // A prose block; keep looking.
    }
  }

  return undefined
}

/** find_previews_for_file: a list of URIs, or of objects carrying `uri`, possibly wrapped. */
export function previewUris(payload: Json): string[] {
  const list = Array.isArray(payload)
    ? payload
    : isObj(payload)
      ? (payload.previews ?? payload.uris ?? payload.results ?? [])
      : []
  if (!Array.isArray(list)) return []

  return list.flatMap(item => {
    const uri = str(item) ?? (isObj(item) ? str(item.uri) : undefined)
    return uri === undefined ? [] : [uri]
  })
}

/**
 * A preview's short name from its id or URI: the function, then the multi-preview variant the
 * id appends after `_` (`GreetingScreenPreview · Devices - Large Round`).
 */
export function labelOf(id: string): string {
  let tail = id.split(/[/#?]/).filter(Boolean).pop() ?? id
  try {
    tail = decodeURIComponent(tail)
  } catch {
    // Not percent-encoded.
  }
  const name = tail.split('.').pop() ?? tail
  const at = name.indexOf('_')
  return at > 0 ? `${name.slice(0, at)} · ${name.slice(at + 1)}` : name
}

/** The functions a Kotlin source annotates with a `@…Preview`, in order. */
export function previewFunctions(source: string): string[] {
  const names = [...source.matchAll(/@\w*Preview\w*\b[\s\S]*?\bfun\s+([A-Za-z_]\w*)/g)].map(m => m[1] ?? '')
  return [...new Set(names.filter(Boolean))]
}

/** The first `findings` array anywhere in the value, as a11y/atf and the CLI's extension carry it. */
export function findingsIn(value: Json, depth = 0): Finding[] {
  if (depth > 6) return []
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findingsIn(item, depth + 1)
      if (found.length > 0) return found
    }
    return []
  }
  if (!isObj(value)) return []
  if (Array.isArray(value.findings)) {
    return value.findings.filter(isObj).map(f => ({
      level: str(f.level) ?? 'INFO',
      type: str(f.type) ?? str(f.checkName) ?? 'finding',
      message: str(f.message) ?? '',
      view: str(f.viewDescription) ?? str(f.view),
    }))
  }
  for (const child of Object.values(value)) {
    const found = findingsIn(child, depth + 1)
    if (found.length > 0) return found
  }

  return []
}

/** render_preview with inline=false. */
export function renderResult(payload: Json): Pick<PreviewShot, 'pngPath' | 'sha' | 'changed' | 'width' | 'height'> {
  const p = isObj(payload) ? payload : {}
  return {
    pngPath: str(p.pngPath),
    sha: str(p.sha256),
    changed: typeof p.changed === 'boolean' ? p.changed : undefined,
    width: num(p.width) ?? num(p.widthPx),
    height: num(p.height) ?? num(p.heightPx),
  }
}

/**
 * The rows of `compose-preview a11y --json` (or `show --json`; both are compose-preview-show/v2)
 * for one source file.
 */
export function cliShots(stdout: string, file: string): PreviewShot[] {
  let envelope: Json
  try {
    envelope = JSON.parse(stdout)
  } catch {
    return []
  }
  const rows = isObj(envelope) && Array.isArray(envelope.previews) ? envelope.previews : []

  return rows.filter(isObj).flatMap(row => {
    const source = str(row.sourceFile)
    if (source === undefined || !sameSource(file, source)) return []
    const capture = Array.isArray(row.captures) ? row.captures.find(isObj) : undefined
    const id = str(row.id) ?? 'preview'

    return [{
      id,
      label: labelOf(id),
      pngPath: capture ? str(capture.pngPath) : undefined,
      sha: capture ? str(capture.sha256) : undefined,
      changed: capture && typeof capture.changed === 'boolean' ? capture.changed : undefined,
      findings: findingsIn(row.dataExtensions),
    }]
  })
}

/** sourceFile is module-relative (`src/main/kotlin/Stop.kt`) or a bare name. */
export function sameSource(file: string, source: string): boolean {
  const norm = (p: string) => p.replace(/\\/g, '/')
  const f = norm(file)
  const s = norm(source)
  return f === s || f.endsWith(`/${s}`) || s.split('/').pop() === f.split('/').pop()
}

/** A Gradle path for the module that holds `file`, from the nearest build file's folder. */
export function gradlePath(root: string, moduleDir: string): string {
  const rel = moduleDir.slice(root.length).replace(/^\/+|\/+$/g, '')
  return rel === '' ? ':' : `:${rel.split('/').join(':')}`
}

/** Width and height from a PNG's IHDR, given its base64. */
export function pngSize(base64: string): { width: number; height: number } | undefined {
  try {
    const head = atob(base64.slice(0, 44))
    if (head.charCodeAt(1) !== 0x50) return undefined
    const u32 = (at: number) =>
      ((head.charCodeAt(at) << 24) | (head.charCodeAt(at + 1) << 16) |
        (head.charCodeAt(at + 2) << 8) | head.charCodeAt(at + 3)) >>> 0
    return { width: u32(16), height: u32(20) }
  } catch {
    return undefined
  }
}

export const countBy = (findings: readonly Finding[], level: string) =>
  findings.filter(f => f.level.toUpperCase() === level).length

/** simulator_launch / simulator_command answers: an id, a package, maybe an error. */
export function simInfo(payload: Json): { simulator?: string; package?: string; error?: string } {
  const p = isObj(payload) ? payload : {}
  const result = isObj(p.result) ? p.result : p
  const build = isObj(result.build) ? result.build : undefined
  const errors = build && Array.isArray(build.errors) ? build.errors.filter(e => typeof e === 'string') : []
  return {
    simulator: str(p.simulator) ?? str(p.id) ?? str(result.simulator),
    package: str(p.package) ?? str(result.package),
    error: str(p.error) ?? (errors.length > 0 ? errors.join('\n') : undefined),
  }
}
