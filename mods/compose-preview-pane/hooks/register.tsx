import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderInput } from 'claude-code'

import type { Finding, PaneUi, PreviewShot, RenderState, SimState } from '../types'
import {
  cliShots,
  countBy,
  findingsIn,
  gradlePath,
  isKotlin,
  labelOf,
  mcpPayload,
  pngSize,
  previewFunctions,
  previewUris,
  renderResult,
  simInfo,
} from './parse'

type $ = EngineInterface
type Options = { mcp_server?: string; max_previews?: number }

const PANE = 'compose-preview'
const TITLE = 'Compose preview'

// Change a tag when that value's fields change: it declines what an earlier
// version stored, which outlives a reload.
const render = atom({ plugin: 'compose-preview-pane', key: 'render' } as const, { status: 'idle', shots: [] } as RenderState, {
  shape: 'render-1',
})
const sim = atom({ plugin: 'compose-preview-pane', key: 'sim' } as const, { status: 'off', frame: 0 } as SimState, {
  shape: 'sim-1',
})
const paneUi = atom({ plugin: 'compose-preview-pane', key: 'ui' } as const, { tab: 'previews', index: 0, show: 'after' } as PaneUi, {
  shape: 'ui-1',
})
const setRender = ($: $, fn: (r: RenderState) => RenderState) => update($, render, fn)
const setSim = ($: $, fn: (s: SimState) => SimState) => update($, sim, fn)
const setUi = ($: $, fn: (u: PaneUi) => PaneUi) => update($, paneUi, fn)
const backend = atom({ plugin: 'compose-preview-pane', key: 'backend' } as const, '')
const scratch = atom({ plugin: 'compose-preview-pane', key: 'scratch' } as const, '')

// The compose-preview plugin's server first, then a standalone registration
// (`compose-preview mcp install`). The CLI is the fallback for renders only.
const SERVERS = ['plugin:compose-preview:compose-preview-mcp', 'compose-preview-mcp']
const MIRRORED = /^mcp__(.+)__(render_preview|simulator_[a-z_]+)$/

class ToolError extends Error {}
class NoServer extends Error {}

// Debounce and single-flight: module state is fine here, a reload drops a
// pending render along with its timer.
let pending: { file: string; timer: { cancel(): void } } | undefined
let running = false
let rerun: string | undefined
const svgCache = new Map<string, string | undefined>()

// Set from the plugin's options each time register runs.
const config = { server: '', maxPreviews: 6 }

async function callMcp($: $, tool: string, args: Record<string, unknown>) {
  const known = await read($, backend)
  const candidates = [...new Set([config.server, known, ...SERVERS])].filter(
    (s): s is string => typeof s === 'string' && s !== '' && s !== 'cli',
  )
  let last: unknown
  for (const server of candidates) {
    let result
    try {
      result = await $.mcp.call(server, tool, args)
    } catch (err) {
      last = err
      continue
    }
    if (known !== server) await update($, backend, () => server)
    if (result.isError) {
      const text = result.content.map(b => ('text' in b ? String(b.text) : '')).join(' ')
      throw new ToolError(text.slice(0, 400) || `${tool} failed`)
    }
    return mcpPayload(result as Parameters<typeof mcpPayload>[0])
  }
  throw new NoServer(String(last ?? 'no compose-preview MCP server is connected'))
}

async function scratchDir($: $) {
  const dir = await read($, scratch)
  if (dir !== '' && (await $.fs.exists(dir))) return dir
  const made = await $.process.run(['mktemp', '-d', '-t', 'compose-preview-pane.XXXXXX'])
  const next = made.stdout.trim()
  await update($, scratch, () => next)
  return next
}

// The previous PNG of a preview, copied aside before the next render
// overwrites it, so the pane can flip between before and after.
async function keepBefore($: $, shot: PreviewShot | undefined) {
  if (shot?.pngPath === undefined || !(await $.fs.exists(shot.pngPath))) return shot?.beforePath
  const dir = await scratchDir($)
  const name = shot.id.replace(/[^A-Za-z0-9._-]+/g, '_').slice(-80)
  const to = `${dir}/before-${name}.png`
  const copied = await $.process.run(['cp', shot.pngPath, to])
  return copied.exitCode === 0 ? to : undefined
}

// render_preview answers `pending` while the project's daemon starts; the same call again
// gets the render (harness-notes R1).
async function renderSettled($: $, args: Record<string, unknown>) {
  let result = await callMcp($, 'render_preview', args)
  for (let attempt = 0; attempt < 20 && /pending/i.test(JSON.stringify(result ?? '')); attempt++) {
    await $.clock.sleep(3000)
    result = await callMcp($, 'render_preview', args)
  }
  return result
}

async function renderOverMcp($: $, file: string, root: string, previous: Map<string, PreviewShot>) {
  let found = await callMcp($, 'find_previews_for_file', { path: file })
  // A server that has not rendered this project yet maps no file to previews. One render by
  // name loads the module, and the lookup answers after it.
  if (previewUris(found).length === 0) {
    const name = previewFunctions(await $.fs.read(file).catch(() => ''))[0]
    if (name !== undefined) {
      await renderSettled($, { preview: name, project: root, inline: false })
      found = await callMcp($, 'find_previews_for_file', { path: file })
    }
  }
  const uris = previewUris(found).slice(0, config.maxPreviews)
  await setRender($, r =>
    uris.length === 0
      ? { ...r, via: 'mcp', shots: [], message: 'No previews in this file.' }
      : { ...r, via: 'mcp', shots: r.shots.filter(s => uris.includes(s.id)), message: undefined },
  )

  let a11yMissing = false
  for (const uri of uris) {
    const before = await keepBefore($, previous.get(uri))
    let shot: PreviewShot
    try {
      const out = renderResult(await renderSettled($, { uri, inline: false }))
      const a11y = a11yMissing
        ? undefined
        : await callMcp($, 'get_preview_data', { uri, kind: 'a11y/atf' }).catch(err => {
            // compose-preview-mcp 4.12.0 advertises only compose/semantics by default.
            if (/not advertised/.test(String((err as Error).message))) a11yMissing = true
            return undefined
          })
      shot = { id: uri, uri, label: labelOf(uri), ...out, beforePath: before, findings: findingsIn(a11y) }
    } catch (err) {
      if (err instanceof NoServer) throw err
      shot = { id: uri, uri, label: labelOf(uri), beforePath: before, findings: [], error: String((err as Error).message ?? err) }
    }
    await setRender($, r => ({ ...r, shots: upsert(r.shots, shot) }))
  }
  if (a11yMissing) {
    await setRender($, r => ({
      ...r,
      message: 'The MCP server does not offer a11y/atf here; `compose-preview a11y` has the findings.',
    }))
  }
}

async function nearest($: $, from: string, names: readonly string[], stop = '/') {
  let dir = from
  while (dir.length > 0 && dir.length >= stop.length) {
    for (const name of names) if (await $.fs.exists(`${dir}/${name}`)) return dir
    dir = dir.slice(0, dir.lastIndexOf('/'))
  }
  return undefined
}

/** The Gradle build that holds `file`: the nearest folder with a settings file. */
async function projectRoot($: $, file: string) {
  return (await nearest($, dirOf(file), ['settings.gradle.kts', 'settings.gradle'])) ?? (await $.session.cwd())
}

async function moduleOf($: $, root: string, file: string) {
  const dir = await nearest($, dirOf(file), ['build.gradle.kts', 'build.gradle'], root)
  return dir === undefined ? undefined : gradlePath(root, dir)
}

async function renderOverCli($: $, file: string, root: string, previous: Map<string, PreviewShot>) {
  const module = await moduleOf($, root, file)
  const befores = new Map<string, string | undefined>()
  for (const [id, shot] of previous) befores.set(id, await keepBefore($, shot))
  await setRender($, r => ({ ...r, via: 'cli', message: `compose-preview a11y${module ? ` --module ${module}` : ''}…` }))

  // `a11y`, not `show --with-extension a11y`: show drops the extension (compose-ai-tools#6341).
  const argv = ['compose-preview', 'a11y', '--json', ...(module ? ['--module', module] : [])]
  const ran = await $.process.run(argv, { cwd: root, timeoutMs: 600_000 })
  const shots = cliShots(ran.stdout, file)
    .slice(0, config.maxPreviews)
    .map(s => ({ ...s, beforePath: befores.get(s.id) }))
  if (ran.exitCode !== 0 && shots.length === 0) {
    throw new ToolError(ran.stderr.trim().split('\n').slice(-6).join('\n') || `exit ${ran.exitCode}`)
  }
  await update($, backend, b => (b === '' ? 'cli' : b))
  await setRender($, r => ({ ...r, shots, message: shots.length === 0 ? 'No previews in this file.' : undefined }))
}

async function renderFile($: $, file: string) {
  if (running) {
    rerun = file
    return
  }
  running = true
  try {
    const prior = await read($, render)
    const previous = new Map(prior.file === file ? prior.shots.map(s => [s.id, s] as const) : [])
    await setRender($, () => ({
      file,
      status: 'rendering',
      at: Date.now(),
      shots: prior.file === file ? prior.shots : [],
    }))
    $.ui.status(`compose-preview: rendering ${file.split('/').pop()}`)
    const root = await projectRoot($, file)
    try {
      await renderOverMcp($, file, root, previous)
    } catch (err) {
      if (!(err instanceof NoServer)) throw err
      await renderOverCli($, file, root, previous)
    }
    const done = await setRender($, r => ({ ...r, status: 'done', at: Date.now() }))
    const errors = done.shots.reduce((n, s) => n + countBy(s.findings, 'ERROR'), 0)
    if (errors > 0) $.ui.toast(`compose-preview: ${errors} accessibility error${errors === 1 ? '' : 's'} in ${file.split('/').pop()}`)
  } catch (err) {
    await setRender($, r => ({ ...r, status: 'error', message: String((err as Error).message ?? err) }))
  } finally {
    $.ui.status(undefined)
    running = false
    const again = rerun
    rerun = undefined
    if (again !== undefined) void renderFile($, again)
  }
}

// ── The simulator: `compose-preview launch` behind the MCP simulator_* tools.

async function screenshot($: $) {
  const s = await read($, sim)
  if (s.status === 'off' || s.status === 'error') return
  const dir = await scratchDir($)
  const path = `${dir}/app.png`
  try {
    await callMcp($, 'simulator_screenshot', { ...(s.simulator ? { simulator: s.simulator } : {}), path })
    await setSim($, v => ({ ...v, screenshot: path, frame: v.frame + 1, at: Date.now() }))
  } catch (err) {
    await setSim($, v => ({ ...v, message: String((err as Error).message ?? err) }))
  }
}

async function simCall($: $, tool: string, args: Record<string, unknown> = {}) {
  const s = await read($, sim)
  const payload = await callMcp($, tool, { ...(s.simulator ? { simulator: s.simulator } : {}), ...args })
  return simInfo(payload)
}

async function launch($: $, target: string) {
  const { file } = await read($, render)
  const root = file !== undefined ? await projectRoot($, file) : await $.session.cwd()
  const isApk = target.endsWith('.apk')
  await setSim($, v => ({ status: 'starting', frame: v.frame, target: target || root, message: 'Starting the simulator…' }))
  try {
    const args = isApk ? { apk: target, headless: true } : { project: target || root, headless: true }
    const info = simInfo(await callMcp($, 'simulator_launch', args))
    if (info.error !== undefined) throw new ToolError(info.error)
    await setSim($, v => ({ ...v, status: 'running', simulator: info.simulator, package: info.package, message: undefined }))
    await screenshot($)
  } catch (err) {
    const text = err instanceof NoServer
      ? 'The simulator needs the compose-preview MCP server (simulator_* tools); none is connected.'
      : String((err as Error).message ?? err)
    await setSim($, v => ({ ...v, status: 'error', message: text }))
  }
}

async function reloadApp($: $) {
  const s = await read($, sim)
  if (s.status !== 'running' || s.target?.endsWith('.apk')) return
  await setSim($, v => ({ ...v, status: 'reloading', message: 'Reloading the edit…' }))
  try {
    const info = await simCall($, 'simulator_reload')
    await setSim($, v => ({ ...v, status: 'running', message: info.error }))
  } catch (err) {
    // A compile error is the reload's error; the running app is left alone.
    await setSim($, v => ({ ...v, status: 'running', message: String((err as Error).message ?? err) }))
  }
  await screenshot($)
}

async function act($: $, tool: string, args: Record<string, unknown> = {}) {
  try {
    await simCall($, tool, args)
    await simCall($, 'simulator_command', { cmd: 'wait', ms: 400 }).catch(() => undefined)
  } catch (err) {
    await setSim($, v => ({ ...v, message: String((err as Error).message ?? err) }))
  }
  await screenshot($)
}

// Every control of the pane, by its key: Buttons call this from onPress.
async function handle($: $, key: string) {
  if (key === 'tab-previews' || key === 'tab-app') {
    await setUi($, u => ({ ...u, tab: key === 'tab-app' ? 'app' : 'previews' }))
  } else if (key.startsWith('shot-')) {
    const index = Number(key.slice(5))
    await setUi($, u => ({ ...u, index, show: 'after' }))
  } else if (key === 'show-before' || key === 'show-after') {
    await setUi($, u => ({ ...u, show: key === 'show-before' ? 'before' : 'after' }))
  } else if (key === 'rerender') {
    const { file } = await read($, render)
    if (file !== undefined) void renderFile($, file)
  } else if (key === 'fix') {
    const r = await read($, render)
    const shot = r.shots[(await read($, paneUi)).index]
    if (shot !== undefined && r.file !== undefined) {
      await $.prompt.fill({ text: fixPrompt(r.file, shot), mode: 'replace' })
    }
  } else if (key === 'app-launch') {
    void launch($, '')
  } else if (key === 'app-refresh') {
    void screenshot($)
  } else if (key === 'app-back') {
    void act($, 'simulator_command', { cmd: 'back' })
  } else if (key === 'app-restart') {
    void act($, 'simulator_restart')
  } else if (key === 'app-reload') {
    void reloadApp($)
  } else if (key === 'app-stop') {
    await simCall($, 'simulator_stop').catch(() => undefined)
    await setSim($, v => ({ status: 'off', frame: v.frame }))
  }
}

function tap($: $, text: string) {
  if (text.trim() !== '') void act($, 'simulator_command', { cmd: 'tap', text: text.trim() })
}

export const register: Register = (on, options) => {
  const opts = options as Options
  config.server = opts.mcp_server ?? ''
  config.maxPreviews = Math.max(1, Math.min(20, Number(opts.max_previews ?? 6) || 6))

  // ── Events.

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'preview-pane',
      description: 'Open the Compose preview pane',
    })
    await $.command.register({
      name: 'compose-app',
      description: 'Run the app in the compose-preview simulator and show it in the pane',
      argumentHint: '[app.apk | project dir]',
    })
    return next(e)
  })

  on('command.run', { command: 'preview-pane' }, async $ => {
    await $.ui.open({ id: PANE, title: TITLE })
    await setUi($, u => ({ ...u, tab: 'previews' }))
    return { text: 'Compose preview pane opened. It re-renders after each Kotlin edit.' }
  })

  on('command.run', { command: 'compose-app' }, async ($, e) => {
    await $.ui.open({ id: PANE, title: TITLE })
    await setUi($, u => ({ ...u, tab: 'app' }))
    const target = e.args.trim()
    $.clock.after(0, () => void launch($, target))
    return { text: `Starting ${target || 'this project'} in the compose-preview simulator; the pane shows it once it is up.` }
  })

  // After an edit to Kotlin: re-render that file's previews (debounced), and
  // reload a running simulator. No model turn is spent on either.
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || ran.isError === true) return ran

    const tool = String(e.tool)
    const path = 'file_path' in e && typeof e.file_path === 'string' ? e.file_path : undefined
    if ((tool === 'Edit' || tool === 'Write' || tool === 'MultiEdit') && path !== undefined && isKotlin(path)) {
      pending?.timer.cancel()
      pending = {
        file: path,
        timer: $.clock.after(700, () => {
          const file = pending?.file
          pending = undefined
          if (file === undefined) return
          void (async () => {
            const opened = await $.ui.open({ id: PANE, title: TITLE })
            if (opened.isPlaced) await renderFile($, file)
            await reloadApp($)
          })()
        }),
      }
      return ran
    }

    // Mirror the agent's own compose-preview calls into the pane, so the
    // person sees what the model just rendered or drove.
    const mirrored = MIRRORED.exec(tool)
    if (mirrored === null) return ran
    const [, server, name] = mirrored
    if (server !== undefined) await update($, backend, () => server)
    const text = JSON.stringify(ran.result ?? '')
    if (name === 'render_preview') {
      const png = /\\?"pngPath\\?"\s*:\s*\\?"([^"\\]+)/.exec(text)?.[1]
      const uri = 'uri' in e && typeof e.uri === 'string' ? e.uri : undefined
      if (png !== undefined && uri !== undefined) {
        await setRender($, r => ({
          ...r,
          status: 'done',
          via: 'agent',
          at: Date.now(),
          shots: upsert(r.shots, { id: uri, uri, label: labelOf(uri), pngPath: png, findings: r.shots.find(s => s.id === uri)?.findings ?? [] }),
        }))
      }
    } else if (name === 'simulator_launch') {
      const id = /\\?"simulator\\?"\s*:\s*\\?"([^"\\]+)/.exec(text)?.[1]
      await setSim($, v => ({ ...v, status: 'running', simulator: id ?? v.simulator, message: 'Launched by Claude' }))
      await screenshot($)
    } else if (name === 'simulator_stop') {
      await setSim($, v => ({ status: 'off', frame: v.frame }))
    } else {
      await screenshot($)
    }
    return ran
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const ui = await read($, paneUi)
    const columns = e.props.bodyColumns ?? 60

    const tabs = (
      <Box flexDirection="row" gap={1}>
        <Button key="tab-previews" onPress={() => void handle($, 'tab-previews')} label="Previews" variant={ui.tab === 'previews' ? 'primary' : 'secondary'} />
        <Button key="tab-app" onPress={() => void handle($, 'tab-app')} label="Running app" variant={ui.tab === 'app' ? 'primary' : 'secondary'} />
      </Box>
    )

    if (ui.tab === 'app') {
      const s = await read($, sim)
      return (
        <Box flexDirection="column" gap={1}>
          {tabs}
          <Text>
            <Text weight="bold">{s.package ?? s.target?.split('/').pop() ?? 'Simulator'}</Text>
            <Text dimColor> · {s.status}</Text>
          </Text>
          {s.message !== undefined && <Text color={s.status === 'error' ? 'error' : undefined} dimColor={s.status !== 'error'}>{s.message}</Text>}
          {s.status === 'off' || s.status === 'error' ? (
            <Button key="app-launch" onPress={() => void handle($, 'app-launch')} label="Run this project" variant="primary" />
          ) : (
            <Box flexDirection="column" gap={1}>
              {s.screenshot !== undefined && (await picture($, e, s.screenshot, s.frame, 'The running app', columns))}
              <Box flexDirection="row" gap={1}>
                <Button key="app-back" onPress={() => void handle($, 'app-back')} label="Back" />
                <Button key="app-refresh" onPress={() => void handle($, 'app-refresh')} label="Refresh" />
                <Button key="app-reload" onPress={() => void handle($, 'app-reload')} label="Reload edit" />
                <Button key="app-restart" onPress={() => void handle($, 'app-restart')} label="Restart" />
                <Button key="app-stop" onPress={() => void handle($, 'app-stop')} label="Stop" />
              </Box>
              {tapField($, e, text => tap($, text))}
            </Box>
          )}
        </Box>
      )
    }

    const r = await read($, render)
    if (r.file === undefined) {
      return (
        <Box flexDirection="column" gap={1}>
          {tabs}
          <Text dimColor>Edit a Kotlin file with @Preview functions and its renders show here.</Text>
        </Box>
      )
    }

    const index = Math.min(ui.index, Math.max(0, r.shots.length - 1))
    const shot = r.shots[index]
    const changed = r.shots.filter(s => s.changed === true).length
    const errors = r.shots.reduce((n, s) => n + countBy(s.findings, 'ERROR'), 0)
    const showBefore = ui.show === 'before' && shot?.beforePath !== undefined
    const path = showBefore ? shot?.beforePath : shot?.pngPath

    return (
      <Box flexDirection="column" gap={1}>
        {tabs}
        <Text>
          <Text weight="bold">{r.file.split('/').pop()}</Text>
          <Text dimColor>
            {' '}· {r.status === 'rendering' ? 'rendering…' : r.status}
            {r.via ? ` via ${r.via}` : ''} · {r.shots.length} preview{r.shots.length === 1 ? '' : 's'}
            {changed > 0 ? ` · ${changed} changed` : ''}
          </Text>
          {errors > 0 && <Text color="error"> · {errors} a11y error{errors === 1 ? '' : 's'}</Text>}
        </Text>
        {r.message !== undefined && <Text color={r.status === 'error' ? 'error' : undefined} dimColor={r.status !== 'error'}>{r.message}</Text>}
        {r.shots.length > 1 && (
          <Box flexDirection="row" flexWrap="wrap" gap={1}>
            {r.shots.map((s, i) => (
              <Button key={`shot-${i}`} onPress={() => void handle($, `shot-${i}`)} plain={i !== index ? true : undefined} variant={i === index ? 'primary' : undefined}>
                {s.label}
                {s.changed === true ? <Text color="warning"> •</Text> : ''}
                {countBy(s.findings, 'ERROR') > 0 ? <Text color="error"> !</Text> : ''}
              </Button>
            ))}
          </Box>
        )}
        {shot !== undefined && (
          <Box flexDirection="column" gap={1}>
            <Box flexDirection="row" gap={1}>
              <Text weight="bold">{shot.label}</Text>
              {shot.beforePath !== undefined && (
                <Box flexDirection="row" gap={1}>
                  <Button key="show-before" onPress={() => void handle($, 'show-before')} label="Before" variant={showBefore ? 'primary' : 'secondary'} />
                  <Button key="show-after" onPress={() => void handle($, 'show-after')} label="After" variant={showBefore ? 'secondary' : 'primary'} />
                </Box>
              )}
              <Button key="rerender" onPress={() => void handle($, 'rerender')} label="Re-render" />
            </Box>
            {shot.error !== undefined && <Text color="error">{shot.error}</Text>}
            {path !== undefined && (await picture($, e, path, r.at ?? 0, `${shot.label} (${showBefore ? 'before' : 'after'})`, columns))}
            {shot.changed === false && <Text dimColor>Pixel-identical to the previous render.</Text>}
            {shot.findings.length > 0 && findingsList($, e, shot.findings)}
            {shot.findings.length > 0 && <Button key="fix" onPress={() => void handle($, 'fix')} label="Ask Claude to fix these" />}
          </Box>
        )}
      </Box>
    )
  })
}

function dirOf(path: string) {
  return path.slice(0, path.lastIndexOf('/'))
}

function upsert(shots: readonly PreviewShot[], shot: PreviewShot): PreviewShot[] {
  const at = shots.findIndex(s => s.id === shot.id)
  return at < 0 ? [...shots, shot] : shots.map((s, i) => (i === at ? shot : s))
}

function fixPrompt(file: string, shot: PreviewShot) {
  const lines = shot.findings.map(f => `- ${f.level} ${f.type}: ${f.message}${f.view ? ` (${f.view})` : ''}`)
  return `Fix the accessibility findings in the ${shot.label} preview of ${file}, then re-render it to confirm:\n${lines.join('\n')}`
}

function findingsList($: $, e: RenderInput & { component: 'Pane' }, findings: readonly Finding[]) {
  const { Box, Text } = $.ui.resolve(e)
  return (
    <Box flexDirection="column">
      {findings.slice(0, 12).map(f => (
        <Text>
          <Text color={f.level.toUpperCase() === 'ERROR' ? 'error' : f.level.toUpperCase() === 'WARNING' ? 'warning' : undefined}>
            {f.level.toLowerCase()}
          </Text>
          <Text> {f.type}</Text>
          <Text dimColor> {f.message}</Text>
        </Text>
      ))}
      {findings.length > 12 && <Text dimColor>…and {findings.length - 12} more</Text>}
    </Box>
  )
}

function tapField($: $, e: RenderInput & { component: 'Pane' }, onSubmit: (text: string) => void) {
  if (e.surface === 'mobile') return undefined
  const { Input } = $.ui.resolve(e)
  return <Input key="app-tap" label="Tap the element with text" placeholder="e.g. Settings" onSubmit={onSubmit} />
}

// A PNG on disk, drawn the surface's way: the terminal reads the file itself;
// the remote surfaces get it inlined in an SVG, which caps it near 96 KB.
async function picture($: $, e: RenderInput & { component: 'Pane' }, path: string, generation: number, alt: string, columns: number) {
  if (e.surface === 'terminal') {
    const { Image } = $.ui.resolve(e)
    const width = Math.max(10, Math.min(columns, 64))
    return <Image key={`img-${alt}`} source={{ file: path, format: 'png', generation }} columns={width} rows={Math.max(6, Math.round(width / 2))} alt={alt} />
  }
  const { Svg, Text } = $.ui.resolve(e)
  const cacheKey = `${path}#${generation}`
  if (!svgCache.has(cacheKey)) {
    let svg: string | undefined
    try {
      const { base64 } = (await $.fs.read(path, { as: 'bytes' })) as { base64: string }
      const size = pngSize(base64) ?? { width: 360, height: 640 }
      const markup =
        `<svg xmlns="http://www.w3.org/2000/svg" width="${size.width}" height="${size.height}" viewBox="0 0 ${size.width} ${size.height}">` +
        `<image width="${size.width}" height="${size.height}" href="data:image/png;base64,${base64}"/></svg>`
      svg = markup.length <= 131_072 ? markup : undefined
    } catch {
      svg = undefined
    }
    if (svgCache.size > 32) svgCache.clear()
    svgCache.set(cacheKey, svg)
  }
  const svg = svgCache.get(cacheKey)
  return svg !== undefined
    ? <Svg source={svg} alt={alt} />
    : <Text dimColor>{alt}: {path}</Text>
}

