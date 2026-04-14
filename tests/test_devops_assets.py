"""Static verification tests for devops and monitoring assets."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_multistage_build():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "AS builder" in dockerfile
    assert "AS runtime" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile


def test_compose_includes_monitoring_profile_services():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "prometheus:" in compose
    assert "grafana:" in compose
    assert 'profiles: ["monitoring"]' in compose
    assert "/api/health" in compose


def test_makefile_contains_expected_dx_targets():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in [
        "run:",
        "test:",
        "lint:",
        "format:",
        "typecheck:",
        "seed:",
        "coverage:",
        "stress:",
        "migrate-upgrade:",
        "docker-up-prod-monitoring:",
    ]:
        assert target in makefile


def test_alembic_initial_revision_exists():
    versions_dir = ROOT / "migrations" / "versions"
    revisions = list(versions_dir.glob("*_initial_schema.py"))
    assert revisions
