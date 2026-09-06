#!/usr/bin/env python3
"""Generate a legally safe deterministic click-and-tone WAV for manual tests."""

import argparse
import math
import struct
import wave
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()
    rate = 16000
    frames = []
    for index in range(round(args.seconds * rate)):
        time = index / rate
        click = 0.7 * math.exp(-90.0 * (time % 0.5))
        tone = 0.2 * math.sin(2.0 * math.pi * (220.0 + 110.0 * time / args.seconds) * time)
        frames.append(struct.pack("<h", round(max(-1.0, min(1.0, click + tone)) * 32767)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"".join(frames))
    print(args.output)


if __name__ == "__main__":
    main()
