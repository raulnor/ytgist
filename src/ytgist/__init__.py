"""ytt — YouTube transcripts, summaries, and an index over both."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ytgist")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0+unknown"