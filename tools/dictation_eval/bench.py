"""
Benchmarks Gemini models for Buddy's dictation on the corpus from make_corpus.py, using the exact
prompt Buddy ships (src.ai.transcriber.DICTATION_PROMPT).

  python tools/dictation_eval/bench.py --models gemini-3.1-flash-lite,gemini-3.5-flash:minimal,gemini-3.8-flash --runs 2

A model may carry a thinking level after a colon (e.g. gemini-3.5-flash:minimal).
--vocabulary sends a vocabulary file exactly as Buddy sends ~/.buddy/dictation_vocabulary.txt.

Dictation rewrites speech into polished text, so outputs are not compared word for word. A judge
model scores each output from 1 to 5 against what was actually said:
  fidelity    every fact, name, number and request kept; nothing invented; self-corrections applied;
              written in the speaker's language(s)
  clarity     concise, clear and professional, with no fillers or rambling
  formatting  bullets on separate lines when the speaker listed several items, plain prose otherwise
Latency is the wall time of the dictation call, as the user waits for it after releasing the hotkey.
"""
import sys
import json
import time
import argparse
import statistics
import concurrent.futures as cf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import check_api_key_or_toast_and_exit  # noqa: E402
from src.ai.transcriber import DICTATION_PROMPT, dictation_generate_config  # noqa: E402
from src.ai.vocabulary import load_vocabulary_instruction  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

JUDGE_MODEL = "gemini-3.1-pro-preview"
JUDGE_PROMPT = """You are grading a voice dictation assistant. It must turn dictated speech into concise, clear,
professional written text in the speaker's own language(s): keep every fact, name, number, date, request and
commitment; add nothing; drop fillers and false starts; apply the speaker's self-corrections; never translate;
use "• " bullets on separate lines only when the speaker lists several items, and plain sentences otherwise.

What the speaker said (the script read aloud):
{spoken}

An ideal result would look like this (wording may differ):
{expect}

Expected format: {format}

The assistant's output:
{output}

Score each from 1 (bad) to 5 (perfect):
- fidelity: facts, names, numbers and requests all present and correct; nothing invented or translated; corrections applied
- clarity: concise, clear, professional; no fillers or rambling
- formatting: bullets and line breaks used appropriately for this content"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "fidelity": {"type": "integer"},
        "clarity": {"type": "integer"},
        "formatting": {"type": "integer"},
        "issues": {"type": "string"},
    },
    "required": ["fidelity", "clarity", "formatting", "issues"],
}


def dictate(client, model: str, thinking: str, wav: bytes, vocabulary: str) -> tuple:
    config = dictation_generate_config(thinking, vocabulary)
    started = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model, contents=[types.Part.from_bytes(data=wav, mime_type="audio/wav"), DICTATION_PROMPT], config=config)
        return (response.text or "").strip(), time.perf_counter() - started, None
    except Exception as e:
        return "", time.perf_counter() - started, str(e)[:160]


def judge(client, ref: dict, output: str) -> dict:
    if not output:
        return {"fidelity": 1, "clarity": 1, "formatting": 1, "issues": "empty output"}
    prompt = JUDGE_PROMPT.format(spoken=ref["spoken"], expect=ref["expect"], format=ref["format"], output=output)
    for _ in range(3):
        try:
            response = client.models.generate_content(
                model=JUDGE_MODEL, contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=JUDGE_SCHEMA))
            return json.loads(response.text)
        except Exception as e:
            last = str(e)[:160]
    return {"fidelity": None, "clarity": None, "formatting": None, "issues": f"judge failed: {last}"}


def run_once(client, model, thinking, sid, wav, ref, vocabulary) -> dict:
    text, sec, error = dictate(client, model, thinking, wav, vocabulary)
    scores = judge(client, ref, text) if not error else {}
    return {"model": model, "thinking": thinking, "sid": sid, "sec": sec, "text": text, "error": error, **scores}


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else float("nan")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default="gemini-3.1-flash-lite,gemini-3.5-flash:minimal,gemini-3.8-flash")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--corpus", default=str(Path(__file__).parent / "corpus"))
    parser.add_argument("--vocabulary", default=None, help="Optional vocabulary file, sent the way Buddy sends the user's")
    parser.add_argument("--results", default=None, help="Optional path to write every individual result as JSON")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    refs = json.loads((corpus / "refs.json").read_text(encoding="utf-8"))
    wavs = {sid: (corpus / f"{sid}.wav").read_bytes() for sid in refs}
    configs = [(m.split(":")[0], m.split(":")[1] if ":" in m else None) for m in args.models.split(",")]
    client = genai.Client(api_key=check_api_key_or_toast_and_exit())
    vocabulary = load_vocabulary_instruction(Path(args.vocabulary)) if args.vocabulary else ""

    jobs = [(m, t, sid) for m, t in configs for sid in refs for _ in range(args.runs)]
    with cf.ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(lambda j: run_once(client, j[0], j[1], j[2], wavs[j[2]], refs[j[2]], vocabulary), jobs))
    if args.results:
        Path(args.results).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{'model':26}{'thinking':10}{'p50 s':>7}{'p90 s':>7}{'fidelity':>10}{'clarity':>9}{'format':>8}{'overall':>9}{'failed':>8}")
    for model, thinking in configs:
        rows = [r for r in results if r["model"] == model and r["thinking"] == thinking]
        ok = [r for r in rows if not r["error"]]
        if not ok:
            print(f"{model:26}{str(thinking or '-'):10}  all calls failed: {rows[0]['error']}")
            continue
        secs = sorted(r["sec"] for r in ok)
        fid, cla, fmt = (mean(r.get(k) for r in ok) for k in ("fidelity", "clarity", "formatting"))
        print(f"{model:26}{str(thinking or '-'):10}{statistics.median(secs):7.2f}{secs[int(0.9 * (len(secs) - 1))]:7.2f}"
              f"{fid:10.2f}{cla:9.2f}{fmt:8.2f}{(fid + cla + fmt) / 3:9.2f}{len(rows) - len(ok):8}")


if __name__ == "__main__":
    main()
