"""Caption a genuine window recording and extract the portfolio screenshots."""

import argparse
import subprocess
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "artifacts/demo-raw.mp4")
    parser.add_argument("--offset", type=float, default=1.5)
    args = parser.parse_args()
    output = ROOT / "artifacts/dataflow-studio-demo.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-ss",
            str(args.offset),
            "-i",
            str(args.input.resolve()),
            "-t",
            "60",
            "-vf",
            "subtitles=demo-captions.srt:force_style='FontName=Arial,FontSize=18,BorderStyle=3,Outline=1,Shadow=0,MarginV=12'",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            "-y",
            str(output),
        ],
        cwd=ROOT / "assets",
        check=True,
    )
    for second, name in [
        (3, "01-dashboard"),
        (12, "02-input-data"),
        (23, "03-processing"),
        (34, "04-before-after"),
        (56, "05-results"),
    ]:
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(args.offset + second),
                "-i",
                str(args.input.resolve()),
                "-frames:v",
                "1",
                "-y",
                str(ROOT / "assets/screenshots" / f"{name}.png"),
            ],
            check=True,
        )
    print(output)


if __name__ == "__main__":
    main()
