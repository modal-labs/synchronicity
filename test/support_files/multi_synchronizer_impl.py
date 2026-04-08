"""Two wrapper targets with distinct synchronizer names (integration test only)."""

import asyncio
import threading

from synchronicity import Module

mod_a = Module("multi_sync.a", "synchronizer_alpha")
mod_b = Module("multi_sync.b", "synchronizer_beta")


@mod_a.wrap_function
async def thread_and_loop_a() -> tuple[int, int]:
    """Return (thread id, event loop id) from this synchronizer's worker thread."""
    return (threading.current_thread().ident or 0, id(asyncio.get_running_loop()))


@mod_b.wrap_function
async def thread_and_loop_b() -> tuple[int, int]:
    return (threading.current_thread().ident or 0, id(asyncio.get_running_loop()))
