# Synchronicity2 Project Description

## Overview

**Synchronicity2** is a Python library code generation tool that automatically creates both synchronous and asynchronous APIs from a single async implementation. It solves the dual-API problem that Python library developers face when supporting both async and sync users.

**Package Name:** `synchronicity` (published name)
**Module Name:** `synchronicity` (internal/development name)
**Python Version:** 3.9+
**License:** Apache 2.0
**Maintainer:** Modal Labs

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

## Solution Architecture

Synchronicity2 uses a **strict separation** between build-time and runtime:

### 1. Build-Time Layer (`Module` class + code generation)
- **Lightweight registration**: `Module` class provides decorators to mark async code for wrapper generation
- **Zero runtime overhead**: Registration only tracks what to generate, no execution logic
- **Build-time code generation**: CLI tool generates wrapper modules during build/packaging step
- **No coupling**: Implementation code has NO runtime dependency on Synchronizer

### 2. Runtime Layer (`Synchronizer` class)
- **Used ONLY by generated code**: Implementation code never imports or uses Synchronizer
- **Dedicated event loop**: Manages background thread with its own event loop
- **Thread-safe execution**: Executes async code from both sync and async contexts
- **Global registry**: Maintains singleton synchronizers by name

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
- Implementation code has no runtime Synchronizer dependency
- Faster imports (no synchronizer initialization)
- Clearer separation: registration vs execution
- Testable without wrapper infrastructure
- Can delete wrapper generation code after build

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
python -m synchronicity.cli -m _my_library my_library_sync -o ./generated/

# Multi-module projects
python -m synchronicity.cli \
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
│   ├── __init__.py                   # Public API: Module, get_synchronizer
│   ├── synchronizer.py               # Module + Synchronizer classes
│   ├── cli.py                        # CLI entry point
│   ├── descriptor.py                 # Python descriptors for method binding
│   └── codegen/                      # Code generation utilities
│       ├── __init__.py
│       ├── compile.py                # Code generation engine
│       ├── type_transformer.py       # Type annotation transformation
│       └── writer.py                 # File writing utilities
├── test/synchronicity2_tests/        # Comprehensive test suite (98 tests)
│   ├── compile_function_test.py      # Function wrapper generation
│   ├── compile_sync_function_test.py # Sync function tests
│   ├── wrapper_class_test.py         # Class wrapper generation
│   ├── type_transformers_test.py     # Type transformation tests
│   ├── translation_integration_test.py  # Type translation pipeline
│   ├── codegen_integration_test.py   # End-to-end generation
│   ├── multifile_integration_test.py # Multi-module tests
│   └── support_files/                # Test fixtures (all use Module)
│       ├── _simple_function.py
│       ├── _simple_class.py
│       ├── _class_with_translation.py
│       └── multifile/
│           ├── _a.py
│           └── _b.py
├── README.md                         # User documentation
├── pyproject.toml                    # Package configuration
└── SYNCHRONICITY2.md                 # This file
```

## Key Components Deep Dive

### 1. Module Class ([src/synchronicity/synchronizer.py](src/synchronicity/synchronizer.py))

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

### 3. CLI Tool ([src/synchronicity/cli.py](src/synchronicity/cli.py))

**Entry Point:** `python -m synchronicity.cli`

**Command-line Arguments:**
```
-m/--modules: Implementation module paths (e.g., _my_library)
synchronizer_name: Synchronizer name for generated code (e.g., my_library_sync)
-o/--output: Output directory (optional, stdout if omitted)
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

## Design Patterns

### 1. Build-Time Registration Pattern

```python
# Module class is pure data - no execution logic
class Module:
    def __init__(self, target_module: str):
        self._target_module = target_module
        self._registered_functions = {}
        self._registered_classes = {}

    def wrap_function(self, f):
        # Just register - no runtime overhead
        self._registered_functions[f] = (self._target_module, f.__name__)
        return f  # Return unchanged
```

**Benefits:**
- Zero runtime overhead for implementation code
- Implementation can be imported without Synchronizer
- Clear separation: registration vs execution
- Testable without wrapper infrastructure

### 2. Proxy Pattern (Generated Wrappers)

- Wrapper classes delegate to `_impl_instance`
- Transparent method and property forwarding
- Interface transformation (async → sync + async)

### 3. Descriptor Pattern

- Custom `__get__` behavior for method access
- Returns wrapper objects with dual interface
- Clean separation of sync/async calling conventions

### 4. Factory Pattern with Caching

```python
_cache_MyClass: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

@classmethod
def _from_impl(cls, impl_instance):
    cache_key = id(impl_instance)
    if cache_key in _cache_MyClass:
        return _cache_MyClass[cache_key]
    wrapper = object.__new__(cls)
    wrapper._impl_instance = impl_instance
    _cache_MyClass[cache_key] = wrapper
    return wrapper
```

- Preserves object identity: same impl → same wrapper
- Automatic cleanup via weak references
- Critical for: `assert some_function(obj) is obj`

### 5. Thread Isolation Pattern

- All async code runs on dedicated background thread
- Sync calls block on `concurrent.futures.Future`
- Async calls use `asyncio.run_coroutine_threadsafe()`
- Prevents event loop blocking in both library and user code

### 6. Composable Type Transformers

```python
# Build complex transformers from simple ones
list_of_optional_nodes = ListTransformer(
    OptionalTransformer(
        WrappedClassTransformer(Node)
    )
)

# Unwrapping is composable
list_of_optional_nodes.unwrap_expr(synchronized_types, "items")
# → "[None if x is None else x._impl_instance for x in items]"
```

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
**Total Tests:** 101 tests across 7 test files organized by abstraction layer
**Pass Rate:** 101 passing (100%)

### Running Tests

**IMPORTANT:** Always activate the virtualenv before running tests:

```bash
# Activate virtualenv (required for pytest to be on PATH)
source .venv/bin/activate

# Run all tests
pytest test/

# Run unit tests only (fast)
pytest test/unit/

# Run integration tests only
pytest test/integration/

# Run specific test file
pytest test/unit/compile/test_function_codegen.py

# Run tests with verbose output
pytest test/ -v

# Run tests with coverage
pytest test/ --cov=synchronicity
```

**Note:** Some tests require `pyright` for type checking validation:
```bash
npm install -g pyright  # Install pyright globally
```

### Test Organization

Tests are organized by abstraction layers for clear separation of concerns:

```
test/
├── unit/                          # Pure unit tests (no execution, no I/O)
│   ├── compile/                   # Code generation units
│   │   ├── test_function_codegen.py    # 26 tests - async/sync/generator functions
│   │   ├── test_class_codegen.py       # 10 tests - class wrapper generation
│   │   └── test_module_codegen.py      # 3 tests - module-level compilation
│   │
│   └── transformers/              # Type transformation units
│       └── test_type_transformers.py   # 53 tests - all transformer types
│
├── integration/                   # Integration tests (execution, I/O)
│   ├── test_codegen_execution.py       # 6 tests - execute generated code
│   ├── test_type_translation.py        # 5 tests - type translation runtime
│   ├── test_multifile.py               # 2 tests - multi-module scenarios
│   └── test_type_checking.py           # 5 tests - pyright validation (requires pyright)
│
└── support_files/                 # Test fixtures using Module API
    ├── _simple_function.py             # Basic functions
    ├── _simple_class.py                # Async class examples
    ├── _class_with_translation.py      # Wrapped type examples
    ├── _test_impl.py                   # Translation test fixtures
    ├── _event_loop_check.py            # Event loop validation
    └── multifile/                      # Cross-module tests
        ├── _a.py
        └── _b.py
```

### Adding New Tests

**Where to add new tests:**

- **Function compilation** → `test/unit/compile/test_function_codegen.py`
- **Class compilation** → `test/unit/compile/test_class_codegen.py`
- **Type transformers** → `test/unit/transformers/test_type_transformers.py`
- **Execution/runtime** → `test/integration/test_codegen_execution.py`
- **Type checking** → `test/integration/test_type_checking.py`
- **Multi-module** → `test/integration/test_multifile.py`

### Test Fixtures (All Use Module API)

**Support Files:** [test/support_files/](test/support_files/)
- `_simple_function.py` - Module("test_support") with basic functions
- `_simple_class.py` - Module("simple_class_lib") with async class
- `_class_with_translation.py` - Module("translation_lib") with wrapped types
- `_test_impl.py` - Module("test_lib") for translation tests
- `_event_loop_check.py` - Module("event_loop_test") for runtime tests
- `multifile/_a.py` and `multifile/_b.py` - Cross-module dependency tests

## When to Use Synchronicity2

### Good Use Cases

1. **Library Development**
   - Building async-first Python library
   - Want to support both sync and async users
   - Want to avoid code duplication

2. **Database Clients / Connection Pools**
   - Persistent connections across calls
   - Need same event loop for connection lifecycle
   - Users might use sync or async patterns

3. **API Clients**
   - HTTP clients with session management
   - WebSocket clients with persistent connections
   - Any client requiring stateful async connections

4. **Event Loop Isolation**
   - Protect library code from user's event loop blocking
   - Protect user code from library's event loop blocking
   - Need separate thread for library execution

### When NOT to Use

1. **Pure sync code** - no need for async/sync bridging
2. **Simple stateless functions** - `asyncio.run()` might suffice
3. **Performance-critical hot paths** - thread overhead may matter
4. **UI frameworks** - might need to run on main thread

## Important Design Decisions

### Why Module-Based Registration?

**The Goal:** Pure async implementation code with zero runtime dependencies

```python
from synchronicity import Module
wrapper_module = Module("my_lib")  # Just metadata!

@wrapper_module.wrap_function  # Just registration
async def foo():
    ...
```

**Benefits:**
1. ✅ Zero runtime dependency on Synchronizer
2. ✅ Lightweight - just data structure
3. ✅ Clear separation: registration vs execution
4. ✅ Testable pure async code
5. ✅ Can delete after code generation

### Design Principle: Build-Time vs Runtime

**Build Time:**
- Module registration
- Code generation
- Type transformation
- Static analysis

**Runtime:**
- Synchronizer event loop
- Thread management
- Async execution
- Only in generated wrappers

**Clear Boundary:**
Implementation code should NEVER touch runtime (Synchronizer).
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

## Quick Reference

### Key Files
1. [src/synchronicity/synchronizer.py](src/synchronicity/synchronizer.py) - Module + Synchronizer classes
2. [src/synchronicity/codegen/compile.py](src/synchronicity/codegen/compile.py) - Code generation
3. [src/synchronicity/codegen/type_transformer.py](src/synchronicity/codegen/type_transformer.py) - Type handling
4. [README.md](README.md) - User documentation

### Key Concepts
- **Module:** Build-time registration (use in implementation)
- **Synchronizer:** Runtime execution (use in generated code only)
- **Dual interface:** `func()` for sync, `func.aio()` for async
- **Background thread:** All async code runs on dedicated event loop
- **Identity preservation:** WeakValueDictionary ensures wrapper uniqueness
- **Type transformation:** Composable transformers handle complex types

### Main Entry Points
- **Implementation:** `from synchronicity import Module`
- **Generated code:** `from synchronicity import get_synchronizer`
- **Build script:** `from synchronicity.codegen.compile import compile_modules`
- **CLI:** `python -m synchronicity.cli`
- **Tests:** `source .venv/bin/activate && pytest test/`

---

## TODO

### High Priority

- [ ] **Add support for async context managers**
  - Implement `__aenter__` and `__aexit__` wrapper generation
  - Support both `with` (sync) and `async with` (async) usage
  - Test with real-world use cases (database connections, file handles)

- [ ] **Add support for wrapping generic types**
  - Support `TypeVar` and generic class parameters
  - Handle `Generic[T]` base classes correctly
  - Preserve generic type information in generated signatures

- [ ] **Add tests that generated code is valid across Python 3.9+ versions**
  - Test code generation on Python 3.9, 3.10, 3.11, 3.12, 3.13
  - Verify type annotation syntax compatibility (e.g., `list[T]` vs `List[T]`)
  - Test with different typing features per version

- [ ] **Restructure integration tests to use session-scoped fixtures**
  - Generate wrapper code once per test session (significant speedup)
  - Cache compiled modules as fixtures
  - Reuse generated code across multiple tests
  - Measure and document performance improvement

### Medium Priority

- [ ] **Improve error messages in code generation**
  - Better diagnostics when type annotations are missing
  - Clear error messages for unsupported type constructs
  - Helpful suggestions for common mistakes

- [ ] **Add support for property setters**
  - Currently only getters are supported
  - Generate property setter wrappers for mutable attributes
  - Handle property deletion (`@property.deleter`)

- [ ] **Optimize generated code size**
  - Reduce boilerplate in generated wrappers
  - Share common code between similar wrappers
  - Consider template-based generation

- [ ] **Add Python 3.13+ improvements**
  - Support new type annotation syntax
  - Leverage performance improvements in asyncio
  - Test with free-threaded Python

### Low Priority

- [ ] **Better CLI ergonomics**
  - Add `--watch` mode for development
  - Support glob patterns for module discovery
  - Add `--check` mode to verify without writing files

- [ ] **Documentation improvements**
  - Add video walkthrough
  - More real-world examples
  - Migration guide from other async/sync bridging solutions

- [ ] **Performance profiling**
  - Benchmark thread overhead
  - Optimize hot paths in Synchronizer
  - Consider alternative execution strategies for high-performance use cases

- [ ] **IDE support**
  - Verify PyCharm/VSCode jump-to-definition
  - Better type checking integration

---

**Last Updated:** 2025-01-25
**Codebase Branch:** `freider/synchronicity2-vibes`
**Test Status:** 101/101 passing (100%) 🎉
