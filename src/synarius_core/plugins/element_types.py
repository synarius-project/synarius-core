"""ABCs and context types for Synarius plugins (handler dispatch, compile passes, simulation runtime)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import UUID

# Controller-only: optional ``id=`` for ``new`` (stored in :class:`NewContext` ``options``, not FMU-specific).
NEW_CONTEXT_OPTION_EXPLICIT_ID = "_synarius_explicit_id"


@dataclass
class CompileContext:
    """Shared context for plugin compile passes."""

    model: Any
    artifacts: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)


class CompilerPass(ABC):
    """One compile pipeline stage."""

    name: str
    stage: str

    @abstractmethod
    def run(self, ctx: CompileContext) -> None:
        ...


@dataclass
class NewContext:
    """Context for ``ElementTypeHandler.new`` (type-agnostic; controller may set ``options`` keys such as :data:`NEW_CONTEXT_OPTION_EXPLICIT_ID`)."""

    controller: Any
    model: Any
    options: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class InspectContext:
    """Context for ``ElementTypeHandler.inspect``."""

    controller: Any
    model: Any
    options: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class InspectResult:
    """Structured result for inspection (serialized to JSON by the controller)."""

    type_key: str
    ref: str
    attributes: dict[str, Any] = field(default_factory=dict)
    pins: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncContext:
    """Context for ``ElementTypeHandler.sync``."""

    controller: Any
    model: Any
    artifacts: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class SimContext:
    """Draft runtime context; the engine adapts :class:`~synarius_core.dataflow_sim.context.SimulationContext` to this shape for :class:`SimulationRuntimePlugin`."""

    artifacts: dict[str, Any]
    scalar_workspace: dict[Any, float]
    options: dict[str, Any]
    diagnostics: list[str]
    time_s: float = 0.0


class ElementTypeHandler(ABC):
    """Handles ``new`` / ``inspect`` / ``sync`` for one ``type_key`` (and optional aliases)."""

    type_key: str
    handler_aliases: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def new(
        self,
        ctx: NewContext,
        ref: str,
        args: list[Any],
        kwargs: dict[str, Any],
    ) -> Any:
        """Create a model object; caller attaches it to the model."""

    def inspect(self, ctx: InspectContext, ref: str) -> InspectResult:
        raise NotImplementedError(f"{type(self).__name__} does not implement inspect")

    def sync(self, ctx: SyncContext, ref: str) -> None:
        """Default: no-op."""

    def registered_keys(self) -> tuple[str, ...]:
        keys = [self.type_key, *self.handler_aliases]
        return tuple(k for k in keys if k)


class SimulationRuntimePlugin(ABC):
    """Optional runtime for capabilities such as ``runtime:fmu``."""

    runtime_capability: str

    @abstractmethod
    def runtime_init(self, ctx: SimContext) -> None: ...

    @abstractmethod
    def runtime_step(self, ctx: SimContext, node_id: UUID) -> None: ...

    @abstractmethod
    def runtime_shutdown(self, ctx: SimContext) -> None: ...

    def runtime_reset(self, ctx: SimContext) -> None:
        self.runtime_shutdown(ctx)
        self.runtime_init(ctx)


class SynariusPlugin(ABC):
    """Abstract contribution provider (loaded parameterless by :class:`~synarius_core.plugins.registry.PluginRegistry`)."""

    name: str = ""

    def compile_passes(self) -> list[CompilerPass]:
        return []

    def element_type_handlers(self) -> list[ElementTypeHandler]:
        return []

    def simulation_runtime(self) -> SimulationRuntimePlugin | None:
        return None
