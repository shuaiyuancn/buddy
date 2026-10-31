# Dictation model evaluation

How we chose the Gemini model for Buddy's dictation (Right Alt) and how to send it a personal vocabulary,
how we measured both, and how to run the evaluation again when new models come out.
Last run: 31 October 2026, against Buddy v0.4.1.

## Recommendation

| Use | Model | Setting |
|---|---|---|
| Default (fast and accurate) | `gemini-3.1-flash-lite` | `"DICTATION_MODEL": "gemini-3.1-flash-lite"` (the default) |
| Highest accuracy, about 2x slower | `gemini-3.8-flash` | `"DICTATION_MODEL": "gemini-3.8-flash"` |

Add the names and terms you use to your vocabulary (**Edit Dictation Vocabulary** in the tray menu).
In our tests, names on the list went from 15% to 100% spelled right and fidelity rose from 4.1 to
4.6 out of 5, with no cost in speed. No model change came close to that.

`gemini-3.1-flash-lite` returns a rewritten dictation in about 3.3 seconds (median). Without a
vocabulary, its remaining errors are mishearings of unusual names and of English terms inside Chinese
speech. `gemini-3.8-flash` makes fewer of those mistakes but takes about 5.5 seconds, which feels slow
when you are waiting to paste.

We ruled out `gemini-3.5-flash` with minimal thinking. Its fidelity score was slightly higher without a
vocabulary, but its mistakes are the wrong kind for a dictation tool: it translated English words in
Chinese sentences ("revenue" to 收入), swapped a name for a different one, changed "Let's" to "I'll",
and once wrote timestamps into the text. You can spot and fix a mishearing at a glance, but a changed
meaning can slip through unnoticed.

## What dictation is asked to do

Dictation is not a word-for-word transcript. Buddy sends the recorded audio to Gemini in one call
with a prompt (`DICTATION_PROMPT` in `src/ai/transcriber.py`) that asks for:

- concise, clear, professional sentences, without fillers, repetitions or false starts
- self-corrections applied ("Wednesday, no wait, Thursday" becomes "Thursday")
- every fact, name, number, request and commitment kept, and nothing added
- the speaker's own language: Chinese stays Chinese, and English terms in mixed speech stay English
- `•` bullets on separate lines when the speaker lists several items, and plain sentences otherwise

If the user has a vocabulary file, it goes in the request's system instruction as a spelling
glossary (see [Vocabulary](#vocabulary) for why it goes there and not in the prompt).

## Test set

Fourteen clips, made by `tools/dictation_eval/make_corpus.py`. Each clip has a script (what is said),
an ideal result, and the expected format (bullets or plain). Names in the clips are fictional.

| Clips | Voice | What they test |
|---|---|---|
| `s1` to `s3` | Windows SAPI (en-GB, en-US) | Short English with fillers, a self-correction, three unusual first names, numbers and percentages |
| `g1_en_fillers` | Gemini TTS | Heavy fillers and "Wednesday, no wait, Thursday" |
| `g2_en_jargon` | Gemini TTS | BigQuery, Kafka consumer lag, API gateway |
| `g3_zh` | Gemini TTS | Mandarin with a time and a quarter |
| `g4_mixed` | Gemini TTS | Mandarin with English terms and a percentage |
| `g1` to `g4`, `_noisy` | Same, plus noise | The four clips above with low-frequency room noise at about 8 dB SNR |
| `g5_en_list` | Gemini TTS | 21 s rambling team update with three action items and a request (should become bullets) |
| `g6_zh_list` | Gemini TTS | 21 s Mandarin update with a list and a name (should become bullets) |
| `g7_en_email` | Gemini TTS | 18 s rambling email paragraph (should stay prose, no bullets) |

All clips are 16 kHz mono 16-bit WAV, the same format Buddy records for dictation.

## How each model was scored

Each clip was sent twice per model with Buddy's exact prompt, six requests at a time.

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

### Models, without a vocabulary

Two runs per clip, 14 clips, judge scores out of 5:

| Model | Thinking | p50 | p90 | Fidelity | Clarity | Format | Overall |
|---|---|---|---|---|---|---|---|
| `gemini-3.8-flash` | default | 5.52 s | 9.47 s | **4.68** | 5.00 | 5.00 | **4.89** |
| `gemini-3.5-flash` | minimal | 3.23 s | 5.30 s | 4.32 | 4.89 | 4.93 | 4.71 |
| **`gemini-3.1-flash-lite`** | default | 3.30 s | 6.84 s | 4.11 | 4.89 | 4.86 | 4.62 |
| `gemini-3.5-flash-lite` | default | **2.88 s** | 4.46 s | 3.82 | 4.29 | 4.96 | 4.36 |

`gemini-3.1-flash-lite`'s low fidelity scores come almost entirely from two things: the fictional
names in `s2` (Thibault, Siobhan and Anuj came out as "Eybold", "Shavonne" and "Anush"), and
"BigQuery" heard as 被Query in Chinese speech. A vocabulary fixes exactly those.

An earlier run of the same comparison, on a version of the clips with different names and terms, gave
the same order (`gemini-3.8-flash` 4.93, `gemini-3.5-flash` minimal 4.83, `gemini-3.1-flash-lite`
4.81, `gemini-3.5-flash-lite` 4.51 overall). `gemini-3.6-flash` (4.74, 4.8 s median) and
`gemini-flash-lite-latest` (4.50) were also tested there and are not competitive.

Example output from `gemini-3.1-flash-lite` for `g5_en_list` (21 seconds of rambling speech):

```
Hey team, quick update on the launch:

• The dashboard is basically done; Siobhan just needs to review it.
• The pipeline is still a bit flaky, so Thibault is looking into the retries.
• We need someone to book the room for the demo on Thursday at 2:00.

Please send me your slides by Wednesday.
```

### Vocabulary

Same clips, with `tools/dictation_eval/vocabulary_example.txt` (the clips' names and a few terms):

| Model | Vocabulary | p50 | p90 | Fidelity | Overall |
|---|---|---|---|---|---|
| `gemini-3.1-flash-lite` | none | 3.30 s | 6.84 s | 4.11 | 4.62 |
| `gemini-3.1-flash-lite` | example | 2.90 s | 5.02 s | **4.60** | **4.77** |
| `gemini-3.8-flash` | none | 5.52 s | 9.47 s | 4.68 | 4.89 |
| `gemini-3.8-flash` | example | 6.25 s | 9.20 s | **5.00** | **4.99** |

A real vocabulary is much longer than the example and mostly lists names that are *not* in a given
dictation. We tested that case with a 138-term personal vocabulary (colleagues, products and tools,
plus 60 known mishearings), none of which occur in the clips. Latency did not change (3.3 s median).

How the vocabulary is sent matters as much as what is in it. On the three clips with names
(`s2`, `g5_en_list`, `g6_zh_list`, four runs each), we counted how often a name from the vocabulary
replaced a different name the speaker had said:

| How the vocabulary was sent (`gemini-3.1-flash-lite`) | Wrong listed name inserted | Spoken names right |
|---|---|---|
| No vocabulary | 0 of 12 | 15% |
| 138 terms in the prompt, told to use only clear matches | 8 of 12 | 0% |
| 138 terms in the system instruction, as a glossary "most entries will not occur" | 1 of 12 | 0% |
| Same, plus the 60 known mishearings (**what Buddy does**) | **0 of 12** | 6% |
| Same framing, with the clip's names in the glossary | 0 of 12 | **100%** |

With the list in the prompt, the model kept turning "Thibault" into a listed colleague's name. Sent as a
system instruction, framed as a glossary that is mostly irrelevant, the swaps stopped. `gemini-3.8-flash`
made no swaps with the glossary framing either. A name that is not on the list is still often
misspelled (the last column), so add the names you dictate.

### Earlier rounds: transcription accuracy

Before dictation switched to rewriting, we ran two rounds that asked for a cleaned-up transcript
and scored it with a token error rate (word-level edit distance against the ideal text, per
character for Chinese, after normalising formatting such as "2.3%" and "2.3 percent"). These rounds
used the first 11 clips, in an earlier version with different names and terms. They are kept here
because they show which models hear accurately, and how much the prompt matters.

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
  echo that text-to-speech does not, so real-world errors will be somewhat higher for every model,
  though the ranking should hold.
- Fourteen clips is a small set. A gap of 0.1 in the overall score is within run-to-run noise (the
  same model's p90 latency moved by more than a second between runs). The gaps we based decisions on,
  such as 0 against 8 name swaps, or 15% against 100% names right, are well outside it.
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

# 3. Optionally test a vocabulary, sent the way Buddy sends yours
python tools/dictation_eval/bench.py --models gemini-3.1-flash-lite --vocabulary tools/dictation_eval/vocabulary_example.txt
```

The bench always uses the prompt and request settings Buddy ships, so changing `DICTATION_PROMPT` or
the vocabulary handling and re-running shows the effect directly. The clips go to
`tools/dictation_eval/corpus/`, which is git-ignored. A run of four models takes about five minutes
and makes about 110 dictation calls and 110 judge calls.
