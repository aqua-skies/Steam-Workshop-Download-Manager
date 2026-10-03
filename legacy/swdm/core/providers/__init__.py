"""Multi-provider download abstraction (多 provider 下载抽象, introduced in 1.4.0).

Registry-based channel chain with fallback. Design doc: research/provider_adaptation.md;
research conclusions: research/provider_research.md.
"""
from .base import (
    Availability,
    DownloadProvider,
    ProviderKind,
    ProviderMeta,
)
from .registry import ProviderRegistry, get_registry

__all__ = [
    "Availability",
    "DownloadProvider",
    "ProviderKind",
    "ProviderMeta",
    "ProviderRegistry",
    "get_registry",
]
