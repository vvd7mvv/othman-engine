"""othman-engine align FILE [-o out.json] [--start S] [--end E]   |   othman-engine download"""
import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from othman_engine import alignment, quran
from othman_engine.errors import ProcessingError


def to_json(result: alignment.Alignment) -> dict:
    names = {s.number: (s.name_ar, s.name_en) for s in quran.surahs()}
    data = {"version": alignment.VERSION, **asdict(result)}
    for segment in data["segments"]:
        segment["surah_name_ar"], segment["surah_name_en"] = names[segment["surah"]]
        # index: ترتيب الكلمة في نص Tanzil الإملائي للآية (البسملة الآية 0)
        segment["words"] = [{"index": i, "start": a, "end": b} for i, a, b in segment["words"]]
        segment["pauses"] = [{"start": a, "end": b} for a, b in segment["pauses"]]
    return data


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="othman-engine", description="Quran recitation → surah, ayahs and word timings")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download", help="download the model and Tanzil text")
    align = commands.add_parser("align", help="align a recitation file (audio or video)")
    align.add_argument("file", type=Path)
    align.add_argument("-o", "--output", type=Path, help="write JSON here (default: print)")
    align.add_argument("--start", type=float, default=0.0, help="seconds")
    align.add_argument("--end", type=float, help="seconds")
    align.add_argument("--threads", type=int, help="CPU threads for the model")
    args = parser.parse_args(argv)

    if args.command == "download":
        from othman_engine.download import main as download
        download()
        return

    from othman_engine.engine import Engine
    started = time.time()
    try:
        result = Engine(args.threads).align_file(args.file, args.start, args.end)
    except ProcessingError as error:
        sys.exit(f"error [{error.code}]: {error}")
    text = json.dumps(to_json(result), ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"{len(result.quran_segments())} ayahs in {time.time() - started:.1f}s → {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
