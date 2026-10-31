import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolate_dictation_history(tmp_path):
    """Keep dictation results written by tests out of the real ~/.buddy/dictations folder."""
    with patch("src.ai.transcriber.DICTATIONS_DIR", tmp_path / "dictations"):
        yield tmp_path / "dictations"
