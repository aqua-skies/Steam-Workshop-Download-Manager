"""多 provider 下载抽象（1.4.0）。

通道注册表 + 链式回退。设计文档：research/provider_adaptation.md
调研结论：research/provider_research.md
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
