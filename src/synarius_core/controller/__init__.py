"""Controller and command protocol implementation for synarius-core."""

from .minimal_controller import CommandError, MinimalController

__all__ = ["MinimalController", "CommandError"]

