"""
Personal dictation vocabulary: names and terms Gemini should spell exactly, plus known mishearings.

Kept in %USERPROFILE%\\.buddy\\dictation_vocabulary.txt (Edit Dictation Vocabulary in the tray menu),
one entry per line:

    Siobhan O'Connell        a name or term, spelled the way it should be written
    Shivon -> Siobhan        something Gemini tends to hear, and what the speaker meant
    # comment                ignored

The file is re-read whenever it changes, so edits apply to the next dictation.
"""
import logging
import threading
from pathlib import Path

import src.config

logger = logging.getLogger("buddy.vocabulary")

TEMPLATE = """# Buddy dictation vocabulary
#
# One name or term per line, spelled exactly the way you want it written, e.g.
#   Siobhan O'Connell
#   Kubernetes
#
# For words Gemini keeps getting wrong, add "what it hears -> what you meant", e.g.
#   Shivon -> Siobhan
#
# Lines starting with # are ignored. Changes apply to your next dictation.
"""

# Keeps the prompt (and the latency it adds) bounded even for a very long file
MAX_TERMS = 400
MAX_CORRECTIONS = 200

_cache_lock = threading.Lock()
_cache = {"path": None, "mtime": None, "value": ([], [])}


def vocabulary_path() -> Path:
    return src.config.DICTATION_VOCABULARY_FILE


def parse_vocabulary(text: str) -> tuple:
    """Returns (terms, corrections): terms in file order without duplicates, corrections as (heard, meant) pairs."""
    terms, corrections, seen = [], [], set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "->" in line:
            heard, meant = (part.strip() for part in line.split("->", 1))
            if heard and meant:
                corrections.append((heard, meant))
                line = meant
            else:
                continue
        if line.lower() not in seen:
            seen.add(line.lower())
            terms.append(line)
    return terms[:MAX_TERMS], corrections[:MAX_CORRECTIONS]


def load_vocabulary(path: Path = None) -> tuple:
    """Reads the vocabulary file, re-parsing only when it has changed. Missing file means no vocabulary."""
    path = Path(path or vocabulary_path())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return [], []
    with _cache_lock:
        if _cache["path"] == path and _cache["mtime"] == mtime:
            return _cache["value"]
    try:
        value = parse_vocabulary(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception(f"Failed to read dictation vocabulary at {path}")
        return [], []
    logger.info(f"Loaded dictation vocabulary: {len(value[0])} terms, {len(value[1])} known mishearings")
    with _cache_lock:
        _cache.update(path=path, mtime=mtime, value=value)
    return value


def vocabulary_instruction(terms: list, corrections: list) -> str:
    """
    System instruction carrying the user's spellings, or "" when there are none.

    It goes in the system instruction, framed as a glossary most of whose entries won't occur,
    rather than in the prompt next to the audio. With a 138-entry list in the prompt,
    gemini-3.1-flash-lite replaced names the speaker said but the list didn't have with listed
    names in 8 of 12 runs ("Thibault" came out as a colleague's name); this framing brought that
    to 0 of 12 while listed names went from 15% to 100% spelled right (docs/dictation-model-evaluation.md).
    """
    if not terms and not corrections:
        return ""
    lines = [
        "Glossary for spelling only. Most entries will NOT occur in this recording. When a word or name in the audio "
        "clearly is one of these, use this spelling; otherwise ignore the glossary and write what you hear. "
        "Never put a glossary name in place of a different name the speaker said:",
        *terms,
    ]
    if corrections:
        lines.append("Known mishearings (apply only when the audio is very close to the left side):")
        lines.extend(f"{heard} -> {meant}" for heard, meant in corrections)
    return "\n".join(lines)


def load_vocabulary_instruction(path: Path = None) -> str:
    """The system instruction for the user's current vocabulary file, or "" if they have none."""
    return vocabulary_instruction(*load_vocabulary(path))


def ensure_vocabulary_file(path: Path = None) -> Path:
    """Creates the vocabulary file with instructions if it does not exist yet, and returns its path."""
    path = Path(path or vocabulary_path())
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEMPLATE, encoding="utf-8")
    return path
