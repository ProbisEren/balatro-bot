"""Balatro AI paketi: Balatro'yu oynayan botun kodu. `__version__`, pyproject.toml'daki sürümden okunur."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("balatro-ai")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
