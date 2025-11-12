import io
import re
from typing import List, Optional
from urllib.parse import urlparse


def clean_text(text: str) -> str:
    """Lightweight cleaner for scraped or pasted text.

    - Strips HTML tags
    - Removes URLs
    - Normalizes whitespace and basic punctuation noise
    """
    if not isinstance(text, str):
        return ""
    # Remove HTML tags
    text = re.sub(r"<[^>]*?>", "", text)
    # Remove URLs
    text = re.sub(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", "", text)
    # Replace multiple spaces with a single space
    text = re.sub(r"\s{2,}", " ", text)
    # Trim leading and trailing whitespace
    text = text.strip()
    # Remove extra whitespace
    text = " ".join(text.split())
    return text


def validate_url(url: str) -> bool:
    """Basic URL validator using urlparse; ensures scheme and netloc exist."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def parse_skills(skills_text: str) -> List[str]:
    """Parse a comma/line-separated skills string into a clean list."""
    if not skills_text:
        return []
    parts = re.split(r"[,\n]", skills_text)
    skills = [p.strip() for p in parts if p.strip()]
    # Deduplicate while preserving order
    seen = set()
    result = []
    for s in skills:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result


def coerce_skills(value) -> List[str]:
    """Coerce an arbitrary value into a list[str] of skills.

    - If value is a string, split using parse_skills (commas/newlines) and return list.
    - If it's already a list/tuple, keep only non-empty strings and strip them.
    - Otherwise, return an empty list.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return parse_skills(value)
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        seen = set()
        for v in value:
            if isinstance(v, str):
                s = v.strip()
                if s and s.lower() not in seen:
                    seen.add(s.lower())
                    out.append(s)
        return out
    return []


def sanitize_links(links: List[str]) -> List[str]:
    """Filter and normalize a list of links."""
    safe = []
    for link in links or []:
        link = (link or "").strip()
        if validate_url(link):
            safe.append(link)
    return safe


def safe_truncate(text: str, max_chars: int = 6000) -> str:
    """Truncate long text safely at a word boundary close to max_chars."""
    if not text or len(text) <= max_chars:
        return text or ""
    cutoff = text.rfind(" ", 0, max_chars)
    return text[: cutoff if cutoff > 0 else max_chars].rstrip() + " …"


def extract_text_from_upload(uploaded_file) -> Optional[str]:
    """Extract text from an uploaded resume file (PDF, DOCX, or TXT).

    Returns text or None if unsupported/failed.
    """
    if uploaded_file is None:
        return None

    filename = uploaded_file.name.lower()
    content = uploaded_file.read()

    try:
        if filename.endswith(".pdf"):
            # Lazy import to avoid hard dependency when unused
            from pypdf import PdfReader

            with io.BytesIO(content) as f:
                reader = PdfReader(f)
                pages = [p.extract_text() or "" for p in reader.pages]
                return "\n".join(pages)

        if filename.endswith(".docx"):
            # Use python-docx to read text from a DOCX file-like object
            from docx import Document

            with io.BytesIO(content) as f:
                doc = Document(f)
                paragraphs = [p.text for p in doc.paragraphs]
                return "\n".join(paragraphs)
    except Exception:
        # Fall through to TXT attempt
        pass

    try:
        # Assume UTF-8 text file
        return content.decode("utf-8", errors="ignore")
    except Exception:
        return None
