# Synchronicity2 Project Description

## Problem Statement

Python library developers face a significant challenge:

1. **Async-first libraries** require users to understand asyncio and work within event loops
2. **Sync-only libraries** cannot be used efficiently in async applications
3. **Dual implementations** (both sync and async) lead to:
   - Code duplication and maintenance burden
   - Divergence between sync/async behavior
   - Double the testing surface area

### Why `asyncio.run()` Isn't Enough

Simply wrapping async functions with `asyncio.run()` fails for:
- **Async generators** - can't be wrapped with `asyncio.run()`
- **Persistent connections** - need the same event loop across multiple calls (e.g., database clients)
- **Stateful async objects** - require event loop persistence between method calls

It also adds a lot of code duplication and manual maintenance work to manually have to wrap all async code with sync variants.

## Solution Architecture

Synchronicity 2.0 uses a **strict separation** between build-time and runtime:

### 1. Build-Time Layer (`Module` class + code generation)
- **Lightweight registration**: `Module` class provides decorators to mark async code for wrapper generation
- **(Almost) Zero runtime overhead**: Registration only tracks what to generate, no execution logic
- **Build-time code generation**: CLI tool generates wrapper modules during build/packaging step
- **Uses type annotations**: Instead of generating runtime type checks

### 2. Runtime Layer (`Synchronizer` class)
- **Used ONLY by generated code**: Implementation code never imports or uses Synchronizer
- **Dedicated event loop**: Manages background thread with its own event loop
- **Thread-safe execution**: Executes async code from both sync and async contexts
- **Global registry**: Maintains singleton synchronizers by name
- **Almost no runtime type checking**: In most cases runtime type checking/branching will not be necessary, since
     type annotations provide enough information to generate code statically from the definitions.

### 3. Decoupling:
- Implementation async code typically has no runtime dependency on Synchronizer, unless the user wants to have a manual sync/async wrapper implementation.
- Generated code has no dependencies on the build-time layer, e.g. does no wrapping of types or functions - only pre-compiled translation operations arguments and return values of functions.


## Core Design Philosophy

**Key Principle: Implementation code should be pure async with minimal decoration**

```python
# Implementation: Pure async with lightweight registration
from synchronicity import Module

wrapper_module = Module("my_lib")  # Just metadata!

@wrapper_module.wrap_function  # Just registration
async def fetch_data():
    ...
```

**Benefits:**
- Implementation is only done in async Python, without having to have knowledge of the wrapping layer
- Implementation code has no runtime Synchronizer dependency
- Fast imports of implementation (no synchronizer initialization)
- Testable without wrapper infrastructure
- Very thin library needed at runtime for generated wrappers (can exclude the code generation part)

## Core API

### For Library Developers (Implementation Side)

```python
# _my_library.py (async implementation)
from synchronicity import Module

# Lightweight registration - NO runtime overhead
wrapper_module = Module("my_library")

@wrapper_module.wrap_function
async def fetch_data(url: str) -> dict:
    """Async implementation only - sync wrapper auto-generated at build time"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

@wrapper_module.wrap_class
class DatabaseClient:
    def __init__(self, connection_string: str):
        self._conn_str = connection_string
        self._connection = None

    async def connect(self):
        self._connection = await create_connection(self._conn_str)

    async def query(self, sql: str) -> list[dict]:
        return await self._connection.execute(sql)
```

### Code Generation (Build Step)

```bash
# Using Module objects directly (recommended)
# This is what you'd put in your build script
python -c "
from _my_library import wrapper_module
from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules
from pathlib import Path

modules = compile_modules([wrapper_module], 'my_library_sync')
write_modules(Path('./'), modules)
"

# Using CLI (searches for Module objects in imported modules)
python -m synchronicity.codegen -m _my_library my_library_sync -o ./generated/

# Multi-module projects
python -m synchronicity.codegen \
    -m package._impl_a \
    -m package._impl_b \
    package_sync \
    -o ./package/
```

### For Library Users (Generated API)

```python
# my_library.py (generated wrapper)
from my_library import fetch_data, DatabaseClient

# Synchronous usage (blocks until complete)
data = fetch_data("https://api.example.com/data")
print(data)

db = DatabaseClient("postgresql://localhost/mydb")
db.connect()
results = db.query("SELECT * FROM users")

# Asynchronous usage (via .aio property)
async def main():
    data = await fetch_data.aio("https://api.example.com/data")

    db = DatabaseClient("postgresql://localhost/mydb")
    await db.connect.aio()
    results = await db.query.aio("SELECT * FROM users")

asyncio.run(main())
```

## Project Structure

```
/Users/elias/code/synchronicity/
├── src/synchronicity/               # Main package
│   ├── __init__.py                   # Public API: Module, Synchronizer, get_synchronizer
│   ├── module.py                     # Module class for build-time registration
│   ├── synchronizer.py               # Synchronizer class for runtime execution
│   ├── descriptor.py                 # Python descriptors for method binding
│   └── codegen/                      # Code generation utilities
│       ├── __init__.py
│       ├── __main__.py               # Allows python -m synchronicity.codegen
│       ├── cli.py                    # CLI entry point
│       ├── compile.py                # Code generation engine
│       ├── signature_utils.py        # Signature inspection utilities
│       ├── type_transformer.py       # Type annotation transformation
│       └── writer.py                 # File writing utilities
├── test/                             # Test suite
│   ├── unit/                         # Unit tests
│   │   ├── compile/                  # Code generation tests
│   │   │   ├── test_function_codegen.py
│   │   │   ├── test_class_codegen.py
│   │   │   └── test_type_translation_codegen.py
│   │   └── transformers/
│   │       └── test_type_transformers.py
│   ├── integration/                  # Integration tests
│   │   ├── test_simple_function.py
│   │   ├── test_simple_class.py
│   │   ├── test_class_with_translation.py
│   │   ├── test_multifile.py
│   │   ├── test_nested_generators.py
│   │   ├── test_event_loop_check.py
│   │   └── test_utils.py
│   └── support_files/                # Test fixtures
│       ├── _simple_function.py
│       ├── _simple_class.py
│       ├── _class_with_translation.py
│       ├── _test_impl.py
│       ├── _event_loop_check.py
│       └── multifile/
│           ├── _a.py
│           └── _b.py
├── README.md                         # User documentation
├── pyproject.toml                    # Package configuration
└── synchronicity2.md                 # This file
```

## Key Components Deep Dive

### 1. Module Class ([src/synchronicity/module.py](src/synchronicity/module.py))

**Purpose:** Lightweight build-time registration for code generation

**Key Characteristics:**
- **NO runtime logic** - pure data structure
- **NO Synchronizer dependency** - completely independent
- **Build-time only** - can be removed after generation
- **Simple API** - two decorators: `@wrap_function` and `@wrap_class`

**API:**
```python
class Module:
    def __init__(self, target_module: str):
        """Create a module registration for code generation.

        Args:
            target_module: Name of the generated wrapper module (e.g., "my_lib")
        """

    def wrap_function(self, f: Callable) -> Callable:
        """Register a function for wrapper generation.
        Returns the function unchanged (zero runtime overhead).
        """

    def wrap_class(self, cls: type) -> type:
        """Register a class for wrapper generation.
        Returns the class unchanged (zero runtime overhead).
        """

    def module_items(self) -> dict:
        """Get all registered items (used by code generator)."""

    @property
    def target_module(self) -> str:
        """Get the target module name."""
```

**Usage Example:**
```python
from synchronicity import Module

# Create module registration
wrapper_module = Module("my_public_api")

@wrapper_module.wrap_function
async def my_function(x: int) -> str:
    return f"Result: {x}"

@wrapper_module.wrap_class
class MyClass:
    async def method(self) -> int:
        return 42

# At build time, pass wrapper_module to compile_modules()
```

### 2. Synchronizer Class ([src/synchronicity/synchronizer.py](src/synchronicity/synchronizer.py))

**Purpose:** Runtime execution manager - ONLY used by generated code

**Key Principle:** Implementation code should NEVER import or use Synchronizer

**Where Synchronizer IS used:**
- ✅ Generated wrapper code (`get_synchronizer('name')._run_function_sync(...)`)
- ✅ Test fixtures that need event loop execution

**Where Synchronizer is NOT used:**
- ❌ Implementation code (use `Module` instead)
- ❌ User-facing library code
- ❌ Registration/decoration

**Key Responsibilities:**
- Creates and manages background thread with dedicated event loop
- Executes async functions from sync context (blocks caller)
- Executes async functions from async context (schedules on background loop)
- Handles async generators (converts to sync generators or preserves async)
- Maintains global registry by name for singleton behavior

**Critical Methods:**
- `_start_loop()` - Initializes background thread and event loop
- `_run_function_sync(coro)` - Blocks until async function completes
- `_run_function_async(coro)` - Returns coroutine scheduled on background loop
- `_run_generator_sync(agen)` - Wraps async generator as sync generator
- `_run_generator_async(agen)` - Wraps async generator for async iteration

### 3. CLI Tool ([src/synchronicity/codegen/cli.py](src/synchronicity/codegen/cli.py))

**Entry Point:** `python -m synchronicity.codegen`

**Command-line Arguments:**
```
-m/--module: Implementation module paths (can be specified multiple times)
synchronizer_name: Synchronizer name for generated code (e.g., my_library_sync)
-o/--output-dir: Output directory (default: current directory)
--stdout: Print to stdout instead of writing files
--ruff: Run ruff to format generated code
```

**Workflow:**
1. Imports specified modules (triggers Module registration via decorators)
2. Collects all Module objects from imported modules
3. Performs TYPE_CHECKING reload pass for type annotation resolution
4. Calls `compile_modules()` to generate wrapper code
5. Writes generated code to files or stdout

### 4. Code Generator ([src/synchronicity/codegen/compile.py](src/synchronicity/codegen/compile.py))

**Main Entry Points:**
```python
def compile_modules(
    modules: list[Module],
    synchronizer_name: str
) -> dict[str, str]:
    """Compile Module objects into wrapper code.

    Args:
        modules: List of Module objects with registered functions/classes
        synchronizer_name: Name for get_synchronizer() calls in generated code

    Returns:
        Dict mapping module names to generated Python code
    """
```

**Key Functions:**
- `compile_module(module, synchronizer_name, synchronized_types)` - Generates one module
- `compile_function(f, target_module, synchronizer_name, synchronized_types)` - Wraps function
- `compile_class(cls, target_module, synchronizer_name, synchronized_types)` - Wraps class
- `compile_method_wrapper(...)` - Wraps class methods

**Generated Code Structure for Functions:**
```python
# Generated wrapper class
class _foo:
    def __call__(self, x: int) -> str:
        """Sync interface: blocks until complete"""
        impl_function = _impl.foo
        return get_synchronizer('my_sync')._run_function_sync(impl_function(x))

    async def aio(self, x: int) -> str:
        """Async interface: runs on synchronizer's loop"""
        impl_function = _impl.foo
        return await get_synchronizer('my_sync')._run_function_async(impl_function(x))

_foo_instance = _foo()

@replace_with(_foo_instance)
def foo(x: int) -> str:
    """Sync wrapper implementation"""
    return _foo_instance(x)
```

**Generated Code Structure for Classes:**
```python
class MyClass:
    def __init__(self, arg: str):
        # Create instance of implementation class
        self._impl_instance = _impl.MyClass(arg=arg)

    @classmethod
    def _from_impl(cls, impl_instance):
        """Factory for wrapping existing impl instances"""
        # Uses WeakValueDictionary cache for identity preservation
        cache_key = id(impl_instance)
        if cache_key in _cache_MyClass:
            return _cache_MyClass[cache_key]
        wrapper = object.__new__(cls)
        wrapper._impl_instance = impl_instance
        _cache_MyClass[cache_key] = wrapper
        return wrapper

    @property
    def some_property(self) -> str:
        """Proxy instance attributes"""
        return self._impl_instance.some_property

    # Method wrappers use descriptor pattern
    @replace_with(_MyClass_my_method_instance)
    def my_method(self, x: int) -> str:
        return _MyClass_my_method_instance(self, x)
```

### 5. Type Transformation ([src/synchronicity/codegen/type_transformer.py](src/synchronicity/codegen/type_transformer.py))

**Purpose:** Converts type annotations between wrapper and implementation types

**Architecture:** Composable transformer pattern

**Key Classes:**
- `TypeTransformer` - Abstract base for all transformers
- `IdentityTransformer` - For primitive types (no transformation)
- `WrappedClassTransformer` - For wrapped classes (Foo → Foo._from_impl)
- `ListTransformer` - For lists with element transformation
- `DictTransformer` - For dicts with value transformation
- `TupleTransformer` - For tuples with element transformation
- `OptionalTransformer` - For Optional[T] with inner transformation
- `GeneratorTransformer` - For async generators

**Key Methods:**
- `wrapped_type(synchronized_types, target_module)` - Returns type string for wrapper signature
- `unwrap_expr(synchronized_types, var_name)` - Generates code to extract ._impl_instance
- `wrap_expr(synchronized_types, target_module, var_name)` - Generates code to wrap with _from_impl()
- `needs_translation()` - Returns whether type needs wrapping/unwrapping

**Example Transformation:**
```python
# Input annotation: list[Node] where Node is wrapped
transformer = ListTransformer(WrappedClassTransformer(Node))

# Type signature in wrapper
transformer.wrapped_type(synchronized_types, "my_module")
# → "list[Node]"

# Unwrap expression (wrapper → impl)
transformer.unwrap_expr(synchronized_types, "nodes")
# → "[x._impl_instance for x in nodes]"

# Wrap expression (impl → wrapper)
transformer.wrap_expr(synchronized_types, "my_module", "result")
# → "[Node._from_impl(x) for x in result]"
```

**Supports Complex Types:**
- Generics: `list[Foo]`, `dict[str, Bar]`, `set[Foo]`
- Optionals: `Optional[Foo]`, `Foo | None`
- Nested: `list[dict[str, Optional[Foo]]]`
- Async generators: `AsyncGenerator[Foo, None]`
- Forward references and string annotations

## Usage Examples

### Example 1: Simple Async Function

```python
# _weather.py (implementation)
from synchronicity import Module

wrapper_module = Module("weather")

@wrapper_module.wrap_function
async def get_temperature(city: str) -> float:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.weather.com/{city}") as resp:
            data = await resp.json()
            return data["temperature"]

# Build script: generate_wrappers.py
from _weather import wrapper_module
from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules
from pathlib import Path

modules = compile_modules([wrapper_module], "weather_sync")
write_modules(Path("./"), modules)
```

```python
# User code
from weather import get_temperature

# Synchronous
temp = get_temperature("Seattle")

# Asynchronous
async def main():
    temp = await get_temperature.aio("Seattle")
```

### Example 2: Database Client

```python
# _database.py (implementation)
from synchronicity import Module

wrapper_module = Module("database")

@wrapper_module.wrap_class
class DatabaseClient:
    def __init__(self, connection_string: str):
        self._conn_str = connection_string
        self._connection = None

    async def connect(self):
        self._connection = await asyncpg.connect(self._conn_str)

    async def query(self, sql: str) -> list[dict]:
        return await self._connection.fetch(sql)

    async def close(self):
        await self._connection.close()
```

### Example 3: Multi-Module Project

```python
# package/_models.py
from synchronicity import Module

models_module = Module("package.models")

@models_module.wrap_class
class User:
    def __init__(self, name: str):
        self.name = name

# package/_api.py
from synchronicity import Module
from ._models import User

api_module = Module("package.api")

@api_module.wrap_function
async def get_user(user_id: int) -> User:
    # Fetch user...
    return User(name="Alice")

# Build script
from package._models import models_module
from package._api import api_module
from synchronicity.codegen.compile import compile_modules
from synchronicity.codegen.writer import write_modules
from pathlib import Path

# Compile both modules together (handles cross-references)
modules = compile_modules(
    [models_module, api_module],
    "package_sync"
)
write_modules(Path("./package/"), modules)
```

## Test Suite Overview

**Location:** [test/](test/)
**Test Organization:** Unit tests and integration tests organized by functionality
**Coverage:** Functions, classes, generators, type transformers, and multi-module scenarios

### Running Tests

**IMPORTANT:** Always activate the virtualenv before running tests. Otherwise, binaries
such as pyright that are used by the tests won't be on the PATH and tests will error.

```bash
# Activate virtualenv (required for pytest to be on PATH)
source .venv/bin/activate

# Run all tests
pytest test/

# Run unit tests only (fast)
pytest test/unit/

# Run integration tests only
pytest test/integration/
```

## Design Decisions

### Why Module-Based Registration?

**The Goal:** Pure async implementation code with zero runtime dependencies / overhead for running the original implementation

```python
from synchronicity import Module
wrapper_module = Module("my_lib")  # Just metadata!

@wrapper_module.wrap_function  # Just registration - doesn't change the function
async def foo():
    ...
```

### Design Principle: Build-Time vs Runtime

**Build Time:**
- Module registration
- Code generation
- Type transformation determination
- Static analysis

**Runtime:**
- Synchronizer event loop
- Thread management
- Async execution
- Actual translations of types when the build step has decided so

**Clear Boundary:**
Implementation code should typically never touch the "runtime" (Synchronizer).
Only generated code uses Synchronizer.

## Common Gotchas

1. **Type annotations are required:**
   - Code generation relies on type hints
   - Use `typing` module for complex types

2. **Wrapper instances are proxies:**
   - Direct attribute access limited to properties
   - Use `@property` or getter methods for attributes

3. **Thread overhead:**
   - All sync calls cross thread boundary
   - Minor overhead for function call dispatch

4. **Generated code imports implementation modules:**
   - Implementation modules must remain importable
   - Don't delete implementation code after generation

### Design Principle: async syntax

The async wrapper interface strives to the following guiding principle:
* Async calls use the `await sync_wrapper.aio({args go here})` syntax when something is *await*able
* If something is async *iterable* in the implementation, the wrapper is also directly async iterable (as well as sync), without using `.aio()`. I.e. `async for res in wrapper_iterable: ...`. See reasoning below.
* If something is an async *context manager* in the implementation, the wrapper is also an async contextmanager, `async with wrapper_context_manager`. See reasoning below.

**Reasoning for not using .aio on context managers/iterables**
* Unlike functions, we don't *need* to distinguish objects - a normal function can't be both blocking and a coroutine function at the same time, but something can be both sync and async iterable/context-manageable.
* *If* we made the wrapper *only* sync iterable/contextmanageable, and required `.aio()` to get the async iterable, it would in the general case require a synthetic `[async] def aio()` method or property on wrapped classes that implement the iterable/context manager protocol.
E.g.
```py
@module.wrap_class
class ImplIterable:
    def __aiter__(self):
        yield 1

it = ImplIterable()
async for res in it:
    ...

# Wrapper:
class ImplIterable
    def __iter__():
        ...

    # possibly a property?
    def aio() -> AsyncIterable:
        ...

for res in it:
    ...

async for res in it.aio():
    ...
```

This is a bit odd, since the sync wrapper doesn't require a "function call" to access the iterator. `aio` could possibly also be a property, but then it doesn't look like our other .aio() calls anymore.

What's worse is - what *type* should the return value of `.aio()` have here? It could be an async generator that wraps the underlying iterator, but what if a class is both an iterable *and* a context manager? Or what if the class implements `__await__` or a `__call__` method that returns a coroutine?

In the general case we'd have to make `aio` return a custom generated type that encapsulates all async aspects of the class, except its async methods, which feels pretty ugly and makes static typing hard to reason about.

For these reasons, async iteration and async context managing of objects use the non-`.aio` syntax.

For this to be syntactically consistent with wrapped *functions* that are declared to return AsyncIterable/AsyncContextManager, the wrapper around those functions should be superficially sync (although not do any blocking operation), but have a return values that also allows async iteration (even without using `.aio()` to call the function):

```py
@module.wrap_function
async def foo() -> AsyncIterable[int]:
    yield 1

# Wrapper code:
def foo() -> AsyncAndSyncIterable[int]:
    yield 1

for res in foo():
    ...

async for res in foo():
    ...

```

This requires custom `AsyncAndSyncIterable` and `AsyncAndSyncContextManager` wrapper types, but at least these are limited in scope and don't require custom generation (they can be part of the Synchronicity static runtime library).

It's quite likely that people will make the mistake of calling `async for res in foo.aio():` above though... We could add it as a sync proxy to `foo()` itself, but it may be confusing that we support both syntaxes too...


## Quick Reference

### Key Files
1. [src/synchronicity/module.py](src/synchronicity/module.py) - Module class for build-time registration
2. [src/synchronicity/synchronizer.py](src/synchronicity/synchronizer.py) - Synchronizer class for runtime
3. [src/synchronicity/codegen/compile.py](src/synchronicity/codegen/compile.py) - Code generation
4. [src/synchronicity/codegen/type_transformer.py](src/synchronicity/codegen/type_transformer.py) - Type handling
5. [src/synchronicity/codegen/cli.py](src/synchronicity/codegen/cli.py) - CLI tool

### Key Concepts
- **Module:** Build-time registration (use in implementation)
- **Synchronizer:** Runtime execution (use in generated code only)
- **Dual interface:** `func()` for sync, `func.aio()` for async
- **Type annotations:** Composable transformers handle complex types
