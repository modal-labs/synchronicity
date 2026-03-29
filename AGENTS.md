## Cursor Cloud specific instructions

This is a pure Python library (`synchronicity`) by Modal Labs. There are no services, databases, or containers to run.

### Dependencies

`uv` is the canonical package/dependency manager. All commands are run through `uv run`.

### Lint / Type-check / Test / Build

Commands are run from the repository root:

- **Lint:** `uv run --group=dev ruff check .` and `uv run --group=dev ruff format --diff .`
- **Type-check:** `uv run --group=dev mypy src/synchronicity`
- **Tests:** `uv run --group=dev pytest -s` (full suite, ~170 tests)
- **README doc tests:** `uv run --group=dev pytest --markdown-docs README.md`
- **Build:** `uv build` (or `make build`)

### Notes

- The project requires Python >= 3.10. The VM ships with Python 3.12.
- `uv` must be on `PATH`; it is installed to `~/.local/bin`. If missing, install with `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- `gevent` tests are only collected on Python < 3.13; on 3.13+ the gevent dependency is excluded.
- Two tests are expected to be skipped (pickle-related and an asyncio-mode test).
- The `shutdown_test.py` tests send SIGINT signals and print "sigint sent" / "cancelled" output — this is expected behavior, not a failure.
