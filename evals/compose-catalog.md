# Compose catalog evals

Run these prompts in at least two harnesses with this repository's
`compose-preview` plugin (which carries the canonical `compose-preview` skill and
the hosted catalog server), or `compose-catalogs` on a host with no shell.

## Prompts

1. "Show me wear-m3 EdgeButton variants."
2. "Compare Button vs FilledTonalButton on a small round device."
3. "What does Card look like at font scale 2?"
4. "Render TitleCard in dark theme."
5. "I have no token."

## Expected behaviour

- Discover the catalog and preview identifiers before rendering.
- Default to semantics for inspection and hashes for sweeps.
- Use `render_matrix` with hash observation, then request no more than three
  inline PNGs for cells the user actually needs to see.
- Report a catalog library version only when the service returns one; never
  infer it from the server version.
- For prompt 5, use `request_access`, show its authorization URL, then use
  `poll_access`. Never ask the user to paste a token into chat.

## Results

Not run. Live service credentials and harness sessions are required.
