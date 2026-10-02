"""Arbiter: an AI governance gateway and EU AI Act compliance toolkit."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ai-arbiter")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
