"""Tests de la configuration sensible au déploiement derrière un reverse-proxy."""

import importlib
from unittest import mock

from config import settings


def test_csrf_trusted_origins_empty_by_default():
    with mock.patch.dict("os.environ", {"DJANGO_CSRF_TRUSTED_ORIGINS": ""}):
        importlib.reload(settings)
    assert settings.CSRF_TRUSTED_ORIGINS == []
    importlib.reload(settings)


def test_csrf_trusted_origins_parses_comma_separated_env_var():
    env = {
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://studymed.example.com,https://autre.example.com"
    }
    with mock.patch.dict("os.environ", env):
        importlib.reload(settings)
    assert settings.CSRF_TRUSTED_ORIGINS == [
        "https://studymed.example.com",
        "https://autre.example.com",
    ]
    importlib.reload(settings)


def test_secure_proxy_ssl_header_trusts_x_forwarded_proto():
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
