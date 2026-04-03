CI/CD badge
[pypi badge](https://pypi.python.org/pypi/synchronicity)

# Synchronicity

Synchronicity generates a synchronous and asynchronous public API from a single async implementation.

## Short example

In short, an async API implementation like:

```py
async def foo_impl() -> str:
    return await external_resource()
```

```py
from public_api import foo

foo()  # calls foo_impl above without async syntax

await foo.aio()  # but you can also call it async!
```

In addition to simple coroutine functions like above, synchronicity supports wrapping classes with async methods, async iterators, two-way async generators, async context managers and more.

## Usage pattern

At a high level, you use it like this:

- Write implementation code as normal async Python with no special instrumentation.
- Specify `Module` objects as a manifest of output Python modules you want to create from your implementation.
- Generate the public API using the `synchronicity` cli as part of your build or packaging step.
- Export the generated module as your user-facing API - complete with both sync and async implementations that delegate to your implementation code. Every function or method gets two call paths:
  - a blocking sync interface like `client.query(...)`
  - an async interface like `await client.query.aio(...)`

## Install

```bash
pip install synchronicity
```

## Example

`Module` registration is build-time metadata only: the decorators return the original function or class unchanged, without starting a synchronizer or changing how your implementation code runs.

You write a private async implementation module:

```python
# _weather_impl.py
from synchronicity import Module

wrapper_module = Module("weather")


@wrapper_module.wrap_function
async def get_temperature(city: str) -> float:
    ...


@wrapper_module.wrap_class
class WeatherClient:
    default_city: str

    def __init__(self, default_city: str):
        self.default_city = default_city

    async def current(self) -> float:
        ...
```

Then generate a public wrapper module:

```bash
synchronicity weather_synchronizer -m _weather_impl -o .
```

That creates `weather.py`, which your users import.

## How generated wrappers behave

Generated wrappers expose a dual interface:

- Regular calls are synchronous and block until the async implementation finishes.
- `.aio(...)` exposes the async variant for awaitable functions and methods.
- Async iterables stay directly iterable in both sync and async code.

### Functions

```python
from weather import get_temperature

value = get_temperature("Stockholm")


async def main() -> None:
    value = await get_temperature.aio("Stockholm")
```

### Classes and methods

```python
from weather import WeatherClient

client = WeatherClient("Stockholm")
value = client.current()


async def main() -> None:
    client = WeatherClient("Stockholm")
    value = await client.current.aio()
```

### Iterables and iterators

For wrapped async iterables, the wrapper object itself supports both `for` and `async for`:

```python
for item in stream_values():
    print(item)


async def main() -> None:
    async for item in stream_values():
        print(item)
```

This also applies to wrapped classes that implement async iteration. Use `.aio(...)` for awaitable functions and methods; for iterable results, use `for` and `async for` directly on the wrapper object. Iterator-like wrappers preserve exhaustion and state in the same way the underlying async iterator does.

### Async generators

Wrapped async generators support both simple iteration and full generator interaction.

For one-way generators, use them as normal in sync and async code:

```python
for item in stream_values():
    print(item)


async def main() -> None:
    async for item in stream_values.aio():
        print(item)
```

For two-way generators annotated as `AsyncGenerator[YieldType, SendType]`, the generated wrappers preserve `send` and close behavior:

- the sync wrapper behaves like a normal generator and supports `.send(...)` and `.close()`
- the async wrapper returned by `.aio(...)` supports `.asend(...)` and `.aclose()`

Cleanup is forwarded correctly, so closing the wrapper waits for async generator finalization to finish.

The positional argument `s` above is the synchronizer name embedded into the generated code. It identifies the shared runtime synchronizer instance used by that generated module set.

### 3. Import the generated API

```python
from simple_function import simple_add, simple_generator

assert simple_add(1, 2) == 3


async def main() -> None:
    assert await simple_add.aio(1, 2) == 3

for item in simple_generator():
    print(item)


async def consume() -> None:
    async for item in simple_generator():
        print(item)
```

## CLI usage

The package installs a `synchronicity` CLI:

```bash
synchronicity -m my_package._impl my_sync
```

Common options:

- `-m/--module`: import module containing one or more `Module` objects; repeatable
- `-o/--output-dir`: directory where generated files should be written
- `--stdout`: print generated modules to stdout instead of writing files
- `--ruff`: run `ruff check --fix` and `ruff format` on generated output

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
- Use `Module`, not `Synchronizer`, in implementation code.
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
- Generated wrapper modules import runtime pieces like `synchronicity.synchronizer`, but they do not need `synchronicity.codegen` at runtime.

## Current limitations

Some design ideas are still future work. In particular, the current implementation does not yet aim to cover every async protocol automatically.

Known gaps worth keeping in mind:

- functions using `Callable[...]` parameters and return values that mention wrapped classes are not translated yet
- unwrapped base classes are not reflected in generated wrapper inheritance

For example, if your implementation looks roughly like:

```python
class UnwrappedBase:
    def unwrapped_method(self) -> bool:
        return True


@mod.wrap_class
class WrappedBase(UnwrappedBase):
    async def wrapped_method(self) -> list[int]:
        return []
```

then the generated wrapper exposes `wrapped_method`, but it does not expose `unwrapped_method` on the public wrapper class by default.

This is intentional. Wrapper instances are proxies around implementation instances rather than actual subclasses of the implementation classes, so an unwrapped base method would run with a different `self` object than the implementation class expects. In practice, that means inherited unwrapped code could observe or mutate different attributes than it would on the real implementation instance. Wrapped bases are safe to mirror because their public methods are re-generated against the wrapper model; unwrapped bases are not mirrored automatically for that reason.

## Typing caveats

The generated APIs are tested with pyright, including consumer-side usage examples, but some advanced typing forms still have rough edges.

Known caveats include:

- A `TypeVar` bound to a wrapped class is not typed cleanly today in all generated contexts. For example, `T = TypeVar("T", bound="SomeClass")` combined with a method like `async def tuple_to_list(self, items: tuple[T, ...]) -> list[T]` currently produces pyright errors in the generated wrapper, with mismatches like `"SomeClass*" is not assignable to "SomeClass"`.
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

- `src/synchronicity/module.py`: build-time registration API
- `src/synchronicity/synchronizer.py`: runtime execution engine
- `src/synchronicity/descriptor.py`: wrapper code for "dual" functions/methods (.aio enabled callables)
- `src/synchronicity/types.py`: shared sync-or-async iterable/iterator runtime helpers
- `src/synchronicity/codegen/`: wrapper (build time) generation logic and CLI
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