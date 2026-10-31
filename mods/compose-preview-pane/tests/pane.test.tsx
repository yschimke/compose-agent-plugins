import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import { cliShots, labelOf, previewFunctions, previewUris, renderResult, sameSource } from '../hooks/parse'

// Shapes recorded from compose-preview CLI 2.77.0 and compose-preview-mcp 4.12.0 against
// android/wear-os-samples ComposeStarter (a Groovy settings.gradle, previews in MainActivity.kt).
const ROOT = '/home/user/android/wear-os-samples/ComposeStarter'
const FILE = `${ROOT}/app/src/main/java/com/example/android/wearable/composestarter/presentation/MainActivity.kt`
const FQN = 'com.example.android.wearable.composestarter.presentation.MainActivityKt'
const URI = (variant: string) =>
  `compose-preview://ComposeStarter-44f65eb9/_app/${FQN}.GreetingScreenPreview_${encodeURIComponent(variant)}`
const SOURCE = `
@WearPreviewDevices
@WearPreviewFontScales
@Composable
fun GreetingScreenPreview() { GreetingScreen("Preview Android", onShowList = {}) }

@WearPreviewDevices
@Composable
fun ListScreenPreview() { ListScreen() }
`

const PANE = {
  plugin: 'compose-preview-pane',
  component: 'Pane',
  requestId: 'compose-preview',
  props: {
    title: 'Compose preview',
    isFocused: false,
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

const PNG_1X1 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
const text = (value: unknown, isError = false) => ({
  value: { content: [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value) }], isError },
})
const ran = (stdout: string, exitCode = 0) => ({
  value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
})

const A11Y_STDOUT = JSON.stringify({
  schema: 'compose-preview-show/v2',
  previews: [
    {
      id: `${FQN}.GreetingScreenPreview_Devices - Large Round`,
      functionName: 'GreetingScreenPreview',
      sourceFile: 'src/main/java/com/example/android/wearable/composestarter/presentation/MainActivity.kt',
      captures: [{ pngPath: `${ROOT}/app/build/compose-previews/renders/GreetingScreenPreview_Devices_Large_Round-9a18e797.png`, sha256: 'ac86', changed: true, optional: false }],
      dataExtensions: {
        a11y: { schema: 'compose-preview-data-a11y/v1', payload: { findings: [{ level: 'ERROR', type: 'TouchTargetSizeCheck', message: 'Target is 40dp', viewDescription: 'Show list' }], nodes: [] } },
      },
    },
    { id: 'com.example.Other.OtherPreview', functionName: 'OtherPreview', sourceFile: 'src/main/java/Other.kt', captures: [] },
  ],
})

type Server = 'up' | 'cold' | 'down'
type Options = { pendingOnce?: boolean; previews?: () => boolean }

function engine(on: On, server: Server, a11y: 'advertised' | 'missing' = 'advertised', options: Options = {}) {
  const calls: string[] = []
  let warmed = server !== 'cold'
  let pending = options.pendingOnce === true
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  // The session runs from above the checkout, as a cloud session does.
  on('session.cwd', () => ({ value: '/home/user' }))
  on('tool.call', () => ({ result: {} }))
  on('fs.exists', (_, e) => {
    const p = e.path
    if (p.endsWith('/settings.gradle')) return { value: p === `${ROOT}/settings.gradle` }
    if (/\/(settings|build)\.gradle(\.kts)?$/.test(p)) return { value: p === `${ROOT}/app/build.gradle.kts` }
    return { value: true }
  })
  on('fs.read', (_, e) => (e.as === 'bytes' ? { value: { base64: PNG_1X1 } } : { value: SOURCE }))
  on('process.run', (_, e) => {
    calls.push(`${e.argv.join(' ')} @ ${e.init?.cwd ?? ''}`)
    if (e.argv[0] === 'mktemp') return ran('/tmp/cpp\n')
    if (e.argv[0] === 'compose-preview') return ran(A11Y_STDOUT)
    return ran('')
  })
  on('mcp.call', (_, e) => {
    calls.push(`mcp ${e.server} ${e.tool} ${JSON.stringify(e.args)}`)
    if (server === 'down') throw new Error('not connected')
    if (e.tool === 'find_previews_for_file') {
      if (!warmed || options.previews?.() === false) return text({ previews: [] })
      return text({
        previews: [
          { uri: URI('Devices - Large Round'), fqn: `${FQN}.GreetingScreenPreview_Devices - Large Round`, bodyLine: 344 },
          { uri: URI('Fonts - Small'), fqn: `${FQN}.GreetingScreenPreview_Fonts - Small`, bodyLine: 344 },
        ],
      })
    }
    if (e.tool === 'render_preview') {
      if (pending) {
        pending = false
        return text({ status: 'pending', message: 'project is starting; call again' })
      }
      warmed = true
      const uri = String(e.args.uri ?? URI('Devices - Large Round'))
      return text({ uri, pngPath: `/tmp/compose-preview-mcp-1/${uri.length}.png`, widthPx: 454, heightPx: 454, sha256: 'ac86', changed: true, durationMs: 6338 })
    }
    if (e.tool === 'get_preview_data') {
      return a11y === 'missing'
        ? text('get_preview_data: DataProductUnknown: data/fetch: kind not advertised: a11y/atf', true)
        : text({ kind: 'a11y/atf', payload: { findings: [{ level: 'ERROR', type: 'TextContrastCheck', message: 'Contrast 2.1:1' }] } })
    }
    // Recorded from compose-preview-mcp 4.13.0 running ComposeStarter's debug APK.
    if (e.tool === 'simulator_launch') {
      return text({ simulator: 'sim-1', info: { package: 'com.example.android.wearable.composestarter', formFactor: 'wear', round: true, width: 454, height: 454 } })
    }
    if (e.tool === 'simulator_screenshot') return text({ width: 454, height: 454, rotation: 0, path: e.args.path, events: [] })
    if (e.tool === 'simulator_reload') return text({ mode: 'unchanged', build: { ok: true, ms: 1657, tasks: [':app:compileDebugJavaWithJavac'] }, totalMs: 1674, events: [] })
    if (e.tool === 'simulator_command' && e.args.cmd === 'wait') return text({ result: { waitedMs: e.args.ms }, events: [] })
    if (e.tool === 'simulator_command' && e.args.cmd === 'tap') {
      return text({ result: { x: 227, y: 400, display: 0, node: { cls: 'android.widget.TextView', text: e.args.text, bounds: [162, 382, 292, 418] } }, events: [] })
    }
    return text({})
  })
  return calls
}

test('parse reads the recorded payloads', () => {
  expect(labelOf(URI('Devices - Large Round'))).toBe('GreetingScreenPreview · Devices - Large Round')
  expect(labelOf(`${FQN}.GreetingScreenPreview_Fonts - Small`)).toBe('GreetingScreenPreview · Fonts - Small')
  expect(labelOf(`${FQN}.ListScreenPreview`)).toBe('ListScreenPreview')
  expect(previewFunctions(SOURCE)).toEqual(['GreetingScreenPreview', 'ListScreenPreview'])
  expect(previewUris({ previews: [{ uri: 'a', fqn: 'x', bodyLine: 1 }] })).toEqual(['a'])
  expect(renderResult({ pngPath: '/p.png', widthPx: 454, heightPx: 454, sha256: 's', changed: true })).toEqual({
    pngPath: '/p.png', sha: 's', changed: true, width: 454, height: 454,
  })
  expect(sameSource('/p/app/src/main/java/a/Home.kt', 'src/main/java/a/Home.kt')).toBe(true)
  expect(sameSource('/p/app/src/main/java/a/Home.kt', 'src/main/java/b/Home.kt')).toBe(false)
  expect(sameSource('/p/app/src/main/java/a/Home.kt', 'Home.kt')).toBe(true)
  const shots = cliShots(A11Y_STDOUT, FILE)
  expect(shots.length).toBe(1)
  expect(shots[0]?.findings[0]?.view).toBe('Show list')
})

test('an Edit to a Kotlin file renders its previews over MCP, without a model turn', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'up')
  await $.session.start({ cwd: '/home/user', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: FILE, old_string: 'a', new_string: 'b' })
  await clock.advance(1000)

  expect(calls.filter(c => c.includes(' render_preview ')).length).toBe(2)
  const notify = calls.findIndex(c => c.includes(' notify_file_changed '))
  expect(calls[notify]).toContain(`{"workspaceId":"ComposeStarter-44f65eb9","path":"${FILE}"}`)
  expect(notify).toBeLessThan(calls.findIndex(c => c.includes(' render_preview ')))
  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /MainActivity\.kt/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /2 a11y errors/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Contrast 2\.1:1/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Devices - Large Round/ })).toBeDefined()
    expect(await ui.find({ key: 'shot-1' })).toBeDefined()
    await ui.unmount()
  }
})

test('a cold server is warmed by one render by name, then asked again', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'cold')
  await $.session.start({ cwd: '/home/user', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: FILE, old_string: 'a', new_string: 'b' })
  await clock.advance(1000)

  const mcp = calls.filter(c => c.startsWith('mcp plugin:compose-preview'))
  expect(mcp[0]).toContain('find_previews_for_file')
  expect(mcp[1]).toContain(`render_preview {"preview":"GreetingScreenPreview","project":"${ROOT}","inline":false}`)
  expect(mcp[2]).toContain('find_previews_for_file')
  expect(mcp.filter(c => c.includes('"uri"') && c.includes('render_preview')).length).toBe(2)
})

test('a server without a11y/atf says so once and still shows the renders', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'up', 'missing')
  await $.session.start({ cwd: '/home/user', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Write', file_path: FILE, content: 'x' })
  await clock.advance(1000)

  expect(calls.filter(c => c.includes('get_preview_data')).length).toBe(1)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /does not offer a11y\/atf/ })).toBeDefined()
  expect(await ui.find({ type: 'Svg' })).toBeDefined()
  await ui.unmount()
})

test('with no MCP server it runs `compose-preview a11y` in the Gradle build that holds the file', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'down')
  await $.session.start({ cwd: '/home/user', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Write', file_path: FILE, content: 'x' })
  await clock.advance(1000)

  expect(calls).toContain(`compose-preview a11y --json --module :app @ ${ROOT}`)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /via cli/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Target is 40dp/ })).toBeDefined()
  await ui.unmount()
})

test('edits to non-Kotlin files and build scripts render nothing', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'up')
  await $.session.start({ cwd: '/home/user', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: `${ROOT}/README.md`, old_string: 'a', new_string: 'b' })
  await $.tool.call({ tool: 'Edit', file_path: `${ROOT}/app/build.gradle.kts`, old_string: 'a', new_string: 'b' })
  await clock.advance(1000)
  expect(calls.length).toBe(0)
})

test('the running-app tab launches the simulator from the edited file\'s project', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'up')
  await $.session.start({ cwd: '/home/user', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: FILE, old_string: 'a', new_string: 'b' })
  await clock.advance(1000)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'tab-app' })
  await ui.press({ key: 'app-launch' })
  await clock.advance(10)
  const sim = calls.filter(c => c.includes(' simulator_'))
  expect(sim[0]).toContain(`simulator_launch {"project":"${ROOT}","headless":true}`)
  // The entrance fade runs before the first screenshot is taken.
  expect(sim[1]).toContain('simulator_command {"simulator":"sim-1","cmd":"wait","ms":1500}')
  expect(sim[2]).toContain('simulator_screenshot {"simulator":"sim-1","path":"/tmp/cpp/app.png"}')
  expect(await ui.find({ type: 'Text', text: /com\.example\.android\.wearable\.composestarter/ })).toBeDefined()
  expect(await ui.find({ key: 'app-back' })).toBeDefined()

  await ui.input({ key: 'app-tap', text: 'Show list' })
  await clock.advance(10)
  expect(calls.some(c => c.includes('simulator_command {"simulator":"sim-1","cmd":"tap","text":"Show list"}'))).toBe(true)
  await ui.unmount()
})

test('a pending render is asked again before the shot is stored', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'up', 'advertised', { pendingOnce: true })
  await $.session.start({ cwd: '/home/user', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: FILE, old_string: 'a', new_string: 'b' })
  await clock.advance(1000)
  await clock.advance(5000)

  expect(calls.filter(c => c.includes(' render_preview ')).length).toBe(3)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Svg' })).toBeDefined()
  await ui.unmount()
})

test('an edit that removes every preview clears the old renders', async ($, on) => {
  const clock = mock.clock(on)
  let hasPreviews = true
  engine(on, 'up', 'advertised', { previews: () => hasPreviews })
  await $.session.start({ cwd: '/home/user', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: FILE, old_string: 'a', new_string: 'b' })
  await clock.advance(1000)
  hasPreviews = false
  await $.tool.call({ tool: 'Edit', file_path: FILE, old_string: 'b', new_string: 'c' })
  await clock.advance(1000)

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /No previews in this file/ })).toBeDefined()
  expect(await ui.find({ type: 'Svg' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /0 previews/ })).toBeDefined()
  await ui.unmount()
})
