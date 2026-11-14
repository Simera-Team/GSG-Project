"""The shared skill vocabulary: canonical names, aliases and the stop list.

The table is seeded before the first run with common technology names and their
variants, so most skills map on day one. A term that matches nothing becomes a
system decision (R-09); once approved it is added here, so the same term never
reaches review twice.

The seed lives in code for now. It is the obvious thing to move behind a
repository once an admin can manage skills and aliases from the interface; the
:class:`SkillAliasTable` constructor already takes its data as arguments so that
move needs no change above this module.
"""

from collections.abc import Iterable, Mapping
from typing import Final

from app.application.ai.text_matching import bounded_edit_distance, canonical_text

#: Canonical skill name to the spellings that mean it. Lookups fold case and
#: punctuation first, so only genuinely different spellings need listing.
SEED_SKILL_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "React": ("reactjs", "react.js", "react js"),
    "Angular": ("angularjs", "angular.js", "angular 2+"),
    "Vue.js": ("vue", "vuejs", "vue js"),
    "Next.js": ("nextjs", "next js"),
    "Node.js": ("node", "nodejs", "node js"),
    "Express.js": ("express", "expressjs"),
    "JavaScript": ("js", "java script", "ecmascript"),
    "TypeScript": ("ts", "type script"),
    "Python": ("python3", "python 3"),
    "Java": ("java se", "core java"),
    "C#": ("csharp", "c sharp"),
    "C++": ("cpp", "c plus plus"),
    "C": (),
    "Go": ("golang",),
    "Rust": (),
    "PHP": (),
    "Laravel": (),
    "Ruby": (),
    "Ruby on Rails": ("rails", "ror"),
    "Kotlin": (),
    "Swift": (),
    "Dart": (),
    "Flutter": (),
    "React Native": ("react-native",),
    "Django": (),
    "Flask": (),
    "FastAPI": ("fast api",),
    "Spring": ("spring framework",),
    "Spring Boot": ("springboot",),
    ".NET": ("dotnet", "dot net", "asp.net", "asp net"),
    "SQL": (),
    "PostgreSQL": ("postgres", "postgre sql", "psql"),
    "MySQL": ("my sql",),
    "SQLite": (),
    "Microsoft SQL Server": ("mssql", "sql server"),
    "Oracle Database": ("oracle db", "oracle"),
    "MongoDB": ("mongo",),
    "Redis": (),
    "Elasticsearch": ("elastic search", "elastic"),
    "RabbitMQ": ("rabbit mq",),
    "Apache Kafka": ("kafka",),
    "Celery": (),
    "GraphQL": ("graph ql",),
    "REST": ("rest api", "restful", "restful api", "rest apis"),
    "gRPC": ("grpc",),
    "Docker": (),
    "Kubernetes": ("k8s",),
    "Terraform": (),
    "Ansible": (),
    "Jenkins": (),
    "GitHub Actions": ("github action",),
    "GitLab CI": ("gitlab ci/cd",),
    "Git": (),
    "Linux": (),
    "Bash": ("shell scripting", "shell"),
    "Nginx": (),
    "AWS": ("amazon web services",),
    "Azure": ("microsoft azure",),
    "Google Cloud Platform": ("gcp", "google cloud"),
    "SQLAlchemy": ("sql alchemy",),
    "Pydantic": (),
    "pandas": (),
    "NumPy": ("numpy",),
    "scikit-learn": ("sklearn", "scikit learn"),
    "TensorFlow": ("tensor flow",),
    "PyTorch": ("torch",),
    "LangChain": ("lang chain",),
    "HTML": ("html5",),
    "CSS": ("css3",),
    "Sass": ("scss",),
    "Tailwind CSS": ("tailwind", "tailwindcss"),
    "Bootstrap": (),
    "Redux": (),
    "Jest": (),
    "Pytest": ("py.test",),
    "Selenium": (),
    "Cypress": (),
    "Figma": (),
    "Jira": (),
    "Agile": ("agile methodology",),
    "Scrum": (),
    "CI/CD": ("ci cd", "cicd", "continuous integration"),
    "Microservices": ("micro services", "microservice"),
    "OAuth 2.0": ("oauth", "oauth2"),
    "JWT": ("json web token", "json web tokens"),
    "WebSockets": ("websocket", "web sockets"),
    "Unit Testing": ("unit tests",),
    "R": (),
    "MATLAB": ("matlab",),
    "Power BI": ("powerbi",),
    "Tableau": (),
    "Excel": ("microsoft excel", "ms excel"),
}

#: Self-claimed traits that are dropped in v0.1 (N-SKILL-04 / R-07). They
#: cannot be vetted and would crowd out the technical skills that matching
#: relies on. If they are wanted later, they belong in a separate soft-skill
#: list with its own short fixed vocabulary, never mixed in here.
SEED_SOFT_SKILL_STOP_LIST: Final[frozenset[str]] = frozenset(
    {
        "team player",
        "teamwork",
        "team work",
        "hardworking",
        "hard working",
        "hard worker",
        "communication",
        "communication skills",
        "good communication",
        "leadership",
        "leader",
        "problem solving",
        "problem solver",
        "critical thinking",
        "time management",
        "self motivated",
        "self-motivated",
        "fast learner",
        "quick learner",
        "detail oriented",
        "detail-oriented",
        "attention to detail",
        "creative",
        "creativity",
        "adaptable",
        "adaptability",
        "flexible",
        "organised",
        "organized",
        "punctual",
        "responsible",
        "motivated",
        "passionate",
        "multitasking",
        "interpersonal skills",
        "work under pressure",
        "works under pressure",
        "presentation skills",
        "customer service",
        "negotiation",
    }
)

#: Canonical names that are also ordinary English words. They are kept only
#: when the model extracted them as skills from the sentence's context, and
#: they are never split or fuzzy-matched (N-SKILL-05 / R-08).
SEED_AMBIGUOUS_SKILLS: Final[frozenset[str]] = frozenset(
    {"Go", "R", "C", "Swift", "Spring", "Rust", "Dart"}
)

#: Shortest name that may be fuzzy-matched at all (N-SKILL-03).
FUZZY_MIN_LENGTH: Final[int] = 5


class SkillAliasTable:
    """Canonicalises a skill spelling against the shared vocabulary.

    All lookups go through :func:`canonical_text`, so case, spacing and the
    punctuation variants a model tends to rewrite never need their own alias.
    """

    def __init__(
        self,
        aliases: Mapping[str, Iterable[str]] | None = None,
        soft_skill_stop_list: Iterable[str] | None = None,
        ambiguous_skills: Iterable[str] | None = None,
    ) -> None:
        source = SEED_SKILL_ALIASES if aliases is None else aliases

        self._lookup: dict[str, str] = {}
        for canonical, variants in source.items():
            self._lookup[self._key(canonical)] = canonical
            for variant in variants:
                self._lookup[self._key(variant)] = canonical

        self._soft_skills = frozenset(
            self._key(name)
            for name in (
                SEED_SOFT_SKILL_STOP_LIST
                if soft_skill_stop_list is None
                else soft_skill_stop_list
            )
        )
        self._ambiguous = frozenset(
            SEED_AMBIGUOUS_SKILLS if ambiguous_skills is None else ambiguous_skills
        )

    @property
    def canonical_names(self) -> frozenset[str]:
        """Every canonical skill name the table knows."""
        return frozenset(self._lookup.values())

    def is_soft_skill(self, name: str) -> bool:
        """Whether ``name`` is on the soft-skill stop list (N-SKILL-04)."""
        return self._key(name) in self._soft_skills

    def is_ambiguous(self, name: str) -> bool:
        """Whether ``name`` is a short name that doubles as an ordinary word."""
        return self.resolve(name) in self._ambiguous or name in self._ambiguous

    def resolve(self, name: str) -> str | None:
        """Return the canonical name for an exact or alias match (N-SKILL-01)."""
        return self._lookup.get(self._key(name))

    def resolve_fuzzy(self, name: str) -> str | None:
        """Return the canonical name for a near-miss spelling (N-SKILL-03).

        Edit distance 1 is allowed for 5 to 8 characters and 2 from 9 upwards;
        shorter names are never fuzzy-matched, because at that length almost
        everything is one edit from something else.
        """
        key = self._key(name)
        if len(key) < FUZZY_MIN_LENGTH:
            return None

        max_distance = 1 if len(key) <= 8 else 2
        best: tuple[int, str] | None = None

        for alias, canonical in self._lookup.items():
            distance = bounded_edit_distance(key, alias, max_distance)
            if distance is None or distance == 0:
                continue
            if best is None or distance < best[0]:
                best = (distance, canonical)

        return best[1] if best else None

    def register(self, canonical: str, *aliases: str) -> None:
        """Add an approved mapping to the table (the answer to an R-09 decision)."""
        self._lookup[self._key(canonical)] = canonical
        for alias in aliases:
            self._lookup[self._key(alias)] = canonical

    @staticmethod
    def _key(name: str) -> str:
        """Fold a name for lookup, keeping the characters that carry meaning.

        ``+``, ``#`` and ``.`` are kept because they are part of the name:
        ``C#`` must not fold onto ``C``.
        """
        folded = canonical_text(name)
        return "".join(
            char for char in folded if char.isalnum() or char in {"+", "#", ".", " "}
        ).strip()
