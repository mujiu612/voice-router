# Contributing to voice-router

Thanks for your interest in improving `voice-router`.

This project is intentionally structured around clear layers: routing, generation, validation, transcoding, and delivery. Contributions are most useful when they preserve that separation.

## Ways to contribute

- report bugs
- suggest improvements to routing or delivery behavior
- improve provider integrations
- expand documentation and failure cases
- add tests for regressions and config drift

## Development principles

Please keep these project rules in mind:

1. **Configuration first**  
   Default behavior should live in `voice_router.json` whenever practical.

2. **Do not collapse layers together**  
   Routing logic should not silently absorb delivery logic, and provider wrappers should not become platform-specific dispatchers.

3. **Fallback must be explicit**  
   If a model or provider can fail, the handoff to the next candidate should remain visible and inspectable.

4. **Validation is part of the feature**  
   Returning a file path is not enough. Audio outputs should be validated when the workflow depends on them.

5. **Prefer repo-relative examples**  
   Avoid machine-specific paths such as `/Users/...` or `/home/...` in committed docs or scripts.

## Local workflow

Typical checks before opening a pull request:

```bash
python3 scripts/validate_config.py --config voice_router.json
python3 scripts/smoke_tests.py
python3 scripts/provider_integration_smoke.py \
  --config voice_router.json \
  --providers noizai minimax \
  --models model_noiz_default model_minimax_formal
```

If your change touches only docs, mention that in the PR.
If your change affects provider behavior, include the exact validation steps you ran.

## Pull request guidance

Please aim to include:

- a clear summary of what changed
- why the change is needed
- any config, provider, or platform implications
- before/after behavior when relevant
- follow-up work that is intentionally left out

Small, focused PRs are strongly preferred over large mixed changes.

## Documentation updates

When changing any of the following, update the matching docs in the same PR:

- `voice_router.json`
- script input/output contracts
- provider behavior
- delivery assumptions
- failure handling

Relevant docs usually live under `references/`.

## Reporting bugs

When filing an issue, include as much of the following as possible:

- the command you ran
- the expected behavior
- the actual behavior
- relevant config excerpt
- provider or platform involved
- sanitized logs or error output

Please remove secrets, tokens, personal addresses, and machine-local paths before posting.

## Security

For vulnerabilities or sensitive issues, do **not** open a public issue first.
Please follow the process in [SECURITY.md](./SECURITY.md).
