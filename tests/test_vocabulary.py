import os
import time
from unittest.mock import MagicMock

import numpy as np

from src.ai import vocabulary
from src.ai.vocabulary import parse_vocabulary, load_vocabulary_instruction, ensure_vocabulary_file, TEMPLATE


def test_parse_terms_corrections_comments_and_duplicates():
    terms, corrections = parse_vocabulary(
        "# my vocabulary\n"
        "Siobhan O'Connell\n"
        "\n"
        "  Kubernetes  \n"
        "Shivon -> Siobhan\n"
        "kubernetes\n"
        "broken ->\n"
    )
    assert terms == ["Siobhan O'Connell", "Kubernetes", "Siobhan"]
    assert corrections == [("Shivon", "Siobhan")]


def test_template_has_no_entries():
    assert parse_vocabulary(TEMPLATE) == ([], [])


def test_no_instruction_without_vocabulary_file(isolate_dictation_vocabulary):
    assert not isolate_dictation_vocabulary.exists()
    assert load_vocabulary_instruction() == ""


def test_instruction_lists_terms_and_mishearings_with_guard(isolate_dictation_vocabulary):
    isolate_dictation_vocabulary.write_text("Thibault\nShivon -> Siobhan\n", encoding="utf-8")
    instruction = load_vocabulary_instruction()
    lines = instruction.splitlines()
    assert "Most entries will NOT occur in this recording" in lines[0]
    assert "Never put a glossary name in place of a different name the speaker said" in lines[0]
    assert lines[1:3] == ["Thibault", "Siobhan"]
    assert lines[-1] == "Shivon -> Siobhan"


def test_edits_apply_without_restart(isolate_dictation_vocabulary):
    isolate_dictation_vocabulary.write_text("Thibault\n", encoding="utf-8")
    assert "Thibault" in load_vocabulary_instruction()
    isolate_dictation_vocabulary.write_text("Ngozi\n", encoding="utf-8")
    later = time.time() + 5
    os.utime(isolate_dictation_vocabulary, (later, later))
    instruction = load_vocabulary_instruction()
    assert "Ngozi" in instruction and "Thibault" not in instruction


def test_term_count_is_capped():
    terms, _ = parse_vocabulary("\n".join(f"Term{i}" for i in range(vocabulary.MAX_TERMS + 50)))
    assert len(terms) == vocabulary.MAX_TERMS


def test_ensure_creates_template_once(isolate_dictation_vocabulary):
    path = ensure_vocabulary_file()
    assert path == isolate_dictation_vocabulary
    assert path.read_text(encoding="utf-8") == TEMPLATE
    path.write_text("Mine\n", encoding="utf-8")
    ensure_vocabulary_file()
    assert path.read_text(encoding="utf-8") == "Mine\n"


def _dictate_once(config_dict=None):
    from src.ai.transcriber import TranscriberService
    from src.audio.mixer import AudioMixer

    service = TranscriberService(api_key="fake-key", config_dict=config_dict or {})
    service.client = MagicMock()
    service.client.models.generate_content.return_value = MagicMock(text="Ask Thibault.")
    service.process_dictation(AudioMixer.convert_to_wav_bytes(np.full(16000, 0.2, dtype=np.float32), sample_rate=16000))
    return service.client.models.generate_content.call_args.kwargs


def test_dictation_sends_vocabulary_as_system_instruction_not_in_prompt(isolate_dictation_vocabulary):
    from src.ai.transcriber import DICTATION_PROMPT

    isolate_dictation_vocabulary.write_text("Thibault\n", encoding="utf-8")
    kwargs = _dictate_once()
    assert kwargs["contents"][1] == DICTATION_PROMPT
    assert "Thibault" in kwargs["config"].system_instruction


def test_dictation_without_vocabulary_sends_no_config(isolate_dictation_vocabulary):
    assert _dictate_once()["config"] is None


def test_vocabulary_and_thinking_level_combine(isolate_dictation_vocabulary):
    isolate_dictation_vocabulary.write_text("Thibault\n", encoding="utf-8")
    config = _dictate_once({"DICTATION_MODEL": "gemini-3.5-flash", "DICTATION_THINKING_LEVEL": "minimal"})["config"]
    assert "Thibault" in config.system_instruction
    assert config.thinking_config.thinking_level.value.lower() == "minimal"
