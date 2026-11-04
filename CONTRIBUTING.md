# Contributing to EV Assistant

This is a solo-maintained hobby project — contributions are welcome, but please keep expectations proportionate to that.

## Reporting bugs / requesting features

Open a [GitHub Issue](https://github.com/weskona/ev_assistant/issues). For a bug, include your Home Assistant version and, ideally, a debug log (`custom_components.ev_assistant: debug` — see the README's Troubleshooting section).

## Pull requests

1. Fork the repo and create a branch off `main`.
2. Make your change.
3. Before opening the PR, make sure both of these pass locally:

   ```bash
   ruff check .
   pip install -r requirements_test.txt   # first time only
   pytest tests -q
   ```

4. Open the PR against `main` with a short description of what changed and why.

## Stable interfaces

[docs/stable-interfaces.md](docs/stable-interfaces.md) ([Deutsch](docs/stable-interfaces.de.md)) lists the services, entities, config keys, WebSocket commands and the panel configuration that stay stable within 1.x. It is generated from the code. If you add, rename or remove one of them, run

```bash
python3 .github/scripts/gen_interfaces.py
```

and commit the result; `tests/test_stable_interfaces.py` fails otherwise. Adding something is fine. A removed or renamed entry in the diff of that page is a **breaking change** (needs a major version and a CHANGELOG entry).

## Persisted data

The coordinator keeps its whole persistent state in one dict (`self.data`) that is written to the store and read back on the next start, so every key is a contract with the data users already have on disk. `tests/ha/test_data_contract.py` fails when a key of `_empty_data()` is renamed, removed or gets another default. If that is intended, think about a migration in `async_setup()` first, then regenerate the snapshot:

```bash
UPDATE_DATA_CONTRACT=1 pytest tests/ha/test_data_contract.py
```

## Code conventions

This codebase follows two conventions fairly strictly throughout `engine.py`/`coordinator.py`/etc. — please match them:

- **Docstrings explain *why*, not just *what*.** Code that's easy to read from the signature alone doesn't need repeating in prose; docstrings exist to capture the reasoning, edge cases, and trade-offs a reader couldn't otherwise infer.
- **External dependencies degrade gracefully.** A missing/unavailable entity, a failed evcc request, malformed input — these return `None`/an empty value and let the caller decide what to do, rather than raising and taking down the integration.

`ruff` (config in `pyproject.toml`) enforces basic style; it won't catch the above, code review will.
