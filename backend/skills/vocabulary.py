"""Canonical skills vocabulary: the single source of truth for skill identity.

This replaces the three divergent alias tables that previously lived in
``services/normalizer.py`` (``TECH_SKILL_MAP``), ``scrapers/base.py``
(``detect_skills``) and ``matching/engine.py`` (``SKILL_ALIASES``).

Every skill has a stable canonical ``id``, a human ``display`` name, a
``category`` and a set of literal ``aliases``.  Aliases that are also common
English words, or that collide with unrelated skills, are listed under
``ambiguous`` and are only matched when corroborating context appears nearby.
That keeps extraction precise without losing recall for the unabbreviated form.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    """A single canonical skill and the surface forms that map to it."""

    id: str
    display: str
    category: str
    aliases: tuple[str, ...] = ()
    #: alias -> tuple of context regexes; alias matches only if one appears in
    #: the surrounding window.  Used for tokens that are also common words.
    ambiguous: tuple[tuple[str, tuple[str, ...]], ...] = ()


def _s(
    id: str,
    display: str,
    category: str,
    aliases: tuple[str, ...] = (),
    ambiguous: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> Skill:
    return Skill(id, display, category, aliases, ambiguous)


# ---------------------------------------------------------------------------
# Context fragments reused by several ambiguous aliases.
# ---------------------------------------------------------------------------

_LANG_CONTEXT = (
    r"\bgolang\b",
    r"\b(?:in|with|using|write|writes|writing|written in|code in|coding in|"
    r"experience (?:in|with)|proficien\w+ in|skilled in|expertise in)\s+go\b",
    r"\bgo\s+(?:language|programming|developer|engineer|microservices?|"
    r"backend|modules?|routines?|code|concurrency)\b",
)

_TS_CONTEXT = (
    r"\btypescript\b",
    r"\bts\s*/\s*js\b",
    r"\breact(?:js)?\b|\bnode\.?js\b|\bnext\.?js\b|\bvue\b|\bangular\b",
)

_JS_CONTEXT = (
    r"\bjavascript\b",
    r"\bnode\.?js\b",
    r"\breact(?:js)?\b|\bvue(?:js)?\b|\bangular\b|\bnext\.?js\b|\bexpress\b",
    r"\bjs\b\s*[,/+&]",
)

_CV_CONTEXT = (
    r"\bcomputer vision\b",
    r"\bopencv\b|\bimage (?:processing|recognition|classification)\b",
    r"\bobject detection\b|\bfacial recognition\b",
)

_ML_CONTEXT = (
    r"\bmachine learning\b",
    r"\bml\s+(?:models?|engineer|pipeline|algorithms?|research|team|ops|tooling|framework)\b",
    r"\b(?:deep|supervised|unsupervised|reinforcement)\s+learning\b",
)

_DL_CONTEXT = (
    r"\bdeep learning\b",
    r"\bneural networks?\b",
    r"\bdl\s+(?:models?|frameworks?|engineer)\b",
)

_AI_CONTEXT = (
    r"\bartificial intelligence\b",
    r"\bai\s+(?:models?|engineer|systems?|research|products?|platform|tools?|ml|solution)\b",
    r"\bgenerative ai\b|\bapplied ai\b",
)

_REST_CONTEXT = (
    r"\brest(?:ful)?\s+api\b",
    r"\brest\b\s*(?:api|apis|ful)",
    r"\bapi\b",
)

_WS_CONTEXT = (
    r"\bwebsockets?\b",
    r"\breal-?time\b",
    r"\bws\b\s*(?:/|,|\+|&)",
)

_LAMBDA_CONTEXT = (
    r"\baws\b|\bamazon web services\b",
    r"\bserverless\b|\baws lambda\b|\blambda functions?\b",
)

_SPARK_CONTEXT = (
    r"\bapache spark\b",
    r"\bspark\s+(?:jobs?|cluster|sql|streaming|dataframe|engine)\b",
    r"\bpyspark\b",
)

_ORACLE_CONTEXT = (
    r"\boracle (?:db|database|sql|fusion|cloud|apex|plsql)\b",
    r"\bpl/?sql\b",
    r"\boracle\s*,",
)

_EXCEL_CONTEXT = (
    r"\bmicrosoft excel\b|\bms excel\b",
    r"\bexcel\s+(?:spreadsheets?|formulas?|macros?|models?|reports?|pivot)\b",
    r"\badvanced excel\b|\bexcel (?:and|&)\b",
)

_GO_CONTEXT = _LANG_CONTEXT


# ---------------------------------------------------------------------------
# The registry.  Canonical ids are stable; rename only with a migration.
# ---------------------------------------------------------------------------

SKILLS: tuple[Skill, ...] = (
    # --- programming languages -------------------------------------------
    _s("python", "Python", "language", ("python", "python3", "python2", "py3", "cpython", "pypy")),
    _s("javascript", "JavaScript", "language", ("javascript", "ecmascript", "es6", "es2015", "es2020"), (("js", _JS_CONTEXT),)),
    _s("typescript", "TypeScript", "language", ("typescript",), (("ts", _TS_CONTEXT),)),
    _s("java", "Java", "language", ("java", "java se", "java ee", "jdk")),
    _s("c++", "C++", "language", ("c++", "cpp", "c plus plus")),
    _s("c#", "C#", "language", ("c#", "csharp", "c sharp")),
    _s("c", "C", "language", (), (("c", (r"\bc (?:language|programming)\b", r"\bembedded c\b", r"\bc/c\+\+")),)),
    _s("go", "Go", "language", ("golang",), (("go", _GO_CONTEXT),)),
    _s("rust", "Rust", "language", ("rust", "rust-lang")),
    _s("ruby", "Ruby", "language", ("ruby",)),
    _s("php", "PHP", "language", ("php",)),
    _s("swift", "Swift", "language", ("swift", "swiftui")),
    _s("kotlin", "Kotlin", "language", ("kotlin",)),
    _s("scala", "Scala", "language", ("scala",)),
    _s("r", "R", "language", ("r language", "r programming", "rstudio", "r studio"), (("r", (r"\br (?:programming|language|studio)\b", r"\brstudio\b", r"\bcran\b")),)),
    _s("dart", "Dart", "language", ("dart",)),
    _s("lua", "Lua", "language", ("lua",)),
    _s("elixir", "Elixir", "language", ("elixir",)),
    _s("haskell", "Haskell", "language", ("haskell",)),
    _s("perl", "Perl", "language", ("perl",)),
    _s("matlab", "MATLAB", "language", ("matlab",)),
    _s("bash", "Bash", "language", ("bash", "shell scripting", "shell script")),

    # --- frontend ---------------------------------------------------------
    _s("react", "React", "frontend", ("react", "reactjs", "react.js")),
    _s("react native", "React Native", "mobile", ("react native",)),
    _s("vue", "Vue.js", "frontend", ("vue", "vuejs", "vue.js")),
    _s("angular", "Angular", "frontend", ("angular", "angularjs", "angular.js")),
    _s("svelte", "Svelte", "frontend", ("svelte", "sveltekit")),
    _s("next.js", "Next.js", "frontend", ("nextjs", "next.js", "next js")),
    _s("node.js", "Node.js", "backend", ("nodejs", "node.js", "node js")),
    _s("express", "Express", "backend", ("expressjs", "express.js"), (("express", (r"\bnode\.?js\b", r"\bjavascript\b", r"\bexpress (?:framework|server|api|apps?)\b")),)),
    _s("jquery", "jQuery", "frontend", ("jquery",)),
    _s("redux", "Redux", "frontend", ("redux",)),
    _s("webpack", "Webpack", "frontend", ("webpack",)),
    _s("html", "HTML", "frontend", ("html", "html5")),
    _s("css", "CSS", "frontend", ("css", "css3")),
    _s("tailwind", "Tailwind CSS", "frontend", ("tailwind", "tailwindcss", "tailwind css")),
    _s("sass", "Sass/SCSS", "frontend", ("sass", "scss")),
    _s("bootstrap", "Bootstrap", "frontend", ("bootstrap",)),

    # --- backend / frameworks --------------------------------------------
    _s("django", "Django", "backend", ("django",)),
    _s("flask", "Flask", "backend", ("flask",)),
    _s("fastapi", "FastAPI", "backend", ("fastapi", "fast api")),
    _s("spring", "Spring", "backend", ("spring", "spring boot", "springboot")),
    _s("laravel", "Laravel", "backend", ("laravel",)),
    _s("rails", "Ruby on Rails", "backend", ("rails", "ruby on rails", "ror")),
    _s("dotnet", ".NET", "backend", (".net", "dotnet", "asp.net", "asp .net")),
    _s("nestjs", "NestJS", "backend", ("nestjs", "nest.js")),
    _s("graphql", "GraphQL", "backend", ("graphql", "gql")),
    _s("rest api", "REST APIs", "backend", ("rest api", "restful api", "rest apis", "api development"), (("rest", _REST_CONTEXT),)),
    _s("grpc", "gRPC", "backend", ("grpc", "protobuf", "protocol buffers")),
    _s("websockets", "WebSockets", "backend", ("websockets", "websocket"), (("ws", _WS_CONTEXT),)),

    # --- mobile -----------------------------------------------------------
    _s("flutter", "Flutter", "mobile", ("flutter",)),
    _s("android", "Android", "mobile", ("android",)),
    _s("ios", "iOS", "mobile", ("ios",)),

    # --- databases --------------------------------------------------------
    _s("postgresql", "PostgreSQL", "database", ("postgresql", "postgres", "psql")),
    _s("mysql", "MySQL", "database", ("mysql", "mariadb")),
    _s("mongodb", "MongoDB", "database", ("mongodb", "mongo")),
    _s("redis", "Redis", "database", ("redis",)),
    _s("sqlite", "SQLite", "database", ("sqlite", "sqlite3")),
    _s("elasticsearch", "Elasticsearch", "database", ("elasticsearch", "elastic", "opensearch")),
    _s("dynamodb", "DynamoDB", "database", ("dynamodb", "dynamo db")),
    _s("cassandra", "Cassandra", "database", ("cassandra",)),
    _s("sql server", "SQL Server", "database", ("sql server", "mssql", "t-sql", "tsql")),
    _s("oracle", "Oracle DB", "database", ("oracle database", "oracle db"), (("oracle", _ORACLE_CONTEXT),)),
    _s("bigquery", "BigQuery", "database", ("bigquery", "big query")),
    _s("snowflake", "Snowflake", "database", ("snowflake",)),
    _s("firebase", "Firebase", "database", ("firebase",)),
    _s("supabase", "Supabase", "database", ("supabase",)),
    _s("sql", "SQL", "database", ("sql",)),

    # --- cloud / devops ---------------------------------------------------
    _s("aws", "AWS", "cloud", ("aws", "amazon web services", "ec2", "s3", "sqs", "sns"), (("lambda", _LAMBDA_CONTEXT),)),
    _s("gcp", "Google Cloud", "cloud", ("gcp", "google cloud", "google cloud platform")),
    _s("azure", "Azure", "cloud", ("azure", "microsoft azure", "azure devops")),
    _s("docker", "Docker", "devops", ("docker", "containerization", "containers")),
    _s("kubernetes", "Kubernetes", "devops", ("kubernetes", "k8s")),
    _s("terraform", "Terraform", "devops", ("terraform",)),
    _s("ansible", "Ansible", "devops", ("ansible",)),
    _s("jenkins", "Jenkins", "devops", ("jenkins",)),
    _s("github actions", "GitHub Actions", "devops", ("github actions", "gh actions")),
    _s("gitlab ci", "GitLab CI", "devops", ("gitlab ci", "gitlab-ci")),
    _s("circleci", "CircleCI", "devops", ("circleci", "circle ci")),
    _s("ci/cd", "CI/CD", "devops", ("ci/cd", "ci cd", "continuous integration", "continuous deployment")),
    _s("git", "Git", "devops", ("git", "github", "gitlab", "bitbucket", "version control")),
    _s("linux", "Linux", "devops", ("linux", "ubuntu", "debian", "centos", "alpine")),
    _s("nginx", "Nginx", "devops", ("nginx",)),
    _s("apache", "Apache", "devops", ("apache httpd", "apache server"), (("apache", (r"\bapache (?:httpd|server|web server|tomcat)\b",)),)),
    _s("rabbitmq", "RabbitMQ", "devops", ("rabbitmq", "rabbit mq")),
    _s("kafka", "Kafka", "devops", ("kafka", "apache kafka")),
    _s("prometheus", "Prometheus", "devops", ("prometheus",)),
    _s("grafana", "Grafana", "devops", ("grafana",)),
    _s("serverless", "Serverless", "cloud", ("serverless",)),

    # --- data / ML --------------------------------------------------------
    _s("machine learning", "Machine Learning", "data", ("machine learning",), (("ml", _ML_CONTEXT),)),
    _s("deep learning", "Deep Learning", "data", ("deep learning",), (("dl", _DL_CONTEXT),)),
    _s("artificial intelligence", "Artificial Intelligence", "data", ("artificial intelligence",), (("ai", _AI_CONTEXT),)),
    _s("data science", "Data Science", "data", ("data science", "data scientist")),
    _s("nlp", "NLP", "data", ("nlp", "natural language processing")),
    _s("computer vision", "Computer Vision", "data", ("computer vision",), (("cv", _CV_CONTEXT),)),
    _s("pandas", "pandas", "data", ("pandas",)),
    _s("numpy", "NumPy", "data", ("numpy",)),
    _s("scikit-learn", "scikit-learn", "data", ("scikit-learn", "sklearn", "scikit learn")),
    _s("pytorch", "PyTorch", "data", ("pytorch",)),
    _s("tensorflow", "TensorFlow", "data", ("tensorflow",)),
    _s("keras", "Keras", "data", ("keras",)),
    _s("hugging face", "Hugging Face", "data", ("hugging face", "huggingface")),
    _s("spark", "Apache Spark", "data", ("apache spark", "pyspark"), (("spark", _SPARK_CONTEXT),)),
    _s("hadoop", "Hadoop", "data", ("hadoop",)),
    _s("airflow", "Airflow", "data", ("airflow",)),
    _s("etl", "ETL", "data", ("etl", "elt")),
    _s("power bi", "Power BI", "data", ("power bi", "powerbi")),
    _s("tableau", "Tableau", "data", ("tableau",)),
    _s("excel", "Excel", "data", ("microsoft excel", "ms excel"), (("excel", _EXCEL_CONTEXT),)),
    _s("statistics", "Statistics", "data", ("statistics", "statistical analysis")),

    # --- testing / QA -----------------------------------------------------
    _s("selenium", "Selenium", "qa", ("selenium",)),
    _s("cypress", "Cypress", "qa", ("cypress",)),
    _s("playwright", "Playwright", "qa", ("playwright",)),
    _s("pytest", "pytest", "qa", ("pytest",)),
    _s("junit", "JUnit", "qa", ("junit",)),
    _s("jest", "Jest", "qa", ("jest",)),
    _s("postman", "Postman", "qa", ("postman",)),

    # --- design -----------------------------------------------------------
    _s("figma", "Figma", "design", ("figma",)),
    _s("adobe xd", "Adobe XD", "design", ("adobe xd",)),
    _s("sketch", "Sketch", "design", ("sketch",)),
    _s("photoshop", "Photoshop", "design", ("photoshop",)),
    _s("illustrator", "Illustrator", "design", ("illustrator",)),

    # --- process / business ----------------------------------------------
    _s("jira", "Jira", "process", ("jira",)),
    _s("confluence", "Confluence", "process", ("confluence",)),
    _s("agile", "Agile", "process", ("agile", "scrum", "kanban")),
    _s("salesforce", "Salesforce", "business", ("salesforce", "sfdc")),
    _s("sap", "SAP", "business", ("sap",)),
    _s("blockchain", "Blockchain", "business", ("blockchain", "web3", "smart contracts")),
    _s("solidity", "Solidity", "language", ("solidity",)),
    _s("cybersecurity", "Cybersecurity", "security", ("cybersecurity", "infosec", "information security", "penetration testing", "pentesting")),
)


# ---------------------------------------------------------------------------
# Derived indexes
# ---------------------------------------------------------------------------

SKILL_BY_ID: dict[str, Skill] = {s.id: s for s in SKILLS}

#: alias (lowercase) -> canonical id.  Includes ambiguous aliases because an
#: explicitly supplied skill list is intentional, not free text.
ALIAS_TO_CANONICAL: dict[str, str] = {}
for _skill in SKILLS:
    for _alias in _skill.aliases:
        ALIAS_TO_CANONICAL.setdefault(_alias.lower(), _skill.id)
    for _alias, _ctx in _skill.ambiguous:
        ALIAS_TO_CANONICAL.setdefault(_alias.lower(), _skill.id)

CANONICAL_IDS: frozenset[str] = frozenset(SKILL_BY_ID)

#: Backwards-compatible view of the old ``TECH_SKILL_MAP`` structure
#: (canonical -> list of aliases), for any external import of that name.
TECH_SKILL_MAP: dict[str, list[str]] = {
    s.id: ([*s.aliases, *(a for a, _ in s.ambiguous)]) for s in SKILLS
}


def normalize_skill(term: str) -> str | None:
    """Return the canonical id for a single skill term, or ``None``."""
    if not term:
        return None
    key = term.strip().lower()
    if not key:
        return None
    if key in CANONICAL_IDS:
        return key
    return ALIAS_TO_CANONICAL.get(key)


def normalize_skill_list(terms: object) -> list[str]:
    """Canonicalize an arbitrary list (or comma string) of skill terms.

    Unknown terms are preserved, lowercased, so recall is never reduced by an
    incomplete vocabulary.
    """
    if isinstance(terms, str):
        terms = [t.strip() for t in terms.split(",")]
    if not isinstance(terms, (list, tuple, set)):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not isinstance(term, str):
            term = str(term)
        canonical = normalize_skill(term)
        value = canonical or term.strip().lower()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return sorted(out)
