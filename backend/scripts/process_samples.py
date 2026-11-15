"""Run the full CV pipeline on sample files and write the results as JSON.

    text extraction -> Gemini (with retries) -> schema validation
    -> field records with evidence checks -> review items -> profile

Nothing is saved to the database; this is for checking results.
Needs GEMINI_API_KEY in .env. Each file is one or more LLM calls.

Usage (from the backend folder):
    python -m scripts.process_samples
    python -m scripts.process_samples --only pilot_cv_sam_carter.pdf
"""

import argparse
import json
import sys
from pathlib import Path

from app.application.dto.extracted_document import ExtractedDocument
from app.application.services.cv_processing_service import CVProcessingService
from app.core.config import settings
from app.infrastructure.ai.ai_client_factory import create_ai_client
from app.infrastructure.file_processing.extractor_factory import get_extractor
from app.infrastructure.reference_data import seed_country_catalog, seed_skill_catalog

SUPPORTED = {".pdf", ".docx", ".md"}


def to_document(path: Path) -> ExtractedDocument:
    result = get_extractor(path.suffix).extract(path.read_bytes())
    return ExtractedDocument(
        source_name=path.name,
        text=result.text,
        # Page markers only make sense for real pages (PDF).
        page_texts=[p.text for p in result.pages] if path.suffix.lower() == ".pdf" else [],
        hyperlinks=result.hyperlinks,
        extraction_method=result.method,
        ocr_confidence=result.ocr_confidence,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="Cv_Samples")
    parser.add_argument("--output", default="processing_output")
    parser.add_argument("--only", help="process a single file name")
    args = parser.parse_args()

    service = CVProcessingService(
        ai_client=create_ai_client(settings),
        countries=seed_country_catalog(),
        skills=seed_skill_catalog(),
        confidence_threshold=settings.REVIEW_CONFIDENCE_THRESHOLD,
        max_attempts=settings.LLM_MAX_ATTEMPTS,
        retry_base_seconds=settings.LLM_RETRY_BASE_SECONDS,
    )

    input_dir, output_dir = Path(args.input), Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in input_dir.iterdir()
                   if p.suffix.lower() in SUPPORTED and (not args.only or p.name == args.only))

    for path in files:
        result = service.process(to_document(path))
        out = output_dir / f"{path.stem}.json"
        out.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
                       encoding="utf-8")

        accepted = sum(not r.needs_review for r in result.field_records)
        print(f"{result.status:12} {path.name:48} attempts={len(result.attempts)} "
              f"fields={len(result.field_records)} accepted={accepted} "
              f"review={len(result.review_items)}"
              + (f"  ({result.reason})" if result.status == "failed" else ""))

    print(f"\nResults -> {output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
