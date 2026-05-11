"""Execution backends for tool subprocesses.

Adapters produce a `LogicalCommand`; a `Backend` decides how to actually run
it. The same adapter code therefore works under native Windows, WSL2, or a
Docker container without modification.
"""

from srna_win_target.backends.base import Backend, BackendResult
from srna_win_target.backends.local import LocalBackend
from srna_win_target.backends.wsl import WSLBackend
from srna_win_target.core.models import BackendKind


def build_backend(kind: BackendKind) -> Backend:
    if kind == BackendKind.LOCAL:
        return LocalBackend()
    if kind == BackendKind.WSL:
        return WSLBackend()
    raise NotImplementedError(f"Backend not implemented yet: {kind}")


__all__ = ["Backend", "BackendResult", "LocalBackend", "WSLBackend", "build_backend"]
