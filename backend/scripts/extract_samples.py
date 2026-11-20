"""Extract text from every CV in a folder and write one JSON file per CV.

Nothing is saved to the database; this is only for checking extraction.
For the full pipeline (LLM, validation, review, profile) use process_samples.

Usage (from the backend folder):
    python -m scripts.extract_samples
    python -m scripts.extract_samples --input Cv_Samples --output extraction_output
"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from app.infrastructure.file_processing.extractor_factory import get_extractor

SUPPORTED = {".pdf", ".docx", ".md"}


def extract_file(path: Path) -> dict:
    started = time.perf_counter()
    result = get_extractor(path.suffix).extract(path.read_bytes())

    return {
        "file_name": path.name,
        "file_type": path.suffix.lower().lstrip("."),
        "extraction_method": result.method,
        "ocr_confidence": result.ocr_confidence,
        "page_count": result.page_count,
        "char_count": len(result.text),
        "seconds": round(time.perf_counter() - started, 2),
        "hyperlinks": result.hyperlinks,
        "pages": [
            {k: v for k, v in asdict(p).items() if k != "text"}
            for p in result.pages
        ],
        "raw_text": result.text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="Cv_Samples")
    parser.add_argument("--output", default="extraction_output")
    args = parser.parse_args()

    input_dir, output_dir = Path(args.input), Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in input_dir.iterdir() if p.suffix.lower() in SUPPORTED)
    if not files:
        print(f"No PDF/DOCX/MD files found in {input_dir}")
        return 1

    failed = 0
    for path in files:
        try:
            data = extract_file(path)
        except Exception as exc:  # report and keep going with the others
            failed += 1
            print(f"FAIL  {path.name}: {exc}")
            continue

        out = output_dir / f"{path.stem}.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        conf = f" conf={data['ocr_confidence']:.2f}" if data["ocr_confidence"] else ""
        print(f"OK    {path.name:50} {data['extraction_method']:5} "
              f"{data['char_count']:6} chars{conf}")

    print(f"\n{len(files) - failed}/{len(files)} extracted -> {output_dir}/")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
