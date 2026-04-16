## TODO
### Known bugs
- [ ] Generated properties for attributes don't type translate at the moment (important for wrapped classes being passed in and out)

### High Priority
- [ ] **Add tests that generated code is valid across Python 3.10+ versions**
  - The code generation process could require a newer Python version
  - Output types needs to still be backwards compatible with Python 3.10+ for now
  - Test generated code across Python versions

- [ ] Add support for explicit @property - break synchronicity 1 backwards compatibility by raising if the underlying function is async
- [ ] Add support for synchronicity-specific @classproperty decorator. Similarly, only allow sync non-blocking methods to be used

- [ ] **First class support for opt-in manual wrapper implementations**
  This is useful when the function needs to do stuff that should not be part of the synchronizer event loop, like consuming data from iterators passed by users that may not be thread safe, or risk being blocking.
  We could export the MethodWithAio
  
### Medium Priority
- [ ] **Investigate generics whose type parameters may or may not be bound to wrapped classes**
  - For a `TypeVar` with a bound that is (or normalizes to) a wrapped implementation type, translation at the boundary is well motivated (unwrap in / wrap out relative to that bound).
  - For an **unbounded** type variable, a plausible policy is to treat values as **opaque** at the wrapper/impl bridge: do not unwrap/wrap even if a concrete substitution could have been a wrapped type, because the implementation contract is not allowed to depend on wrapped-class structure—only on the opaque type parameter.
  - Still worth spelling out edge cases (e.g. users instantiating `G[Wrapper]` where `T` is unbounded), deciding what we guarantee, and **documenting** the chosen behavior either way.

- [ ] Transfer docstrings to generated wrappers
- [ ] Backport some of the traceback stripping (if needed?)
- [ ] **Unify async-generator wrapper surface semantics**
  - Raw async-generator wrappers currently require calling `.aio()` on the wrapper method/function before they become async-iterable
  - This is inconsistent with wrappers for callables returning `AsyncGenerator[...]`, where the wrapper result is already directly async-iterable
  - Migrate toward a single, more consistent async-generator surface model
- [ ] **Improve error messages in code generation**
  - Better diagnostics when type annotations are missing
  - Clear error messages for unsupported type constructs
  - Helpful suggestions for common mistakes
- [ ] **Investigate translation of TypeVar bounds that reference wrapped classes**
  - Confirmed failing typed paths also include callback/callable forms like `Callable[P, T] -> Callable[P, list[T]]` when `T` is bound to a wrapped class
- [ ] **Add callback/callable translation for wrapped classes**
  - Plain callback forms like `Callable[[Node], Node]` and `Callable[[Node], int]` are not translated to public wrapper types today
  - This is a separate limitation from TypeVar-bound translation, though the two interact in callback-heavy generic APIs
  - Runtime and pyright coverage currently live in xfailed integration tests; use those as the target behavior
- [ ] Add inclusion/exclusion overrides for both properties and methods (default excludes _-prefixed)
- [ ] Add option for renaming the output entity itself, not just the module (function name or class name)
- [ ] Add Module.auto(__name__) for auto-inferring output modules as sibling of current (_-prefix or _impl suffix)

- [ ] **Clean up generated code**
  - Share common code between similar wrappers
  - Consider template-based generation

- [ ] **IDE support**
  - Verify PyCharm/VSCode jump-to-definition
  - Check compatibility with MyPy and ty

### Low Priority

- [ ] **Better CLI ergonomics**
  - Add `--watch` mode for development
  - Support glob patterns for module discovery, or full package discovery

- [ ] **Performance profiling**
  - Benchmark thread overhead
  - Optimize hot paths in Synchronizer
  - Consider alternative execution strategies for high-performance use cases

## IDEAS

### Separate "pure" async wrapper
It might be nice to be able to generate a "pure" async interface too that doesn't have the sync methods, since this makes it harder to make the mistake of calling blocking code from within async code when objects have both types.
Then you could have a separate interface `my_library.aio` that mirrors your sync `my_library` library export, but with purely async types. This wrapper could either offload to the same Synchronizer, or entirely (optionally?) circumvent the Synchronizer altogether - reducing the thread overhead.


### "Vendor" library in generated code
If we make the code generator include the library code itself (the synchronizer etc.), the generated library wouldn't even depend on the synchronicity package anymore and be entirely self-contained.

This isn't trivial with the current structure where we use things like synchronicity.Module in library code
to mark what entities to generate code for (this import would fail), and would require some restructuring - for example pre-generation of the code that contains Module, or a separate set of manifest files that determine what
to emit in codegen.

### Support a different kind of generation manifest**
1. One idea is to just put Modules and their specs in a separate file from implementation (should already be possible but needs to be confirmed).
2. One idea is to piggyback on `__all__`

Moving away from decorators as a manifest has one big disadvantage - the decorators ensure statically that *when an implementation type is instantiated, even if that is in a private scope* we know that the type's potential wrappers will have been registered by nature of the type being imported (since the decorator executes at the same time as the type creation). This is critical to get
type "upgrades" to work, i.e. wrapping a returned object in a subtype of the declared return value.
