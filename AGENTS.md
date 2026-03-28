# Synchronicity repo guidance

## Core architecture

- Treat Synchronicity 2 as a build-time plus runtime split, with the bulk of logic being in the build-time part of the library.
- Implementation modules that *use* synchronicity should be pure async Python and should usually use `Module`, not `Synchronizer`.
- Generated wrapper modules are the public API and are the layer that calls `get_synchronizer(...)`.
- Keep the separation clear: registration and code generation at build time, event-loop execution at runtime.

## Development practices

- When implementing new features, start out by creating an end to end integration test that assumes the new feature already exists in it's future form. This test is expected to initially fail. Then implement the code changes necessary to make the test + other such tests to pass.
- Ask before making changes to integration tests themselves to make tests pass. Unit tests can be changed more permissively if the output syntax in gencode is intentionded to change.
- When running pytest, always activate the virtualenv in `.venv` first.
- Update docs and examples to reflect changes and new features as they are added
- Preserve accurate feature documentation by checking the current source and tests
- Use type annotations in examples and implementation fixtures; code generation depends on them.
- Avoid introducing runtime dependencies from implementation code onto generated-code helpers unless there is a deliberate design reason.
- Prefer concise docs that explain the public authoring model: write async impls, register with `Module`, generate wrappers, import generated modules.
- Generated files under `generated/` are typically transient test or inspection artifacts; do not hand-edit them unless the task is specifically about generated output.
- The `oldtests` directory exists temporarily as a way to backport certain tests from synchronicity 0.x - don't maintain or change those tests in the current location - they are expected to fail.

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
- `src/synchronicity/codegen/`: compiler, CLI, signature handling, and writer utilities
- `test/unit/`: codegen and transformer unit tests
- `test/integration/`: end-to-end wrapper generation and runtime behavior tests
- `test/support_files/`: example implementation modules used to generate wrappers in tests
- `generated/`: local/generated wrapper output used in tests and debugging

## Feature expectations to keep in mind

- Supported areas are driven by the current code and tests, including wrapped functions, classes, iterables, inheritance, generics, and `classmethod`/`staticmethod`.
- Public wrapper properties currently come from annotated public attributes on wrapped classes.
- Some design ideas are still aspirational; do not assume every TODO item is already implemented.