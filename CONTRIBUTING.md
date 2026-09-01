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

## Code conventions

This codebase follows two conventions fairly strictly throughout `engine.py`/`coordinator.py`/etc. — please match them:

- **Docstrings explain *why*, not just *what*.** Code that's easy to read from the signature alone doesn't need repeating in prose; docstrings exist to capture the reasoning, edge cases, and trade-offs a reader couldn't otherwise infer.
- **External dependencies degrade gracefully.** A missing/unavailable entity, a failed evcc request, malformed input — these return `None`/an empty value and let the caller decide what to do, rather than raising and taking down the integration.

`ruff` (config in `pyproject.toml`) enforces basic style; it won't catch the above, code review will.
