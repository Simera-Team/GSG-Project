"""Reference lists: countries, standard skills and skill aliases.

The database (country, skill, skill_alias tables) is the source of truth in
production, and the administrator extends it; these lists are what the
migrations seed and what is used when no database is connected (sample
checks, unit tests). Migration 3c7f1a9e5b42 inserts exactly these skills
and aliases.

Aliases are only needed for real synonyms: spelling variants such as
"Node JS" / "node.js" / "NodeJS" or "Pandas (Software)" already match through
the match key (see domain/services/skills.py).
"""

from app.domain.services.countries import CountryCatalog
from app.domain.services.skills import SkillCatalog

SEED_COUNTRIES: list[tuple[str, str]] = [
    ("Jordan", "JO"), ("Palestine", "PS"), ("United Arab Emirates", "AE"),
    ("Saudi Arabia", "SA"), ("Egypt", "EG"), ("United States", "US"),
    ("United Kingdom", "GB"), ("Germany", "DE"),
]

# The 11 skills of the first seed (sql/cverge_schema.sql, migration 5f8a2c41d9e7).
ORIGINAL_SKILLS: list[str] = [
    "React", "Node.js", "Python", "JavaScript", "TypeScript",
    "PostgreSQL", "MySQL", "Docker", "Java", "C#", "Git",
]

ORIGINAL_SKILL_ALIASES: dict[str, str] = {
    "reactjs": "React", "react.js": "React",
    "node": "Node.js", "nodejs": "Node.js",
    "js": "JavaScript", "ts": "TypeScript",
    "postgres": "PostgreSQL", "psql": "PostgreSQL",
    "mysql8": "MySQL",
}

# Added by migration 3c7f1a9e5b42, grouped for readability.
ADDED_SKILLS: dict[str, list[str]] = {
    "programming": [
        "C", "C++", "Go", "PHP", "Ruby", "Kotlin", "Swift", "R", "SQL", "HTML", "CSS", "Bash",
    ],
    "frameworks": [
        "React Native", "Angular", "Vue.js", "Next.js", "Express", "Django", "Flask",
        "FastAPI", "Spring Boot", ".NET", "Laravel",
    ],
    "data": [
        "MongoDB", "SQL Server", "Oracle Database", "Redis", "Pandas", "NumPy", "scikit-learn",
        "TensorFlow", "PyTorch", "Power BI", "Tableau", "Microsoft Excel", "DAX", "SPSS",
        "Data Analysis", "Data Engineering", "Data Visualization", "Machine Learning",
        "Artificial Intelligence", "Deep Learning", "Statistics", "ETL",
    ],
    "devops_cloud": [
        "Kubernetes", "GitHub", "Linux", "AWS", "Microsoft Azure", "Google Cloud", "CI/CD",
        "REST APIs",
    ],
    "office_tools": [
        "Microsoft Office", "Microsoft Word", "Microsoft PowerPoint", "Microsoft Access",
        "Google Analytics", "Slack", "Zoom", "Jira", "Windows", "macOS",
    ],
    "design_media": [
        "Adobe Photoshop", "Adobe Illustrator", "Adobe Premiere Pro", "Adobe After Effects",
        "Final Cut Pro", "Avid Media Composer", "Figma", "Video Editing",
    ],
    "business": [
        "Marketing", "Digital Marketing", "Sales", "Customer Service", "Project Management",
        "Agile", "Scrum", "Public Relations", "Fundraising",
    ],
    "soft_skills": [
        "Communication", "Teamwork", "Leadership", "Problem Solving", "Critical Thinking",
        "Time Management", "Conflict Resolution", "Active Listening", "Organization",
    ],
}

ADDED_SKILL_ALIASES: dict[str, str] = {
    # programming / frameworks
    "golang": "Go", "c plus plus": "C++", "cpp": "C++", "vue": "Vue.js",
    "express.js": "Express", "expressjs": "Express", "dotnet": ".NET", "asp.net": ".NET",
    "html5": "HTML", "css3": "CSS", "shell scripting": "Bash",
    # data
    "mongo": "MongoDB", "mssql": "SQL Server", "microsoft sql server": "SQL Server",
    "oracle": "Oracle Database", "sklearn": "scikit-learn", "microsoft power bi": "Power BI",
    "excel": "Microsoft Excel", "ms excel": "Microsoft Excel", "spss statistics": "SPSS",
    "ibm spss": "SPSS", "ibm spss statistics": "SPSS", "data analytics": "Data Analysis",
    "ml": "Machine Learning", "ai": "Artificial Intelligence", "dl": "Deep Learning",
    # devops / cloud
    "k8s": "Kubernetes", "amazon web services": "AWS", "azure": "Microsoft Azure",
    "gcp": "Google Cloud", "google cloud platform": "Google Cloud", "rest": "REST APIs",
    "rest api": "REST APIs", "restful apis": "REST APIs", "continuous integration": "CI/CD",
    # office
    "ms office": "Microsoft Office", "microsoft office suite": "Microsoft Office",
    "office 365": "Microsoft Office", "microsoft 365": "Microsoft Office",
    "ms word": "Microsoft Word", "powerpoint": "Microsoft PowerPoint",
    "ms powerpoint": "Microsoft PowerPoint", "ms access": "Microsoft Access",
    "mac os": "macOS", "mac os x": "macOS", "os x": "macOS", "osx": "macOS",
    "microsoft windows": "Windows",
    # design / media
    "photoshop": "Adobe Photoshop", "illustrator": "Adobe Illustrator",
    "premiere": "Adobe Premiere Pro", "premiere pro": "Adobe Premiere Pro",
    "adobe premiere": "Adobe Premiere Pro", "after effects": "Adobe After Effects",
    "final cut": "Final Cut Pro", "fcp": "Final Cut Pro", "avid": "Avid Media Composer",
    "media composer": "Avid Media Composer",
    # business / soft skills
    "customer care": "Customer Service", "pr": "Public Relations",
    "team work": "Teamwork", "team player": "Teamwork", "team leadership": "Leadership",
    "organisation": "Organization", "organizational skills": "Organization",
    "organisational skills": "Organization", "time-management": "Time Management",
}

# More soft skills, added by migration 4e2b8d6f1a73.
MORE_SOFT_SKILLS: list[str] = [
    "Attention to Detail", "Adaptability", "Creativity", "Decision Making",
    "Emotional Intelligence", "Interpersonal Skills", "Negotiation", "Presentation Skills",
    "Multitasking", "Work Ethic", "Analytical Thinking", "Strategic Thinking",
    "Self-Motivation", "Working Under Pressure", "Mentoring", "Empathy", "Accountability",
    "Initiative", "Punctuality", "Delegation", "Cultural Awareness",
]

# Common ways CVs write soft skills. A trailing "skills"/"abilities" is
# already ignored by the match key ("communication skills" = Communication).
MORE_SOFT_SKILL_ALIASES: dict[str, str] = {
    # existing soft skills
    "excellent communication": "Communication", "strong communication": "Communication",
    "effective communication": "Communication", "good communication": "Communication",
    "communicator": "Communication",
    "collaboration": "Teamwork", "collaborative": "Teamwork",
    "teamwork and collaboration": "Teamwork", "team working": "Teamwork",
    "strong leadership": "Leadership", "people management": "Leadership",
    "problem solver": "Problem Solving", "troubleshooting": "Problem Solving",
    "critical thinker": "Critical Thinking",
    "time management and organization": "Time Management", "prioritization": "Time Management",
    "prioritisation": "Time Management",
    "conflict management": "Conflict Resolution", "dispute resolution": "Conflict Resolution",
    "listening": "Active Listening",
    "organized": "Organization", "organised": "Organization", "well organized": "Organization",
    "well organised": "Organization", "highly organized": "Organization",
    "highly organised": "Organization", "extremely organized": "Organization",
    "extremely organised": "Organization",
    # new soft skills
    "detail oriented": "Attention to Detail", "attention to details": "Attention to Detail",
    "eye for detail": "Attention to Detail",
    "flexibility": "Adaptability", "flexible": "Adaptability", "adaptable": "Adaptability",
    "creative thinking": "Creativity", "creative": "Creativity",
    "decisive": "Decision Making",
    "eq": "Emotional Intelligence",
    "people skills": "Interpersonal Skills", "relationship building": "Interpersonal Skills",
    "negotiating": "Negotiation",
    "public speaking": "Presentation Skills", "presenting": "Presentation Skills",
    "presentations": "Presentation Skills",
    "multitasker": "Multitasking",
    "strong work ethic": "Work Ethic", "hard working": "Work Ethic", "hardworking": "Work Ethic",
    "analytical": "Analytical Thinking", "analytical thinker": "Analytical Thinking",
    "self motivated": "Self-Motivation", "self starter": "Self-Motivation",
    "ability to work under pressure": "Working Under Pressure",
    "works well under pressure": "Working Under Pressure",
    "performing under pressure": "Working Under Pressure",
    "stress management": "Working Under Pressure",
    "coaching": "Mentoring", "mentorship": "Mentoring",
    "punctual": "Punctuality",
    "responsibility": "Accountability",
    "proactive": "Initiative", "proactivity": "Initiative",
    "cultural sensitivity": "Cultural Awareness",
    "cross cultural communication": "Cultural Awareness",
}

SEED_SKILLS: list[str] = (ORIGINAL_SKILLS + [s for group in ADDED_SKILLS.values() for s in group]
                          + MORE_SOFT_SKILLS)
SEED_SKILL_ALIASES: dict[str, str] = {**ORIGINAL_SKILL_ALIASES, **ADDED_SKILL_ALIASES,
                                      **MORE_SOFT_SKILL_ALIASES}


def seed_country_catalog() -> CountryCatalog:
    return CountryCatalog(SEED_COUNTRIES)


def seed_skill_catalog() -> SkillCatalog:
    return SkillCatalog(SEED_SKILLS, SEED_SKILL_ALIASES)
