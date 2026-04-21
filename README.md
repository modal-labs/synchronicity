CI/CD badge
[pypi badge](https://pypi.python.org/pypi/synchronicity2)

# Synchronicity

Synchronicity generates a synchronous and asynchronous public API from a single async implementation.

## Short example

In short, an async API implementation like:

```py notest
async def foo_impl() -> str:
    return await external_resource()
```

```py notest
from public_api import foo

foo()  # calls foo_impl above without async syntax

await foo.aio()  # but you can also call it async!
```

In addition to simple coroutine functions like above, synchronicity supports wrapping classes with async methods, async iterators, two-way async generators, async context managers and more.

## Usage pattern

At a high level, you use it like this:

- Write implementation code as normal async Python with no special instrumentation.
- Specify `Module` objects as a manifest of output Python modules you want to create from your implementation.
- **Recommended for libraries you ship:** vendor synchronicity2 into a package such as `mylib.synchronicity` (see below) and pass `--runtime-package mylib.synchronicity` to `synchronicity2 wrappers` so generated code does not import top-level `synchronicity2`. Implementation modules can use `from mylib.synchronicity import Module`; your wheel can stay free of a runtime dependency on the PyPI package.
- Generate the public API using the `synchronicity2` CLI as part of your build or packaging step (the CLI / codegen still come from the PyPI install).
- Export the generated module as your user-facing API - complete with both sync and async implementations that delegate to your implementation code. Every function or method gets two call paths:
  - a blocking sync interface like `client.query(...)`
  - an async interface like `await client.query.aio(...)`

## Install

```bash
pip install synchronicity2
```

## Example

`Module` registration is build-time metadata only: the decorators return the original function or class unchanged, without starting a synchronizer or changing how your implementation code runs.

Before you import `Module` from `mylib.synchronicity`, create that package tree once (re-run this when you upgrade synchronicity2 and want to refresh the copy). It writes `src/mylib/synchronicity/` with `module.py`, `types.py`, `descriptor.py`, `synchronizer.py`, and `__init__.py`—check it into source control next to the rest of `mylib`:

```bash
synchronicity2 vendor mylib.synchronicity -o src/
```

Then write a private async implementation module:

```python
# mylib/_weather_impl.py
import collections.abc

from mylib.synchronicity import Module

wrapper_module = Module("mylib.weather")


@wrapper_module.wrap_function()
async def get_temperature(city: str) -> float:
    ...


@wrapper_module.wrap_class()
class WeatherClient:
    default_city: str

    def __init__(self, default_city: str):
        self.default_city = default_city

    async def current(self) -> float:
        ...


@wrapper_module.wrap_function()
async def stream_temperature_readings() -> collections.abc.AsyncGenerator[float, None]:
    """Async generator of sample readings (°C)."""
    yield 17.5
    yield 18.0
    yield 18.5
```

Then generate a public wrapper module:

```bash
synchronicity2 wrappers -m mylib._weather_impl --runtime-package mylib.synchronicity -o src
```

That creates `src/mylib/weather.py`. Your users import the public API with `from mylib.weather import get_temperature, WeatherClient, stream_temperature_readings` (with `src` on your `PYTHONPATH` or installed as a package). By default, `Module` uses the synchronizer name `default_synchronizer` (see `synchronicity2.DEFAULT_SYNCHRONIZER_NAME`); pass a second argument to `Module(...)` if you need multiple isolated synchronizer instances.

## Including unwrapped entries

If a generated module or wrapper class should expose an entry without generating a synchronicity2 wrapper for it, register it as usual and mark the inserted object with `Module.manual_wrapper()`.

```python
from mylib.synchronicity import FunctionWithAio, MethodWithAio, Module
from mylib.synchronicity.descriptor import function_with_aio, method_with_aio

mod = Module("mylib.api")


class _ManualFunctionWithAio(FunctionWithAio):
    def __call__(self, value: int) -> str:
        return self._sync_impl(value)

    async def aio(self, value: int) -> str:
        return f"aio:{value}"


@mod.wrap_function()
@mod.manual_wrapper()
@function_with_aio(_ManualFunctionWithAio)
def manual_function(value: int) -> str:
    return f"sync:{value}"


class _ManualMethodWithAio(MethodWithAio):
    async def aio(self, value: int) -> str:
        return f"aio:{value}"


@mod.wrap_class()
class Client:
    @mod.manual_wrapper()
    @method_with_aio(_ManualMethodWithAio)
    def manual_method(self, value: int) -> str:
        return f"sync:{value}"
```

The generated code re-exports these entries directly instead of parsing signatures and emitting a new wrapper body. At module scope that becomes a simple alias like `manual_function = mylib._impl.manual_function`; inside wrapped classes, the marked attribute is copied into the emitted wrapper class unchanged. The same pattern also works for re-exporting a whole class directly:

```python
@mod.wrap_class()
@mod.manual_wrapper()
class ExistingPublicType:
    ...
```

## Vendoring (recommended for published libraries)

Libraries published to PyPI usually should avoid a **runtime** dependency on the `synchronicity2` package. Instead, check in a copy of the library pieces your code and generated wrappers need under a package you own (for example `mylib.synchronicity`), and pass `--runtime-package` to `synchronicity2 wrappers` so imports point at that tree.

1. **Create or refresh the vendored tree** (paths are created under the output directory):

   ```bash
   synchronicity2 vendor mylib.synchronicity -o src/
   ```

   This writes `src/mylib/synchronicity/` with `module.py`, `types.py`, `descriptor.py`, `synchronizer.py`, and `__init__.py`.

2. **Generate wrappers** using the same dotted path (use `-o src` when each `Module(...)` target is a full name like `mylib.weather`):

   ```bash
   synchronicity2 wrappers -m mylib._weather_impl --runtime-package mylib.synchronicity -o src
   ```

The vendored `__init__.py` re-exports `Module`, `FunctionWithAio`, `get_synchronizer`, `Synchronizer`, and `classproperty`, so implementation code and stubs can use `from mylib.synchronicity import Module` and names like `mylib.synchronicity.FunctionWithAio` without depending on PyPI `synchronicity2` at runtime.

When working on synchronicity2 itself, tests use the default `--runtime-package synchronicity2` so you do not need a vendor step for every edit.

## How generated wrappers behave

Generated wrappers expose a dual interface:

- Regular calls are synchronous and block until the async implementation finishes.
- `.aio(...)` exposes the async variant for awaitable functions and methods.
- Async streams (see below) support both sync `for` and `async for` on the right entry point, depending on how you call the wrapper.

### Functions

```python
from mylib.weather import get_temperature

assert get_temperature("Stockholm") == 20.0


async def main() -> None:
    assert await get_temperature.aio("Stockholm") == 20.0
```

### Classes and methods

```python
from mylib.weather import WeatherClient

client = WeatherClient("Stockholm")
assert client.current() == 21.0


async def main() -> None:
    client = WeatherClient("Stockholm")
    assert await client.current.aio() == 21.0
```

### Async streams (generators, iterators, and iterables)

The compiler uses your **return annotations** to tell async **generators**, **iterators**, and **iterables** apart (`AsyncGenerator[...]`, `AsyncIterator[...]`, `AsyncIterable[...]`, and class methods that implement `__aiter__` / `__anext__`). Use the right shapes in implementation code and generation will produce matching dual sync/async usage.

Here is a **one-way async generator** function from the weather example—sync callers use an ordinary `for` loop; async callers use `.aio()` with `async for` (here driven by `asyncio.run`):

```python
import asyncio

from mylib.weather import stream_temperature_readings

for item in stream_temperature_readings():
    print(item)


async def main() -> None:
    async for item in stream_temperature_readings.aio():
        print(item)


asyncio.run(main())
```

**Two-way** async generators annotated as `AsyncGenerator[YieldType, SendType]` also get first-class wrappers: the sync side supports `.send(...)` and `.close()`, the async side from `.aio(...)` supports `.asend(...)` and `.aclose()`, and cleanup is forwarded so closing the wrapper waits for async generator finalization.

## CLI usage

The package installs a `synchronicity2` CLI with two subcommands: `vendor` (copy runtime into your tree) and `wrappers` (generate public modules from `Module`-registered implementation code).

```bash
synchronicity2 wrappers -m mylib._impl --runtime-package mylib.synchronicity -o src
```

`wrappers` options:

- `-m/--module`: import module containing one or more `Module` objects; repeatable
- `-o/--output-dir`: root directory for generated files; paths mirror the `Module` target (e.g. `Module("mylib.weather")` with `-o src` writes `src/mylib/weather.py`)
- `--stdout`: print generated modules to stdout instead of writing files
- `--ruff`: run `ruff check --fix` and `ruff format` on generated output
- `--runtime-package`: dotted import path for generated imports of `types` / `descriptor` / `synchronizer` (default: `synchronicity2`; use your vendored package when shipping a self-contained wheel)

The same commands work as `python -m synchronicity2.codegen wrappers ...` and `python -m synchronicity2.codegen vendor ...`.

## Low-level runtime API

`Synchronizer` is still part of the public package API, but it is now the lower-level runtime primitive rather than the main authoring model.

In the current architecture:

- library implementation code should usually use `Module`
- generated wrapper code uses `Synchronizer`
- direct `Synchronizer` usage is mainly for advanced/manual cases and internal runtime behavior

## Why this exists

Library authors often want to maintain a single implementation of their API, and async code is usually the most flexible place to do that. It composes well with network and I/O heavy code, works naturally for streaming results, and handles long-lived resources like connections or sessions cleanly.

The problem is that many consumers of a library still want a synchronous interface. They may be writing scripts, working in mostly blocking codebases, or just not want to structure their application around `asyncio` to call one library.

So the real goal is usually not "make async code sync", but "ship one implementation while serving both sync and async users".

You can build that layer manually, but it is inconvenient:

- you have to write and maintain two public interfaces
- wrappers tend to drift from the implementation over time
- classes, methods, and translated argument and return types add a lot of boilerplate
- generators, iterators, and long-lived async state make wrapping logic much more complicated

Simple `asyncio.run()` wrappers are fine for one-off calls, but they are not powerful enough when you need:

- persistent async state across calls (network connections, synchronization primitives etc.)
- async generators, iterators, context manager support
- one implementation that supports both sync and async consumers seemlessly in the same application

## What is supported today

The current codebase and tests cover:

- async functions and functions returning typed `Awaitable[...]`, exposed with `.aio(...)`
- wrapper-side translation of wrapped classes in annotated arguments and return values, including common container shapes like `list[...]`, `tuple[...]`, and `Optional[...]`
- async generators, including two-way generators with `send`/`asend` and cleanup via `close`/`aclose`
- sync and async iteration over wrapped async iterables and iterators
- async context managers, including direct `__aenter__`/`__aexit__` wrappers and functions or methods returning async context manager values
- wrapped classes with public instance methods
- wrapped `classmethod` and `staticmethod`
- sync methods on wrapped classes
- constructor argument translation for wrapped types
- cross-module wrapper generation
- wrapped class inheritance, including mirrored generic bases and wrapped base classes
- generic classes and functions with type variables
- generated properties from annotated public attributes
- type checking of generated wrappers and support files with pyright as part of the integration test suite

When a wrapped class inherits from another wrapped class, the generated wrapper preserves that public inheritance structure. In other words, if your implementation has `WrappedSub(WrappedBase)`, the generated public API also has `WrappedSub(WrappedBase)`, inherited wrapped methods stay available on the subclass, and `isinstance(sub, WrappedBase)` works on the public wrapper side.

## Important rules when authoring implementation code

- Prefer pure async implementation modules.
- Use `Module` (typically `from mylib.synchronicity import Module` when vendored), not `Synchronizer`, in implementation code.
- Add type annotations. Generation relies on them.
- Keep implementation modules importable after generation; generated wrappers import them.
- Public wrapper methods come from public methods on the implementation class.
- Public wrapper properties are derived from annotated public attributes.

## Design decisions

### Combined functions for sync/async usage

- The decision to use `.aio()` "dual" functions was made largely to avoid having to have two different types for every wrapped class (one with async method and one with sync methods). The notable downside to using "dual" functions instead of distinc types is that during async usage it becomes very easy to accidentally use blocking wrappers in async code - causing event loop blockage.
Two other variant were explored a long time ago:
- Auto infer at runtime if functions run inside of event loops and use that info to either run the underlying function blockingly or return an awaitable. This is bad for several reasons - it can't be statically typed, and sync functions that run inside event loops wouldn't be able to await the async awaitable returned anyways ("event loop already running")
- Distinct async and blocking types. The main disadvantages of this is:
  - Usage of both sync and async SDKs in the same application becomes clunky
  - Serialization of wrapped objects somewhat enforces that receiver also use sync or async interface (i.e. "mixed usage in distributed applications")
  - Namespace bloat of the top level namespace (could be mitigated if we make a different top level package for aio)

  Arguably these aren't very strong disadvantages and they can be mitigated by having conversion utilities, so I think we might want to consider distinct types as an alternative wrapper syntax going forward.

### Using the synchronizer event loop for async usage
For async usage, we still use the synchronizer event loop instead of just running it directly on the caller's event loop. This has a couple of advantages:
* Event loop blockage in the user's code won't break library code since the library code runs on its own thread/event loop
* Mixed usage of sync and async APIs in the same applications interoperate well since the library code runs on the same event loop so underlying eventloop specific code can be reused (e.g. network connections)

The big disadvantage is that it introduces additional call stack height and thread synchronization primitives which gives worse performance and traceback readability.

### Iterator syntax
Syntax for async iteration is currently `async for x in async_generator_func(): ...` rather than `async for x in async_generator_func.aio(): ...` which might feel more consistent with the function calling syntax.
The reason for choosing this path is:
* Generalized iterator objects implementing `__aiter__` can exist without being accessed through a callable.

## Practical gotchas

- `.aio(...)` runs implementation code on the generated module's shared synchronizer loop in a background thread, not on the caller's current event loop.
- Wrapped objects are translated back to implementation objects when passed into wrapped functions, methods, and constructors.
- Wrapper identity is preserved across that boundary: if the same implementation object comes back out, you get the same wrapper instance back.
- Async iterables and async iterators preserve their usual semantics. Iterator-like wrappers can be single-use or stateful, while iterable-like wrappers can be iterated repeatedly.
- Wrapped class instances are proxies around implementation instances, so ordinary implementation attributes are not part of the public wrapper unless exposed intentionally.
- Sync calls cross a thread boundary into the synchronizer loop, so there is some dispatch overhead compared with calling the raw implementation directly.
- Generated modules import the implementation modules at runtime, so generation does not make the implementation code disposable.
- Generated wrapper modules import runtime pieces like `synchronicity2.synchronizer` by default, or your vendored path (e.g. `mylib.synchronicity.synchronizer`) when using `--runtime-package`. They do not need `synchronicity2.codegen` at runtime.

## Current limitations

Some design ideas are still future work. In particular, the current implementation does not yet aim to cover every async protocol automatically.

Known gaps worth keeping in mind:

- functions using `Callable[...]` parameters and return values that mention wrapped classes are not translated yet
- unwrapped base classes are not reflected in generated wrapper inheritance

For example, if your implementation looks roughly like:

```python notest
class UnwrappedBase:
    def unwrapped_method(self) -> bool:
        return True


@mod.wrap_class()
class WrappedBase(UnwrappedBase):
    async def wrapped_method(self) -> list[int]:
        return []
```

then the generated wrapper exposes `wrapped_method`, but it does not expose `unwrapped_method` on the public wrapper class by default.

This is intentional. Wrapper instances are proxies around implementation instances rather than actual subclasses of the implementation classes, so an unwrapped base method would run with a different `self` object than the implementation class expects. In practice, that means inherited unwrapped code could observe or mutate different attributes than it would on the real implementation instance. Wrapped bases are safe to mirror because their public methods are re-generated against the wrapper model; unwrapped bases are not mirrored automatically for that reason.

## Typing caveats

The generated APIs are tested with pyright, including consumer-side usage examples, but some advanced typing forms still have rough edges.

Known caveats include:

- Plain callback translation is also not typed correctly yet. For example, shapes like `Callable[[Node], Node]` and `Callable[[Node], int]` are not rewritten to the public wrapper type consistently, so user-facing callback signatures do not type check cleanly.

## Runtime architecture

Generated code uses `get_synchronizer(name)` to obtain a shared `Synchronizer`.

That runtime component:

- owns a dedicated event loop in a background thread
- runs async work for sync callers
- also provides the async `.aio(...)` path on the same isolated loop
- preserves wrapper identity for wrapped classes via `_from_impl(...)`

Implementation modules should usually not need to import `Synchronizer` directly.

## Repository layout

- `src/synchronicity2/module.py`: build-time registration API
- `src/synchronicity2/synchronizer.py`: runtime execution engine
- `src/synchronicity2/descriptor.py`: wrapper code for "dual" functions/methods (.aio enabled callables)
- `src/synchronicity2/types.py`: shared sync-or-async iterable/iterator runtime helpers
- `src/synchronicity2/codegen/`: wrapper (build time) generation logic and CLI
- `test/support_files/`: example impl modules and type check files used by integration tests
- `generated/`: temporary output directory used in tests and local inspection

## Migrating from 0.x

The main architectural difference from Synchronicity `0.x` is that `2.x` is code-generation-based whereas `0.x` used runtime determination of how to proxy each call. The interface from a user of a library is still 99% backwards compatible, but the authoring process is slightly changed.

In `0.x`, the typical model was:

- create a `Synchronizer` in library code
- wrap functions and classes directly using a `@synchronizer.wrap()` decorator. The resulting entity could be used directly at runtime - no preprocessing step needed. This is the entity that was exposed as the public API.
- optionally run a build-time type-stub generation step to give the wrappers static types

In `2.x`, the typical model is:

- keep implementation modules as normal async Python with simple markers for what to translate
- register functions and classes with `Module` manifests
- generate wrapper source files ahead of time
- publish or import those generated modules as the public API

Migration considerations:

- Separate the modules where implementation is defined from the ones where the "public" wrappers are defined
- Replace `@synchronizer.wrap` authoring patterns with `@wrapper_module.wrap_function` and `@wrapper_module.wrap_class`.
- Keep implementation modules importable after generation, since generated wrappers import them.
- Add or tighten type annotations if older code relied on runtime inspection; the new compiler uses annotations heavily.
- If you previously documented direct `Synchronizer` usage as the primary user-facing pattern, update examples to show generated modules instead.
- Treat `Synchronizer` as a lower-level primitive that still exists, but is no longer the main recommended entry point for library authors.

## Development / Contribution

See AGENTS.md
