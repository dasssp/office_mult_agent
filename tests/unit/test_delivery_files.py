from pathlib import Path


def test_delivery_files_include_container_and_ci_contracts() -> None:
    root = Path(__file__).parents[2]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    workflow = (root / ".gitlab-ci.yml").read_text(encoding="utf-8")
    assert "USER app" in dockerfile
    assert "alembic upgrade head" in dockerfile
    assert "postgres:" in compose and "redis:" in compose and "app:" in compose
    assert "python -m pytest -q" in workflow
    assert "postgres-recovery:" in workflow
    assert "redis-cache:" in workflow
