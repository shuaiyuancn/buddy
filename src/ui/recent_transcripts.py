import json
import threading
from datetime import datetime
from pathlib import Path
from src.config import RECENT_TRANSCRIPTS_FILE

class RecentTranscriptsManager:
    """
    Thread-safe manager for maintaining the most recent dictation transcripts.
    Persists history to JSON on disk and keeps an in-memory FIFO capped list.
    """
    def __init__(self, file_path: Path = RECENT_TRANSCRIPTS_FILE, max_items: int = 5):
        self.file_path = Path(file_path)
        self.max_items = max_items
        self._lock = threading.Lock()
        self._items = []
        self._load()

    def _load(self):
        with self._lock:
            if not self.file_path.exists():
                self._items = []
                return
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._items = data[:self.max_items]
                    else:
                        self._items = []
            except Exception:
                self._items = []

    def _save(self):
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._items, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Warning] Failed to save recent transcripts to {self.file_path}: {e}")

    def add_transcript(self, text: str) -> dict | None:
        """
        Adds a new transcript to the head of the list, keeping at most max_items.
        """
        cleaned = text.strip() if text else ""
        if not cleaned:
            return None

        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "text": cleaned
        }

        with self._lock:
            self._items.insert(0, entry)
            self._items = self._items[:self.max_items]
            self._save()

        return entry

    def get_recent(self) -> list[dict]:
        """
        Returns a copy of the recent transcripts list.
        """
        with self._lock:
            return list(self._items)

    def clear(self):
        """
        Clears all stored transcripts in memory and on disk.
        """
        with self._lock:
            self._items = []
            self._save()
