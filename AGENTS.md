# Synchronicity repo guidance

## Core architecture

- Treat Synchronicity 2 as a build-time plus runtime split, with the bulk of logic being in the build-time part of the library.
- The thin runtime library is mainly responsible for setting up a dedicated event loop on a different thread and sending workloads/getting results to that event loop in a safe way
- Implementation modules that *use* synchronicity should be pure async Python and should usually use `Module`, not `Synchronizer`.
- Generated wrapper modules are the public API for a library
- Keep the separation clear: registration and code generation at build time, event-loop execution at runtime
- There are two types of "type translation" that needs to happen at the call boundary between the wrapper functions and impementation functions:
  - Async -> sync translations. E.g. making sure that an `Awaitable[X]` is translated to `X` in the return annotation.
  - Synchronized type translation - Users are expected to interact using wrapper classes which are distinct from the wrapped implementation class. Synchronicity wrappers should always translate wrapper classes into implementation ones before they are passed to implementation.
- The determination of what to translate should be statically determinated at gencode time by looking at function signatures - never through runtime type inspection except possibly in very niche use cases like `Union` types.

## Development practices
- Always ask the user before relaxing type annotations
- Prefer clean refactors and a single obvious name over backward-compatibility aliases or duplicate APIs. There is no obligation to preserve synchronicity 0.x naming or shims; keep changes minimal but do not carry legacy aliases “just in case.” If `pytest test/integration/` (and the rest of the suite) still passes, the change is acceptable.
- Use `uv` for managing dependencies and virtualenvs. For local development in this repo:
  ```bash
  uv sync --dev
  source .venv/bin/activate
  ```
- When implementing new features, start out by creating an end to end integration test that assumes the new feature already exists in its future form (TDD). This test is expected to initially fail for a new feature. Then implement the code changes necessary to make the test + other such tests to pass.
- For integration tests, make sure to test both runtime logic assumptions and static type checking of the generated wrapper classes
- Ask before making changes to integration tests themselves to make tests pass. Unit tests can be changed more permissively if the output syntax in gencode is intentionded to change.
- When running pytest, always activate the virtualenv in `.venv` first.
- The `.venv` activation is also required for repo-local tools such as `pyright`; run test, lint, and type-check commands in the same shell after `source .venv/bin/activate`.
- Before pushing code, run the repo's pre-commit hooks and fix any reported lint or format issues. Install once per clone with `pre-commit install`; run all hooks manually with `pre-commit run --all-files` (or rely on hooks at commit time).
- Update docs and examples to reflect changes and new features as they are added
- Preserve accurate feature documentation by checking the current source and tests
- Use type annotations in examples and implementation - code generation depends on them.
- Avoid introducing runtime dependencies from implementation code onto generated-code helpers unless there is a deliberate design reason.
- Generated files under `generated/` are typically transient test or inspection artifacts; do not hand-edit them unless the task is specifically about generated output. They can be used to debug the output of integration tests after having run a test.

## Testing and verification

- Primary test command:
  - `source .venv/bin/activate && pytest test/`
- Useful focused commands:
  - `source .venv/bin/activate && pytest test/unit/`
  - `source .venv/bin/activate && pytest test/integration/`
- Integration tests generate wrapper modules into `generated/`.
- Type-checking coverage is part of the test story; integration tests use `pyright` against generated modules and support files.

## Repository structure

- `src/synchronicity/__init__.py`: public exports
- `src/synchronicity/module.py`: build-time registration API
- `src/synchronicity/synchronizer.py`: runtime event-loop execution engine
- `src/synchronicity/descriptor.py`: descriptors for dual sync/async method access
- `src/synchronicity/types.py`: shared sync-or-async iterable helpers
- `src/synchronicity/codegen/`: build-time utilities - should never be imported by runtime code; see `ARCHITECTURE.md` for parse IR vs emission layering
- `test/unit/`: codegen and transformer unit tests
- `test/integration/`: end-to-end wrapper generation and runtime behavior tests
- `test/support_files/`: example implementation modules used to generate wrappers in tests
- `generated/`: local/generated wrapper output used in tests and debugging
