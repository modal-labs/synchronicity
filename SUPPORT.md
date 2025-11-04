* Functions
    * Wrapped type in annotated arguments are unwrapped (even if nested structures)
    * Wrapped types in annotated return values are wrapped before being returned
    * Async functions (either in annotation or async def) wrapped as FunctionWithAio, with Synchronizer execution
    * sync functions are wrapped to get unwrapping code, but are executed in calling context
* Generators
* Classes w/ methods
* Class inheritance
    * typing.Generic base classes are mirrored in the wrapper
    * wrapped base classes are reflected in the wrapper
    * unwrapped base classes are *not* reflected in the wrapper
