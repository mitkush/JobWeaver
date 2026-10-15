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


def upstream_of(cls: type[SourceAdapter]) -> list[type[SourceAdapter]]:
    """Immediate main through the root Source, in dependency order."""
    result = []
    seen = {cls.name}
    while cls.standby_for:
        cls = get_adapter_class(cls.standby_for)
        if cls.name in seen:
            raise ValueError("Source standby chain contains a cycle")
        seen.add(cls.name)
        result.append(cls)
    return result


def family_of(cls: type[SourceAdapter]) -> set[str]:
    """The complete fallback family shares successful query watermarks."""
    parents = upstream_of(cls)
    root = parents[-1].name if parents else cls.name
    family = {root}
    pending = [root]
    while pending:
        for child in standbys_of(pending.pop()):
            if child.name not in family:
                family.add(child.name)
                pending.append(child.name)
    return family


def pool_of(cls: type[SourceAdapter]) -> set[str]:
    """Sources whose spend counts against the same allowance as this one."""
    if cls.budget_pool is None:
        return {cls.name}
    return {c.name for c in registered_adapters() if c.budget_pool == cls.budget_pool}


def run_order() -> list[type[SourceAdapter]]:
    """Each fallback runs after all upstream Sources have had their turn."""
    return sorted(registered_adapters(), key=lambda cls: (len(upstream_of(cls)), cls.priority))
