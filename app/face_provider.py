from collections.abc import Sequence
from functools import lru_cache
from importlib import import_module
from typing import Protocol

from app.config import get_settings


class FaceProvider(Protocol):
    """Provider contract: decode, detect, align and embed one uploaded image."""

    def embed(self, image_bytes: bytes) -> Sequence[float]: ...


class FaceNotFoundError(ValueError):
    pass


class DisabledFaceProvider:
    def embed(self, image_bytes: bytes) -> Sequence[float]:
        raise RuntimeError("No licensed face provider is configured")


@lru_cache
def get_face_provider() -> FaceProvider:
    settings = get_settings()
    if settings.face_provider == "disabled":
        return DisabledFaceProvider()
    try:
        module_name, factory_name = settings.face_provider.split(":", maxsplit=1)
        factory = getattr(import_module(module_name), factory_name)
        return factory(settings)
    except (ValueError, ImportError, AttributeError, TypeError) as exc:
        raise RuntimeError("Configured face provider could not be loaded") from exc
