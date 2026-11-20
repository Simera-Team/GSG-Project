"""Language check tests for English source enforcement (R-11).

Rules tested:
1. An English CV from Cv_Samples text: accepted.
2. An Arabic CV text: rejected, no LLM call (assert fake AI never called).
3. A French CV text (Latin script, few English markers): rejected.
4. An English CV containing an Arabic name and one Arabic line: accepted.
5. A LinkedIn Markdown export in English: accepted.
6. Text under 200 letters: language check skipped.
7. Vetting JSON: language check skipped.
"""

import json
from pathlib import Path

import pytest

from app.application.dto.extracted_document import ExtractedDocument
from app.application.services.cv_processing_service import JobStatus
from app.application.services.vetting_parser import VettingParser
from app.application.use_cases.process_cv import ProcessCVUseCase
from app.domain.entities.source_file import SourceFile
from app.domain.services.language import (
    MIN_LETTERS_FOR_CHECK,
    is_english,
)
from app.infrastructure.reference_data import seed_country_catalog, seed_skill_catalog
from tests.helpers import answer, as_json
from tests.test_processing_service import FakeAI, make_service


# 1. An English CV from Cv_Samples text: accepted.
def test_english_cv_from_cv_samples_accepted():
    sample_path = Path(__file__).resolve().parent.parent / "Cv_Samples" / "sahar-fayyad.md"
    text = sample_path.read_text(encoding="utf-8")
    assert is_english(text) is True

    ai = FakeAI(as_json(answer()))
    doc = ExtractedDocument(source_name="sahar-fayyad.md", text=text)
    result = make_service(ai).process(doc)

    assert ai.calls == 1
    assert result.status != JobStatus.REJECTED


# 2. An Arabic CV text: rejected, no LLM call (assert the fake AI was never called).
def test_arabic_cv_text_rejected_no_llm_call():
    arabic_cv = (
        "السيرة الذاتية\n"
        "الاسم: أحمد محمد خليل\n"
        "المسمى الوظيفي: مهندس برمجيات أول ومطور نظم معلومات\n"
        "الخبرات المهنية:\n"
        "- مهندس برمجيات أول في شركة الشرق الأوسط للتقنيات الحديثة (2019 - حتى الآن)\n"
        "- تطوير وصيانة تطبيقات الويب باستخدام لغة بايثون وقواعد بيانات بوستجريس\n"
        "- تصميم وبناء واجهات البرمجة والخدمات المصغرة وفق أعلى المعايير\n"
        "- إدارة وتوجيه الفرق الهندسية ومراجعة الأكواد البرمجية\n"
        "المؤهلات العلمية والتعليم:\n"
        "- درجة البكالوريوس في علم الحاسوب، الجامعة الأردنية، تقدير ممتاز (2015 - 2019)\n"
        "المهارات الفنية:\n"
        "- لغات البرمجة: بايثون، جافا سكريبت، إس كيو إل، بي إتش بي\n"
        "- أطر العمل: فاست إيه بي آي، دجانغو، فلاسك، رياكت\n"
        "اللغات:\n"
        "- اللغة العربية: اللغة الأم\n"
    )
    assert not is_english(arabic_cv)

    ai = FakeAI(as_json(answer()))
    doc = ExtractedDocument(source_name="arabic_cv.pdf", text=arabic_cv)
    result = make_service(ai).process(doc)

    assert ai.calls == 0
    assert result.status == JobStatus.REJECTED
    assert result.status == "rejected"
    assert result.reason == "unsupported_language"
    assert result.rule == "R-11"
    assert result.message == "Only CVs written in English are accepted. Please upload an English version."
    assert len(result.attempts) == 0
    assert len(result.review_items) == 0


# 3. A French CV text (Latin script, few English markers): rejected.
def test_french_cv_text_rejected():
    french_cv = (
        "Curriculum Vitae\n"
        "Nom: Pierre Dupont\n"
        "Poste: Développeur Full Stack Senior\n"
        "Expérience professionnelle:\n"
        "- Développeur chez Société Générale à Paris depuis 2018.\n"
        "- Conception et développement d'applications d'entreprise en microservices.\n"
        "- Maintenance corrective et évolutive des architectures logicielles existantes.\n"
        "- Collaboration avec les chefs de projet et les équipes métier.\n"
        "Formation académique:\n"
        "- Diplôme d'ingénieur en informatique, École Polytechnique, 2013-2018.\n"
        "- Baccalauréat scientifique mention très bien.\n"
        "Compétences informatiques:\n"
        "- Langages: Python, Java, TypeScript, SQL.\n"
        "- Outils: Git, Docker, Kubernetes, Jenkins.\n"
        "Centres d'intérêt: Lecture, voyages, course à pied.\n"
    )
    assert not is_english(french_cv)

    ai = FakeAI(as_json(answer()))
    doc = ExtractedDocument(source_name="french_cv.pdf", text=french_cv)
    result = make_service(ai).process(doc)

    assert ai.calls == 0
    assert result.status == JobStatus.REJECTED
    assert result.reason == "unsupported_language"
    assert result.rule == "R-11"


# 4. An English CV containing an Arabic name and one Arabic line: accepted.
def test_english_cv_with_arabic_name_and_one_arabic_line_accepted():
    mixed_cv = (
        "Ahmad Khalil (أحمد خليل)\n"
        "Software Engineer\n"
        "Email: ahmad@example.com | Phone: +962790001234\n"
        "اللغة العربية: اللغة الأم\n"
        "Summary\n"
        "Passionate software engineer with over five years of experience in building scalable web applications.\n"
        "Experience\n"
        "Senior Software Engineer at Tech Solutions (2020 - Present)\n"
        "- Built RESTful APIs using Python, FastAPI, and PostgreSQL with high performance.\n"
        "- Collaborated with cross-functional teams to design and deliver robust microservices.\n"
        "- Mentored junior engineers and led code reviews to maintain code quality.\n"
        "Education\n"
        "Bachelor of Science in Computer Science from University of Jordan (2015 - 2019)\n"
        "Skills\n"
        "Python, Docker, SQL, Git, Linux, FastAPI, Problem Solving, Teamwork\n"
    )
    assert is_english(mixed_cv) is True

    ai = FakeAI(as_json(answer()))
    doc = ExtractedDocument(source_name="mixed_cv.pdf", text=mixed_cv)
    result = make_service(ai).process(doc)

    assert ai.calls == 1
    assert result.status != JobStatus.REJECTED


# 5. A LinkedIn Markdown export in English: accepted.
def test_linkedin_markdown_export_in_english_accepted():
    linkedin_md = (
        "# Sara Yousef\n"
        "Senior Product Manager at Cloud Inc.\n"
        "Amman, Jordan\n\n"
        "## Summary\n"
        "Experienced product manager with a proven track record of delivering SaaS products from inception to scale.\n\n"
        "## Experience\n"
        "### Senior Product Manager\n"
        "Cloud Inc. · Full-time\n"
        "Jan 2021 - Present · 3 yrs 5 mos\n"
        "Amman, Jordan\n"
        "- Leading product roadmap and development for cloud management platform.\n"
        "- Working with engineering, design, and sales teams to drive adoption.\n\n"
        "## Education\n"
        "### Princess Sumaya University for Technology\n"
        "Bachelor of Science in Management Information Systems\n"
        "2014 - 2018\n\n"
        "## Skills\n"
        "Product Management, Agile Methodologies, SaaS, User Research, Roadmapping\n"
    )
    assert is_english(linkedin_md) is True

    ai = FakeAI(as_json(answer()))
    doc = ExtractedDocument(source_name="linkedin_export.md", text=linkedin_md)
    result = make_service(ai).process(doc)

    assert ai.calls == 1
    assert result.status != JobStatus.REJECTED


# 6. Text under 200 letters: language check skipped.
def test_text_under_200_letters_language_check_skipped():
    short_text = "Software Developer with Python and SQL skills."
    letters_count = len([c for c in short_text if c.isalpha()])
    assert letters_count < MIN_LETTERS_FOR_CHECK
    assert is_english(short_text) is True

    # Short foreign text also skips the check
    short_arabic = "مهندس برمجيات بايثون"
    assert len([c for c in short_arabic if c.isalpha()]) < MIN_LETTERS_FOR_CHECK
    assert is_english(short_arabic) is True

    # Processing proceeds to LLM rather than being rejected by language check
    ai = FakeAI(as_json(answer()))
    doc = ExtractedDocument(source_name="short.docx", text=short_text)
    result = make_service(ai).process(doc)

    assert ai.calls == 1
    assert result.status != JobStatus.REJECTED


# 7. Vetting JSON: language check skipped.
def test_vetting_json_language_check_skipped():
    vetting_payload = json.dumps({
        "skills": [
            {"name": "Python", "level": 5},
            {"name": "React", "level": 4}
        ]
    })

    # 7a. Direct parser invocation
    parser = VettingParser(seed_skill_catalog())
    parsed = parser.parse(vetting_payload, "vetting.json")
    assert len(parsed.skills) == 2
    assert parsed.skills[0].skill_name == "Python"

    # 7b. End-to-end ProcessCVUseCase execution
    class DummyRepo:
        def get_source_file(self, file_id):
            return SourceFile(
                file_id=file_id,
                profile_id=1,
                file_type="json",
                original_name="vetting.json",
                file_hash="dummy_hash",
                storage_path="/dummy/path",
                source_kind="vetting",
            )

        def set_file_status(self, *args, **kwargs):
            pass

        def next_attempt_number(self, file_id):
            return 1

        def save_attempts(self, *args, **kwargs):
            return [1]

        def save_field_records(self, *args, **kwargs):
            return {}

        def load_profile_field_records(self, profile_id):
            return []

        def replace_profile(self, *args, **kwargs):
            pass

        def replace_open_reviews(self, *args, **kwargs):
            pass

        def set_change_context(self, *args, **kwargs):
            pass

    class DummyUoW:
        def commit(self):
            pass

        def rollback(self):
            pass

    class DummyReader:
        def read(self, source):
            return ExtractedDocument(source_name="vetting.json", text=vetting_payload)

    class DummyCatalogs:
        def country_catalog(self):
            return seed_country_catalog()

        def skill_catalog(self):
            return seed_skill_catalog()

    ai = FakeAI()
    use_case = ProcessCVUseCase(
        DummyRepo(), DummyCatalogs(), DummyReader(), ai, DummyUoW()
    )
    result = use_case.execute(1)

    # FakeAI was never called because vetting doesn't need an LLM
    assert ai.calls == 0
    # Status is DONE, not REJECTED
    assert result.status != JobStatus.REJECTED
    assert result.status == JobStatus.DONE
