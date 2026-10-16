"""
core/io_utils.py
Centralized I/O and encoding utilities for robust text and delimited data (CSV/TSV) handling.
Provides automatic encoding detection (UTF-8, UTF-8-SIG, CP1254, CP1252, Latin-1)
and CSV delimiter sniffing (, ; \t |).
"""

import os
import csv
import pandas as pd
from typing import Tuple, Optional


COMMON_ENCODINGS = ("utf-8-sig", "utf-8", "cp1254", "cp1252", "iso-8859-9", "latin1")


def detect_text_encoding(file_path: str, sample_size: int = 32768) -> str:
    """
    Detects the best text encoding for the given file.
    Checks BOMs first, then attempts decoding sample bytes with common encodings.
    Defaults to 'utf-8'.
    """
    if not os.path.isfile(file_path):
        return "utf-8"

    try:
        with open(file_path, "rb") as f:
            raw = f.read(sample_size)
    except Exception:
        return "utf-8"

    if not raw:
        return "utf-8"

    # 1. BOM checks
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"

    # 2. Sequential decode tests
    for enc in COMMON_ENCODINGS:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue

    return "utf-8"


def sniff_delimiter(sample_text: str, default: str = ",") -> str:
    """
    Sniffs the delimiter (, ; \t |) from a sample text snippet.
    Falls back to frequency heuristic if csv.Sniffer fails.
    """
    if not sample_text:
        return default

    # Try standard Python sniffer first
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",;\t|")
        if dialect and dialect.delimiter:
            return dialect.delimiter
    except Exception:
        pass

    # Heuristic frequency check across non-empty lines
    lines = [ln.strip() for ln in sample_text.splitlines() if ln.strip()]
    if not lines:
        return default

    head_lines = lines[:5]
    delims = (",", ";", "\t", "|")
    scores = {d: 0 for d in delims}

    for d in delims:
        counts = [ln.count(d) for ln in head_lines]
        if counts and all(c > 0 and c == counts[0] for c in counts):
            # Consistent column count across rows gets high priority
            scores[d] += 100 + counts[0]
        else:
            scores[d] += sum(counts)

    best_delim = max(scores, key=scores.get)
    return best_delim if scores[best_delim] > 0 else default


def read_delimited_file(file_path: str, **kwargs) -> Tuple[pd.DataFrame, str, str]:
    """
    Reads a delimited file (CSV, TSV, TXT table) into a pandas DataFrame.
    Automatically detects encoding and delimiter.

    Returns:
        (df, delimiter, encoding)
    """
    encoding = kwargs.pop("encoding", None) or detect_text_encoding(file_path)

    # Read sample for delimiter detection
    sample = ""
    try:
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            sample = f.read(16384)
    except Exception:
        pass

    sep = kwargs.pop("sep", None)
    if sep is None:
        sep = sniff_delimiter(sample)

    try:
        df = pd.read_csv(file_path, sep=sep, encoding=encoding, **kwargs)
    except Exception:
        # Fallback to python engine with looser parsing
        try:
            df = pd.read_csv(file_path, sep=None, engine="python", encoding=encoding, **kwargs)
        except Exception:
            # Last-resort fallback with latin1
            df = pd.read_csv(file_path, sep=sep, encoding="latin1", on_bad_lines="skip", **kwargs)

    return df, sep, encoding


def read_text_file(file_path: str, encoding: Optional[str] = None) -> str:
    """
    Safely reads a text file using detected encoding, preventing UnicodeDecodeError.
    """
    enc = encoding or detect_text_encoding(file_path)
    try:
        with open(file_path, "r", encoding=enc) as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


def write_text_file(file_path: str, content: str, encoding: str = "utf-8") -> None:
    """
    Safely writes a text file with UTF-8 encoding.
    """
    with open(file_path, "w", encoding=encoding) as f:
        f.write(content)

