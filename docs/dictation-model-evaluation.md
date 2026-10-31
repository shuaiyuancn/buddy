# Dictation model evaluation

How we chose the Gemini model for Buddy's dictation (Right Alt), how we measured it, and how to run
the evaluation again when new models come out. Last run: 31 October 2026, against Buddy v0.4.0.

## Recommendation

| Use | Model | Setting |
|---|---|---|
| Default (fast and accurate) | `gemini-3.1-flash-lite` | `"DICTATION_MODEL": "gemini-3.1-flash-lite"` (the default) |
| Highest accuracy, about 2x slower | `gemini-3.8-flash` | `"DICTATION_MODEL": "gemini-3.8-flash"` |

`gemini-3.1-flash-lite` returns a rewritten dictation in about 3.5 seconds (median) and keeps the
facts intact more reliably than any other fast model. Its remaining errors are mishearings of rare
names and jargon (for example "Benoit" heard as "Ben Watt"). `gemini-3.8-flash` makes fewer of those
mistakes but takes about 6.8 seconds, which feels slow when you are waiting to paste.

We ruled out `gemini-3.5-flash` with minimal thinking. Its scores were close, but its mistakes are the
wrong kind for a dictation tool: it changed "Let's" to "I'll", dropped the reason from a sentence,
and translated an English word in a Chinese sentence. You can spot and fix a mishearing at a
glance, but a changed meaning can slip through unnoticed.

## What dictation is asked to do

Dictation is not a word-for-word transcript. Buddy sends the recorded audio to Gemini in one call
with a prompt (`DICTATION_PROMPT` in `src/ai/transcriber.py`) that asks for:

- concise, clear, professional sentences, without fillers, repetitions or false starts
- self-corrections applied ("Wednesday, no wait, Thursday" becomes "Thursday")
- every fact, name, number, request and commitment kept, and nothing added
- the speaker's own language: Chinese stays Chinese, and English terms in mixed speech stay English
- `•` bullets on separate lines when the speaker lists several items, and plain sentences otherwise

## Test set

Fourteen clips, made by `tools/dictation_eval/make_corpus.py`. Each clip has a script (what is said),
an ideal result, and the expected format (bullets or plain).

| Clips | Voice | What they test |
|---|---|---|
| `s1` to `s3` | Windows SAPI (en-GB, en-US) | Short English with fillers, a self-correction, names, numbers and percentages |
| `g1_en_fillers` | Gemini TTS | Heavy fillers and "Wednesday, no wait, Thursday" |
| `g2_en_jargon` | Gemini TTS | BigQuery, P+ marketplace, RTI, adserver |
| `g3_zh` | Gemini TTS | Mandarin with a time and a quarter |
| `g4_mixed` | Gemini TTS | Mandarin with English product terms and a percentage |
| `g1` to `g4`, `_noisy` | Same, plus noise | The four clips above with low-frequency room noise at about 8 dB SNR |
| `g5_en_list` | Gemini TTS | 21 s rambling team update with three action items and a request (should become bullets) |
| `g6_zh_list` | Gemini TTS | 21 s Mandarin update with a three-item list (should become bullets) |
| `g7_en_email` | Gemini TTS | 15 s rambling email paragraph (should stay prose, no bullets) |

All clips are 16 kHz mono 16-bit WAV, the same format Buddy records for dictation.

## How each model was scored

For each model, every clip was sent twice with Buddy's exact prompt, six requests at a time.

- **Latency** is the wall time of the call, which is what you wait for after releasing the hotkey.
  We report the median (p50) and the 90th percentile (p90), because one slow dictation in ten is
  what you notice.
- **Quality** is scored by a judge model (`gemini-3.1-pro-preview`). For each output, the judge
  sees the script, the ideal result and the expected format, and scores 1 to 5 on:
  - **fidelity**: facts, names, numbers and requests present and correct; nothing invented or
    translated; corrections applied
  - **clarity**: concise, clear and professional
  - **formatting**: bullets and line breaks used where the content calls for them, and nowhere else

  The judge also writes a one-line note on what went wrong, which is how we told mishearings
  apart from changed meaning.

## Results

### Rewrite mode (what ships)

Two runs per clip, 14 clips, judge scores out of 5:

| Model | Thinking | p50 | p90 | Fidelity | Clarity | Format | Overall |
|---|---|---|---|---|---|---|---|
| `gemini-3.8-flash` | default | 6.84 s | 9.39 s | **4.86** | 5.00 | 4.93 | **4.93** |
| `gemini-3.5-flash` | minimal | 3.50 s | 5.03 s | 4.54 | 4.96 | 5.00 | 4.83 |
| **`gemini-3.1-flash-lite`** | default | 3.46 s | 5.36 s | 4.68 | 4.93 | 4.82 | 4.81 |
| `gemini-3.6-flash` | default | 4.77 s | 7.63 s | 4.32 | 5.00 | 4.89 | 4.74 |
| `gemini-3.5-flash-lite` | default | **2.73 s** | 3.89 s | 4.07 | 4.46 | 5.00 | 4.51 |
| `gemini-flash-lite-latest` | default | 3.32 s | 5.44 s | 4.18 | 4.32 | 5.00 | 4.50 |

Example output from `gemini-3.1-flash-lite` for `g5_en_list` (21 seconds of rambling speech):

```
Hey team, quick update on the launch:

• The dashboard is basically done; Sunil just needs to review it.
• The pipeline is still a bit flaky, so Heiko is looking into the retries.
• We need someone to book the room for the demo on Thursday at 2:00.

Please send me your slides by Wednesday.
```

### Earlier rounds: transcription accuracy

Before dictation switched to rewriting, we ran two rounds that asked for a cleaned-up transcript
and scored it with a token error rate (word-level edit distance against the ideal text, per
character for Chinese, after normalising formatting such as "2.3%" and "2.3 percent"). These rounds
used the first 11 clips. They are kept here because they show which models hear accurately, and
how much the prompt matters.

**Round 1** used the prompt Buddy shipped before v0.4.0 (two runs per clip):

| Model | Thinking | p50 | p90 | Error | English | Chinese and mixed |
|---|---|---|---|---|---|---|
| `gemini-flash-latest` | default | 5.63 s | 8.30 s | 3.9% | 6.2% | 0.0% |
| `gemini-3.7-flash` | default | 5.88 s | 8.28 s | 4.3% | 6.8% | 0.0% |
| `gemini-3.8-flash` | default | 5.46 s | 8.09 s | 4.3% | 6.8% | 0.0% |
| `gemini-3.5-flash` | default | 4.45 s | 5.63 s | 8.4% | 6.0% | 12.7% |
| `gemini-3.6-flash` | default | 4.28 s | 5.86 s | 8.6% | 9.7% | 6.5% |
| `gemini-3.5-flash` | minimal | 3.37 s | 4.53 s | 9.1% | n/a | n/a |
| `gemini-3.1-flash-lite` | default | 3.10 s | 3.44 s | 9.4% | 13.5% | 2.3% |
| `gemini-2.5-flash` | default | 4.00 s | 4.88 s | 10.4% | 13.0% | 5.7% |
| `gemini-flash-lite-latest` | default | 2.58 s | 2.98 s | 11.9% | 16.6% | 3.5% |
| `gemini-3.5-flash-lite` (old default) | default | 2.82 s | 4.55 s | 12.9% | 18.3% | 3.4% |
| `gemini-2.5-flash-lite` | default | 3.04 s | 4.58 s | 25.0% | 15.6% | 41.3% |

Three models were dropped in this round:

- `gemini-3.5-transcribe` returns its transcript as audio-transcription parts, not text, so it
  can't follow a rewrite prompt.
- `gemini-omni-1.1-flash` only works through the Interactions API.
- `gemini-3.7-flash` and `gemini-3.8-flash` reject the `minimal` thinking level.

**Round 2** used a sharper prompt that asked explicitly for self-corrections, the speaker's language
and digits (three runs per clip):

| Model | Thinking | p50 | p90 | Error | English | Chinese and mixed |
|---|---|---|---|---|---|---|
| `gemini-3.8-flash` | default | 5.56 s | 7.33 s | **1.0%** | 1.3% | 0.6% |
| `gemini-3.5-flash` | minimal | 3.53 s | 4.76 s | 2.5% | 2.2% | 3.0% |
| `gemini-3.1-flash-lite` | default | 2.88 s | 3.68 s | 3.1% | 3.4% | 2.5% |
| `gemini-3.5-flash-lite` | default | **2.43 s** | 4.30 s | 7.1% | 9.1% | 3.6% |
| `gemini-flash-lite-latest` | default | 2.85 s | 3.57 s | 7.9% | 10.3% | 3.7% |
| `gemini-flash-latest` | low | 4.56 s | 5.62 s | 11.2% | 16.8% | 1.5% |
| `gemini-3.7-flash` | low | 5.04 s | 7.60 s | 11.3% | 17.2% | 1.1% |
| `gemini-3.8-flash` | low | 4.42 s | 5.80 s | 11.7% | 17.6% | 1.3% |

The prompt change alone cut `gemini-3.1-flash-lite`'s error from 9.4% to 3.1%. The `low` thinking
level made the larger models less accurate, and on one clip `gemini-3.8-flash` returned nothing,
so Buddy leaves thinking at the model's default (`DICTATION_THINKING_LEVEL` is empty).

## Limits of this evaluation

- The voices are synthetic. Real speech through a laptop microphone has accents, overlap and room
  echo that text-to-speech does not, so real-world errors will be somewhat higher for every model, though the ranking
  should hold.
- Fourteen clips is a small set. A gap of 0.1 in the overall score is within run-to-run noise. The
  gaps we based the decision on, such as fidelity 4.07 against 4.68, or 2.7 s against 6.8 s, are
  well outside it.
- The judge is itself a Gemini model, so it may favour Gemini-style phrasing. It only compared
  Gemini models with each other, and every low score was checked against the judge's note.
- Latency was measured from one Windows laptop with six requests in flight. Your numbers will
  vary with network and API load; compare models within one run, not across runs.

## Running it again

```powershell
# 1. Build the clips (Windows; uses your GEMINI_API_KEY)
python tools/dictation_eval/make_corpus.py

# 2. Benchmark any models (append :minimal / :low to set a thinking level)
python tools/dictation_eval/bench.py --models gemini-3.1-flash-lite,gemini-3.8-flash,gemini-3.5-flash:minimal --runs 2 --results results.json
```

The bench always uses the prompt Buddy ships, so changing `DICTATION_PROMPT` and re-running shows
the effect of a prompt change directly. The clips go to `tools/dictation_eval/corpus/`, which is
git-ignored. A full run of six models takes about five minutes and makes about 170 dictation calls
and 170 judge calls.
