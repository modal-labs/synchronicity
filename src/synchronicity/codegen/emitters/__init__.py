"""Output emitters: map parsed IR to generated Python source."""

from .protocol import CodegenEmitter
from .sync_async_wrappers import SyncAsyncWrapperEmitter

__all__ = ["CodegenEmitter", "SyncAsyncWrapperEmitter"]
