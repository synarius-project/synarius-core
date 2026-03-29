"""In-memory SQLite (SQLAlchemy) index: variable *names* → instance counts in the model tree.

The object tree remains authoritative; this registry is derived and updated incrementally
(attach / delete / rename). Not persisted on disk.
"""

from __future__ import annotations

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class _Base(DeclarativeBase):
    pass


class _VariableNameRow(_Base):
    __tablename__ = "variable_name_registry"

    name: Mapped[str] = mapped_column(primary_key=True)
    instance_count: Mapped[int] = mapped_column(nullable=False)


class VariableNameRegistry:
    """Counts :class:`~synarius_core.model.Variable` instances per ``name`` (plain name, whole model)."""

    def __init__(self) -> None:
        self._engine = create_engine("sqlite:///:memory:", future=True)
        _Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False, class_=Session)

    def clear(self) -> None:
        with self._session_factory() as session:
            session.execute(delete(_VariableNameRow))
            session.commit()

    def increment(self, name: str) -> None:
        key = name.strip()
        if not key:
            return
        with self._session_factory() as session:
            row = session.get(_VariableNameRow, key)
            if row is None:
                session.add(_VariableNameRow(name=key, instance_count=1))
            else:
                row.instance_count += 1
            session.commit()

    def decrement(self, name: str) -> None:
        key = name.strip()
        if not key:
            return
        with self._session_factory() as session:
            row = session.get(_VariableNameRow, key)
            if row is None:
                return
            row.instance_count -= 1
            if row.instance_count <= 0:
                session.delete(row)
            session.commit()

    def on_renamed(self, old_name: str, new_name: str) -> None:
        old_k = old_name.strip()
        new_k = new_name.strip()
        if old_k == new_k:
            return
        self.decrement(old_k)
        self.increment(new_k)

    def rows_ordered_by_name(self) -> list[tuple[str, int]]:
        with self._session_factory() as session:
            stmt = select(_VariableNameRow).order_by(_VariableNameRow.name)
            return [(r.name, r.instance_count) for r in session.scalars(stmt)]

    def count_for_name(self, name: str) -> int:
        key = name.strip()
        if not key:
            return 0
        with self._session_factory() as session:
            row = session.get(_VariableNameRow, key)
            return 0 if row is None else row.instance_count


__all__ = ["VariableNameRegistry"]
