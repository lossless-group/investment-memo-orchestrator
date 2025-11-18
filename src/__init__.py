"""Investment Memo Orchestrator - Multi-agent system for generating investment memos."""

try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    from importlib_metadata import version, PackageNotFoundError

try:
    __version__ = version("investment-memo-orchestrator")
except PackageNotFoundError:
    # Package not installed, version will be determined by setuptools-scm at build time
    __version__ = "unknown"
