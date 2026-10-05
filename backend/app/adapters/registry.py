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
