"""
Builds the dictation evaluation corpus: 16 kHz mono WAV clips plus refs.json.

  python tools/dictation_eval/make_corpus.py [--out tools/dictation_eval/corpus]

Clips:
  s1-s3   Windows SAPI voice (en-GB / en-US), short English with numbers and names.
  g1-g4   Gemini TTS voice: English with fillers and a self-correction, English jargon,
          Mandarin, and mixed Mandarin-English. Each also gets a "_noisy" copy at ~8 dB SNR.
  g5-g7   Gemini TTS voice, longer rambling dictations: an English update with action items,
          a Mandarin update with a list, and an English email paragraph that should stay prose.

refs.json maps each clip to {"spoken": what was said, "expect": an ideal result,
"format": "bullets" or "plain"}; the judge in bench.py compares outputs against these.

Needs GEMINI_API_KEY (config.json, env var or keyring, as Buddy itself resolves it) and Windows.
"""
import os
import sys
import json
import wave
import argparse
import subprocess
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import check_api_key_or_toast_and_exit  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

# (id, what the voice says, an ideal dictation result)
SAPI_SAMPLES = [
    ("s1", "Um, so I wanted to, uh, follow up on the quarterly planning doc. Can you send me the latest numbers for the B plus marketplace by Friday?",
     "I wanted to follow up on the quarterly planning doc. Can you send me the latest numbers for the B+ marketplace by Friday?"),
    ("s2", "Let's schedule the review for Tuesday at three p.m. and invite Heiko, Sunil and Benoit. Actually, make that four p.m.",
     "Let's schedule the review for Tuesday at 4 p.m. and invite Heiko, Sunil and Benoit."),
    ("s3", "The bid floor model improved revenue by two point three percent in the A B test, but latency went up by eight milliseconds.",
     "The bid floor model improved revenue by 2.3% in the A/B test, but latency went up by 8 ms."),
]

GEMINI_SAMPLES = [
    ("g1_en_fillers", "So, um, I think we should, uh, push the launch to next Wednesday, no wait, Thursday, because the, um, the data pipeline isn't ready yet.",
     "I think we should push the launch to next Thursday because the data pipeline isn't ready yet."),
    ("g2_en_jargon", "Can you check the BigQuery table for the P plus marketplace and see why the RTI latency spiked after the adserver deploy on Monday?",
     "Can you check the BigQuery table for the P+ marketplace and see why the RTI latency spiked after the adserver deploy on Monday?"),
    ("g3_zh", "我们下周二下午三点开会，讨论第四季度的预算，请大家提前准备好数据。",
     "我们下周二下午3点开会，讨论第四季度的预算，请大家提前准备好数据。"),
    ("g4_mixed", "我刚看了一下 BigQuery 的数据，B plus marketplace 的 revenue 上周涨了百分之五，主要是因为 floor optimization 的模型上线了。",
     "我刚看了一下BigQuery的数据，B+ marketplace的revenue上周涨了5%，主要是因为floor optimization的模型上线了。"),
    ("g5_en_list", "Hey team, um, quick update on the launch. So first, the dashboard is, uh, basically done, Sunil just needs to review it. "
     "Second, the pipeline is still, like, a bit flaky, so Heiko is looking into the retries. And, um, third, we need someone to book "
     "the room for the demo on Thursday at two. Oh and, uh, please send me your slides by Wednesday.",
     "Quick update on the launch:\n"
     "• The dashboard is done; Sunil needs to review it.\n"
     "• The pipeline is still flaky; Heiko is looking into the retries.\n"
     "• Someone needs to book the room for the demo on Thursday at 2.\n"
     "\n"
     "Please send me your slides by Wednesday."),
    ("g6_zh_list", "大家好，嗯，跟大家同步一下这周的进展。第一个是，那个，BigQuery 的表已经迁移完了。第二个就是，呃，floor optimization 的实验还在跑，"
     "预计周五出结果。还有就是，下周一我们要跟 Freddy 开个会，讨论一下 Q4 的规划，大家记得准备一下。",
     "同步一下本周进展：\n"
     "• BigQuery的表已迁移完成。\n"
     "• floor optimization实验仍在进行，预计周五出结果。\n"
     "• 下周一与Freddy开会讨论Q4规划，请大家提前准备。"),
    ("g7_en_email", "Hi Csaba, so, um, I wanted to let you know that, uh, the hiring for the data engineering manager role in Dublin is, you know, "
     "moving along, we have two candidates in the final round, and, um, I think we can probably make an offer by the end of next week, "
     "assuming the references come back fine.",
     "Hi Csaba, the hiring for the Data Engineering Manager role in Dublin is progressing. We have two candidates in the final round "
     "and expect to make an offer by the end of next week, assuming the references come back fine."),
]
BULLET_SAMPLES = {"g5_en_list", "g6_zh_list"}
NOISY_SAMPLES = {"g1_en_fillers", "g2_en_jargon", "g3_zh", "g4_mixed"}
NOISY_SNR_DB = 8


def write_wav(path: Path, samples: np.ndarray):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.clip(samples, -32768, 32767).astype(np.int16).tobytes())


def add_noise(samples: np.ndarray, snr_db: float) -> np.ndarray:
    """Adds low-frequency-weighted (brown-ish, high-passed) noise, closer to room/fan noise than white noise."""
    rng = np.random.default_rng(7)
    noise = np.cumsum(rng.standard_normal(len(samples)))
    noise -= np.convolve(noise, np.ones(400) / 400, "same")
    noise *= np.sqrt(np.mean(samples ** 2) / np.mean(noise ** 2)) / 10 ** (snr_db / 20)
    return samples + noise


def sapi_to_wav(text: str, path: Path):
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); "
        f"$s.SetOutputToWaveFile('{path}', $f); $s.Speak($env:BUDDY_EVAL_TEXT); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True,
                   env={**os.environ, "BUDDY_EVAL_TEXT": text})


def gemini_tts(client, text: str) -> np.ndarray:
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=f"Say naturally, like someone dictating a message: {text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore"))),
        ),
    )
    pcm24k = np.frombuffer(response.candidates[0].content.parts[0].inline_data.data, dtype=np.int16).astype(np.float32)
    return np.interp(np.arange(0, len(pcm24k), 1.5), np.arange(len(pcm24k)), pcm24k)  # 24 kHz -> 16 kHz


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(Path(__file__).parent / "corpus"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    refs = {}

    for sid, spoken, expect in SAPI_SAMPLES:
        sapi_to_wav(spoken, out / f"{sid}.wav")
        refs[sid] = {"spoken": spoken, "expect": expect, "format": "plain"}
        print(f"{sid}: SAPI")

    client = genai.Client(api_key=check_api_key_or_toast_and_exit())
    for sid, spoken, expect in GEMINI_SAMPLES:
        clean = gemini_tts(client, spoken)
        entry = {"spoken": spoken, "expect": expect, "format": "bullets" if sid in BULLET_SAMPLES else "plain"}
        write_wav(out / f"{sid}.wav", clean)
        refs[sid] = entry
        if sid in NOISY_SAMPLES:
            write_wav(out / f"{sid}_noisy.wav", add_noise(clean, NOISY_SNR_DB))
            refs[f"{sid}_noisy"] = entry
        print(f"{sid}: Gemini TTS, {len(clean) / 16000:.1f}s")

    (out / "refs.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(refs)} clips to {out}")


if __name__ == "__main__":
    main()
