#!/usr/bin/env python3
"""Generate a vertical "blackout"-style edit (1080x1920) with an original beat.

Everything (picture and sound) is synthesized by ffmpeg, so there is no
copyrighted material. The look changes every day: colours, caption, tempo.

Usage: python3 make_video.py OUTPUT.mp4 [--date YYYY-MM-DD]
Prints the caption to use for the post on stdout.
"""
import argparse
import datetime as dt
import json
import random
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1080, 1920
DURATION = 12  # seconds

PALETTES = [
    ("0xff006e", "0x8338ec", "0x3a86ff"),
    ("0xfb5607", "0xffbe0b", "0xff006e"),
    ("0x00f5d4", "0x00bbf9", "0x9b5de5"),
    ("0xf72585", "0x7209b7", "0x4cc9f0"),
    ("0x06d6a0", "0x118ab2", "0xffd166"),
    ("0xe63946", "0x1d3557", "0xf1faee"),
    ("0xff9f1c", "0x2ec4b6", "0xcbf3f0"),
]


def esc(text: str) -> str:
    """Escape text for ffmpeg drawtext inside a filtergraph."""
    return (text.replace("\\", "\\\\").replace(":", "\\:")
            .replace("'", "’").replace("%", "\\%").replace(",", "\\,"))


def build(out: Path, day: dt.date) -> str:
    rng = random.Random(day.toordinal())
    captions = json.loads((HERE / "captions.json").read_text(encoding="utf-8"))
    cap = captions[day.toordinal() % len(captions)]
    c0, c1, c2 = rng.choice(PALETTES)
    bpm = rng.choice([120, 126, 128, 132, 140])
    beat = 60 / bpm
    root = rng.choice([41.2, 43.65, 46.25, 49.0, 55.0])  # bass note, Hz
    black = round(beat * 0.28, 3)  # how long each blackout lasts

    m = f"mod(t\\,{beat:.4f})"
    # Picture: moving gradient, hue drift, pulse zoom, blackout on every beat,
    # caption words revealed one per bar.
    lines = cap["text"].split("\n")
    draw = []
    for i, line in enumerate(lines):
        y = f"(h/2)-{(len(lines) * 120) // 2}+{i * 120}"
        start = 1 + i * beat * 4
        draw.append(
            f"drawtext=fontfile={FONT}:text='{esc(line)}':fontsize=96:"
            f"fontcolor=white:borderw=6:bordercolor=black:"
            f"x=(w-text_w)/2:y={y}:enable='gte(t\\,{start:.3f})'"
        )
    vf = ",".join([
        f"hue=h=t*25",
        f"scale=w='{W}*(1+0.06*exp(-6*{m}))':h=-2:eval=frame",
        f"crop={W}:{H}",
        *draw,
        f"drawtext=fontfile={FONT}:text='{esc(cap['tag'])}':fontsize=54:"
        f"fontcolor=white@0.85:x=(w-text_w)/2:y=h-260",
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:"
        f"enable='lt({m}\\,{black})*gte(t\\,0.5)'",
        "format=yuv420p",
    ])
    video_src = (f"gradients=s={W}x{H}:c0={c0}:c1={c1}:c2={c2}:"
                 f"speed=0.03:r=30:d={DURATION}")

    # Sound: kick on every beat, offbeat hat, sliding bass.
    ph = f"mod(t,{beat:.4f})"
    off = f"mod(t+{beat / 2:.4f},{beat:.4f})"
    audio_expr = (
        f"0.9*sin(2*PI*(45+140*exp(-35*{ph}))*{ph})*exp(-7*{ph})"
        f"+0.15*(random(0)*2-1)*exp(-60*{off})"
        f"+0.25*sin(2*PI*{root}*(1+0.5*(mod(floor(t/({beat:.4f}*4)),2)))*t)"
        f"*(1-exp(-20*{off}))"
    )
    audio_src = f"aevalsrc='{audio_expr}':s=44100:d={DURATION}"

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", video_src,
        "-f", "lavfi", "-i", audio_src,
        "-vf", vf,
        "-af", "alimiter=limit=0.9,aformat=channel_layouts=stereo",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", "-shortest", str(out),
    ]
    subprocess.run(cmd, check=True)
    return cap["caption"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    p.add_argument("--date", type=dt.date.fromisoformat, default=dt.date.today())
    a = p.parse_args()
    print(build(a.output, a.date))


if __name__ == "__main__":
    main()
