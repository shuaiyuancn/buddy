import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolate_dictation_history(tmp_path):
    """Keep dictation results written by tests out of the real ~/.buddy/dictations folder."""
    with patch("src.ai.transcriber.DICTATIONS_DIR", tmp_path / "dictations"):
        yield tmp_path / "dictations"


@pytest.fixture(autouse=True)
def isolate_dictation_vocabulary(tmp_path):
    """Tests never read or create the user's real ~/.buddy/dictation_vocabulary.txt."""
    with patch("src.config.DICTATION_VOCABULARY_FILE", tmp_path / "dictation_vocabulary.txt"):
        yield tmp_path / "dictation_vocabulary.txt"
