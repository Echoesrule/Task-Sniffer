"""Static regression tests for deployment and frontend security defaults."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_does_not_publish_database_or_redis_ports():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]

    assert "ports" not in services["db"]
    assert "ports" not in services["redis"]
    assert services["api"]["ports"] == ["8000:8000"]


def test_compose_requires_redis_authentication_and_private_network_url():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]

    command = services["redis"]["command"]
    assert "--requirepass" in command
    assert "${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}" in command
    assert "REDIS_PASSWORD" in services["redis"]["environment"]

    for service in ("api", "worker", "beat"):
        redis_url = services[service]["environment"]["REDIS_URL"]
        assert redis_url.startswith("redis://:")
        assert "@redis:6379/0" in redis_url


def test_compose_applies_no_new_privileges_and_no_source_bind_mounts():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]

    for service in ("db", "redis", "api", "worker", "beat"):
        assert "no-new-privileges:true" in services[service]["security_opt"]

    for service in ("api", "worker", "beat"):
        volumes = services[service].get("volumes", [])
        assert not any(str(volume).startswith("./backend") for volume in volumes)


def test_runtime_image_is_multistage_nonroot_and_without_build_tools():
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "AS builder" in dockerfile
    assert "AS runtime" in dockerfile
    runtime = dockerfile.split("AS runtime", 1)[1]
    assert "build-essential" not in runtime
    assert "apt-get install" not in runtime
    assert "USER app" in runtime
    assert "HEALTHCHECK" in runtime


def test_env_example_does_not_contain_secret_values():
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value

    for key in (
        "SECRET_KEY",
        "ENCRYPTION_KEY",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "TELEGRAM_BOT_TOKEN",
        "OPENAI_API_KEY",
    ):
        assert values.get(key) == "", f"{key} must not ship with a value"


def test_frontend_does_not_store_credentials_in_web_storage():
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        source = path.read_text()
        assert "localStorage" not in source, f"localStorage used in {path}"
        assert "sessionStorage" not in source, f"sessionStorage used in {path}"


def test_frontend_has_no_raw_html_sinks_or_eval():
    for path in (ROOT / "frontend" / "src").rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        source = path.read_text()
        assert "dangerouslySetInnerHTML" not in source, f"raw HTML sink in {path}"
        assert "innerHTML" not in source, f"innerHTML sink in {path}"
        assert "eval(" not in source, f"eval sink in {path}"
