"""Adapters register themselves by name; nothing else knows which Sources exist."""

from app.adapters.base import SourceAdapter

_REGISTRY: dict[str, type[SourceAdapter]] = {}


def register_adapter(cls: type[SourceAdapter]) -> type[SourceAdapter]:
    if cls.name in _REGISTRY and _REGISTRY[cls.name] is not cls:
        raise ValueError(f"Source adapter {cls.name!r} is already registered")
    _REGISTRY[cls.name] = cls
    return cls


def get_adapter_class(name: str) -> type[SourceAdapter]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"No source adapter named {name!r}") from exc


def registered_adapters() -> list[type[SourceAdapter]]:
    return sorted(_REGISTRY.values(), key=lambda cls: cls.priority)


def standbys_of(name: str) -> list[type[SourceAdapter]]:
    return [cls for cls in registered_adapters() if cls.standby_for == name]


def family_of(cls: type[SourceAdapter]) -> set[str]:
    """A Source plus its main and standbys: they share query watermarks."""
    main = cls.standby_for or cls.name
    return {main, *(c.name for c in standbys_of(main))}


def pool_of(cls: type[SourceAdapter]) -> set[str]:
    """Sources whose spend counts against the same allowance as this one."""
    if cls.budget_pool is None:
        return {cls.name}
    return {c.name for c in registered_adapters() if c.budget_pool == cls.budget_pool}


def run_order() -> list[type[SourceAdapter]]:
    """Main Sources by priority, then standbys: a standby decides from its main's
    state after that run, not yesterday's."""
    return sorted(
        registered_adapters(), key=lambda cls: (cls.standby_for is not None, cls.priority)
    )
