"""Tests d'infrastructure pour le déploiement Docker (issue #59, phase 1)."""

import os
from pathlib import Path

import pytest
import yaml


BASE_DIR = Path(__file__).resolve().parent.parent


def test_dockerfile_exists_and_is_multistage():
    dockerfile = BASE_DIR / "Dockerfile"
    assert dockerfile.exists()
    content = dockerfile.read_text()
    assert content.count("FROM") >= 2
    assert "AS builder" in content
    assert "AS runtime" in content


def test_dockerfile_uses_non_root_user():
    content = (BASE_DIR / "Dockerfile").read_text()
    assert "useradd" in content
    entrypoint = (BASE_DIR / "entrypoint.sh").read_text()
    assert "gosu app" in entrypoint


def test_entrypoint_exists_and_is_executable():
    entrypoint = BASE_DIR / "entrypoint.sh"
    assert entrypoint.exists()
    assert os.access(entrypoint, os.X_OK)
    content = entrypoint.read_text()
    assert "migrate" in content
    assert "collectstatic" in content


@pytest.fixture
def compose_config():
    compose_file = BASE_DIR / "docker-compose.yml"
    assert compose_file.exists()
    with compose_file.open() as f:
        return yaml.safe_load(f)


def test_compose_has_expected_services(compose_config):
    services = compose_config["services"]
    assert "db" in services
    assert "web" in services
    assert "nginx" in services


def test_compose_web_references_published_ghcr_image(compose_config):
    web = compose_config["services"]["web"]
    assert web["image"].startswith("ghcr.io/")
    assert "build" not in web


def test_compose_web_depends_on_healthy_db(compose_config):
    web = compose_config["services"]["web"]
    assert web["depends_on"]["db"]["condition"] == "service_healthy"


def test_compose_db_has_volume_and_healthcheck(compose_config):
    db = compose_config["services"]["db"]
    assert "healthcheck" in db
    assert any("data/postgres" in v for v in db.get("volumes", []))


def test_compose_web_shares_media_and_static_volumes(compose_config):
    web_volumes = compose_config["services"]["web"].get("volumes", [])
    nginx_volumes = compose_config["services"]["nginx"].get("volumes", [])
    assert any("media" in v for v in web_volumes)
    assert any("static" in v for v in web_volumes)
    assert any("media" in v for v in nginx_volumes)
    assert any("static" in v for v in nginx_volumes)


def test_compose_web_has_import_init_mount(compose_config):
    web_volumes = compose_config["services"]["web"].get("volumes", [])
    assert any("import_init:/app/import_init" in v for v in web_volumes)


def test_dockerignore_excludes_dev_artifacts():
    dockerignore = (BASE_DIR / ".dockerignore").read_text()
    for entry in [".venv", ".git", "tests", "notebooks", "docs", "db.sqlite3"]:
        assert entry in dockerignore


def test_env_example_documents_required_variables():
    content = (BASE_DIR / ".env.example").read_text()
    for var in [
        "DJANGO_SECRET_KEY",
        "DJANGO_DEBUG",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "NGINX_PORT",
        "STORAGE_DIR",
    ]:
        assert var in content


def test_gunicorn_is_a_project_dependency():
    import tomllib

    with (BASE_DIR / "pyproject.toml").open("rb") as f:
        pyproject = tomllib.load(f)
    assert "gunicorn" in pyproject["project"]["dependencies"]


def test_nginx_conf_proxies_to_web():
    nginx_conf = (BASE_DIR / "conf" / "nginx.conf").read_text()
    assert "proxy_pass" in nginx_conf
    assert "web:8000" in nginx_conf


def test_nginx_conf_relays_forwarded_proto_instead_of_hardcoding():
    nginx_conf = (BASE_DIR / "conf" / "nginx.conf").read_text()
    assert "proxy_set_header X-Forwarded-Proto https;" not in nginx_conf
    assert "$http_x_forwarded_proto" in nginx_conf
    assert "$scheme" in nginx_conf


def test_nginx_conf_preserves_port_in_host_header():
    nginx_conf = (BASE_DIR / "conf" / "nginx.conf").read_text()
    assert "proxy_set_header Host $host;" not in nginx_conf
    assert "proxy_set_header Host $http_host;" in nginx_conf


def test_ci_publishes_image_to_ghcr():
    workflow = BASE_DIR / ".github" / "workflows" / "docker-publish.yml"
    assert workflow.exists()
    with workflow.open() as f:
        config = yaml.safe_load(f)
    assert "ghcr.io" in str(config)


def test_compose_web_has_watchtower_label(compose_config):
    web = compose_config["services"]["web"]
    labels = web.get("labels", [])
    assert any(
        "com.centurylinklabs.watchtower.enable=true" in str(label) for label in labels
    )
