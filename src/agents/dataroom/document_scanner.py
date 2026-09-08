"""
Document Scanner for Dataroom Analysis

Discovers and inventories all documents in a dataroom directory.
"""

from pathlib import Path
from typing import List, Dict, Optional
import re

from .dataroom_state import DocumentInventoryItem


# =============================================================================
# Supported File Types
# =============================================================================

SUPPORTED_EXTENSIONS = {
    # Documents
    ".pdf": "document",
    ".docx": "document",
    ".doc": "document",

    # Spreadsheets
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".csv": "data",

    # Presentations
    ".pptx": "presentation",
    ".ppt": "presentation",

    # Images (for diagrams, screenshots)
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".svg": "image",

    # Text
    ".md": "text",
    ".txt": "text",

    # Mail. A closing-confirmation email is often the only artifact that dates
    # a financing, so it belongs in the inventory rather than beside it.
    ".eml": "email",
}

# Directories whose contents are never dataroom documents. Checked against the
# whole path, not just the filename, because the point is to skip a subtree.
#
# `_zip-originals/` is the parking lot: raw archive downloads whose contents are
# already expanded as siblings, media kept out of git and reaching the pipeline
# as transcripts, and originals of assets that have been normalized. Every file
# in there is either a duplicate of something already in the dataroom or
# deliberately unreadable, so scanning it produces false "could not be read"
# warnings and, worse, offers the extractor two copies of the same document.
IGNORE_DIRS = {
    "_zip-originals",
    "__MACOSX",
    ".git",
}

# Files to ignore
IGNORE_PATTERNS = [
    ".DS_Store",
    "Thumbs.db",
    "__MACOSX",
    ".git",
    "~$",  # Office temp files
    ".~",  # LibreOffice temp files
]

# Extensions that are real content the pipeline cannot yet read. They are
# reported rather than dropped: an operator who exports a .pages file to PDF
# recovers the document, but only if something tells them it was skipped.
UNREADABLE_EXTENSIONS = {
    ".pages": "Apple Pages bundle — export to PDF or DOCX",
    ".key": "Apple Keynote bundle — export to PDF or PPTX",
    ".numbers": "Apple Numbers bundle — export to XLSX or CSV",
    ".msg": "Outlook message — export to .eml",
    ".zip": "archive — expand it in place so its contents can be scanned",
    ".rar": "archive — expand it in place so its contents can be scanned",
    ".7z": "archive — expand it in place so its contents can be scanned",
}


# =============================================================================
# Scanner Functions
# =============================================================================

def scan_dataroom(dataroom_path: str, return_skipped: bool = False):
    """
    Scan dataroom directory and create inventory of all documents.

    Args:
        dataroom_path: Path to dataroom directory
        return_skipped: Also return the files that were passed over, with the
            reason for each. Off by default so existing callers are unaffected.

    Returns:
        List of DocumentInventoryItem objects (unclassified), or a
        ``(inventory, skipped)`` tuple when ``return_skipped`` is set.
    """
    dataroom = Path(dataroom_path)

    if not dataroom.exists():
        raise FileNotFoundError(f"Dataroom path does not exist: {dataroom_path}")

    if not dataroom.is_dir():
        raise ValueError(f"Dataroom path is not a directory: {dataroom_path}")

    inventory: List[DocumentInventoryItem] = []
    skipped: List[Dict[str, str]] = []

    # Walk directory tree
    for file_path in dataroom.rglob("*"):
        # Skip directories
        if file_path.is_dir():
            continue

        # Skip ignored files
        if _should_ignore(file_path):
            continue

        # Get file info
        extension = file_path.suffix.lower()

        # Record unsupported formats instead of dropping them silently. A
        # dataroom whose only cap table is a .numbers file must not report
        # "no cap table found".
        if extension not in SUPPORTED_EXTENSIONS:
            skipped.append({
                "file_path": str(file_path),
                "filename": file_path.name,
                "extension": extension,
                "reason": UNREADABLE_EXTENSIONS.get(
                    extension, f"unsupported file type '{extension}'"
                ),
            })
            continue

        # Get parent directory name (for classification hints)
        parent_dir = file_path.parent.name

        # Create inventory item
        item: DocumentInventoryItem = {
            "file_path": str(file_path),
            "filename": file_path.name,
            "extension": extension,
            "file_size_bytes": file_path.stat().st_size,
            "page_count": _get_page_count(file_path) if extension == ".pdf" else None,
            "parent_directory": parent_dir,

            # Classification (to be filled by classifier)
            "document_type": "unknown",
            "classification_confidence": 0.0,
            "classification_reasoning": "",
            "classification_source": "unknown",

            # Processing status
            "processed": False,
            "extraction_status": "pending",
            "extraction_error": None,
        }

        inventory.append(item)

    # Sort by path for consistent ordering
    inventory.sort(key=lambda x: x["file_path"])

    if return_skipped:
        return inventory, sorted(skipped, key=lambda x: x["file_path"])
    return inventory


def get_directory_structure(dataroom_path: str) -> Dict[str, List[str]]:
    """
    Get directory structure with files for classification hints.

    Args:
        dataroom_path: Path to dataroom directory

    Returns:
        Dict mapping relative directory paths to list of filenames
    """
    dataroom = Path(dataroom_path)
    structure: Dict[str, List[str]] = {}

    for dir_path in dataroom.rglob("*"):
        if dir_path.is_dir():
            rel_path = str(dir_path.relative_to(dataroom))
            files = [
                f.name for f in dir_path.iterdir()
                if f.is_file() and not _should_ignore(f)
            ]
            if files:  # Only include directories with files
                structure[rel_path] = files

    return structure


def get_inventory_summary(inventory: List[DocumentInventoryItem]) -> Dict[str, any]:
    """
    Generate summary statistics from inventory.

    Args:
        inventory: List of DocumentInventoryItem objects

    Returns:
        Summary dict with counts and stats
    """
    summary = {
        "total_documents": len(inventory),
        "by_extension": {},
        "by_type": {},
        "by_directory": {},
        "total_size_bytes": 0,
        "total_pages": 0,
    }

    for item in inventory:
        # Count by extension
        ext = item["extension"]
        summary["by_extension"][ext] = summary["by_extension"].get(ext, 0) + 1

        # Count by document type
        doc_type = item["document_type"]
        summary["by_type"][doc_type] = summary["by_type"].get(doc_type, 0) + 1

        # Count by directory
        parent = item["parent_directory"]
        summary["by_directory"][parent] = summary["by_directory"].get(parent, 0) + 1

        # Totals
        summary["total_size_bytes"] += item["file_size_bytes"]
        if item["page_count"]:
            summary["total_pages"] += item["page_count"]

    return summary


# =============================================================================
# Helper Functions
# =============================================================================

def _should_ignore(file_path: Path) -> bool:
    """Check if file should be ignored, by directory subtree and by filename."""
    # Subtree check first: a parked original is a perfectly ordinary filename
    # sitting somewhere the scanner has no business looking.
    if IGNORE_DIRS.intersection(file_path.parts):
        return True

    name = file_path.name

    for pattern in IGNORE_PATTERNS:
        if pattern in name or name.startswith(pattern):
            return True

    # Skip hidden files
    if name.startswith("."):
        return True

    return False


def _get_page_count(pdf_path: Path) -> Optional[int]:
    """
    Page count for a PDF, via the shared text layer.

    Previously read pypdf directly inside a bare except, so an uninstalled
    pypdf reported every PDF as having an unknown page count — which the
    inventory then rendered as zero total pages.
    """
    from .document_text import extract_text

    return extract_text(pdf_path, max_chars=1, ocr=False).page_count


def parse_directory_category(directory_name: str) -> Optional[str]:
    """
    Parse directory name to extract category hint.

    Handles patterns like:
    - "1 1_0 Executive Summary"
    - "4 4_0 GTM_Competitive Overview"
    - "Financial Overview"
    - "5. Financials"

    Returns:
        Normalized category string or None
    """
    # Remove leading numbers and separators
    # Pattern: optional "N" or "N.N" or "N N_N" prefix
    cleaned = re.sub(r'^[\d\s._]+', '', directory_name)

    # Normalize separators
    cleaned = cleaned.replace('_', ' ').replace('-', ' ')

    # Lowercase for matching
    cleaned = cleaned.lower().strip()

    return cleaned if cleaned else None
