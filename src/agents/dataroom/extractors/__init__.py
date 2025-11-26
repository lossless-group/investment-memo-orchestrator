"""
Dataroom Extractors

Specialized extraction modules for different document types.
"""

from .competitive_extractor import extract_competitive_data

__all__ = [
    "extract_competitive_data",
]
