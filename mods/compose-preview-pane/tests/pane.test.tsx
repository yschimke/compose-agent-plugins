import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

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

const FILE = '/proj/app/src/main/kotlin/Home.kt'
const PNG_1X1 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
const text = (value: unknown) => ({ value: { content: [{ type: 'text', text: JSON.stringify(value) }], isError: false } })

function engine(on: On, mcp: 'up' | 'down') {
  const calls: string[] = []
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/proj' }))
  on('tool.call', () => ({ result: {} }))
  on('fs.exists', (_, e) => ({ value: /\/build\.gradle(\.kts)?$/.test(e.path) ? e.path === '/proj/app/build.gradle.kts' : true }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('fs.read', () => ({ value: { base64: PNG_1X1 } }))
  on('process.run', (_, e) => {
    calls.push(e.argv.join(' '))
    if (e.argv[0] === 'mktemp') return { value: { exitCode: 0, stdout: '/tmp/cpp\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    if (e.argv[0] === 'compose-preview') {
      const stdout = JSON.stringify({
        schema: 'compose-preview-show/v2',
        previews: [
          { id: 'app.HomeKt.HomePreview', functionName: 'HomePreview', sourceFile: 'src/main/kotlin/Home.kt',
            captures: [{ pngPath: '/proj/app/build/home.png', sha256: 'aa', changed: true }],
            dataExtensions: { a11y: { payload: { findings: [{ level: 'ERROR', type: 'TouchTargetSize', message: 'Too small' }] } } } },
          { id: 'app.OtherKt.Other', functionName: 'Other', sourceFile: 'src/main/kotlin/Other.kt', captures: [] },
        ],
      })
      return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('mcp.call', (_, e) => {
    calls.push(`mcp ${e.server} ${e.tool}`)
    if (mcp === 'down') throw new Error('not connected')
    if (e.tool === 'find_previews_for_file') return text(['preview://app/HomeKt.HomePreview', 'preview://app/HomeKt.HomeDarkPreview'])
    if (e.tool === 'render_preview') return text({ pngPath: `/proj/build/${String(e.args.uri).split('.').pop()}.png`, sha256: 'bb', changed: true, width: 1, height: 1 })
    if (e.tool === 'get_preview_data') return text({ kind: 'a11y/atf', payload: { findings: [{ level: 'ERROR', type: 'TextContrast', message: 'Contrast 2.1:1' }] } })
    return text({})
  })
  return calls
}

test('an Edit to a Kotlin file renders its previews over MCP, without a model turn', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'up')
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: FILE, old_string: 'a', new_string: 'b' })
  await clock.advance(1000)

  expect(calls.filter(c => c.includes('render_preview')).length).toBe(2)
  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect(await ui.find({ type: 'Text', text: /Home\.kt/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /2 a11y errors/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Contrast 2\.1:1/ })).toBeDefined()
    expect(await ui.find({ key: 'shot-1' })).toBeDefined()
    await ui.unmount()
  }
})

test('with no MCP server it falls back to the CLI for the edited module', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'down')
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Write', file_path: FILE, content: 'x' })
  await clock.advance(1000)

  expect(calls).toContain('compose-preview show --json --with-extension a11y --module :app')
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /via cli/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Too small/ })).toBeDefined()
  await ui.unmount()
})

test('edits to non-Kotlin files render nothing', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'up')
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: '/proj/README.md', old_string: 'a', new_string: 'b' })
  await $.tool.call({ tool: 'Edit', file_path: '/proj/app/build.gradle.kts', old_string: 'a', new_string: 'b' })
  await clock.advance(1000)
  expect(calls.length).toBe(0)
})

test('the running-app tab launches the simulator from the project', async ($, on) => {
  const clock = mock.clock(on)
  const calls = engine(on, 'up')
  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'tab-app' })
  await ui.press({ key: 'app-launch' })
  await clock.advance(10)
  expect(calls).toContain('mcp plugin:compose-preview:compose-preview-mcp simulator_launch')
  expect(calls).toContain('mcp plugin:compose-preview:compose-preview-mcp simulator_screenshot')
  expect(await ui.find({ key: 'app-back' })).toBeDefined()
  await ui.unmount()
})
