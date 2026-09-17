"""The configuration gates, which until Phase 1 gated nothing.

`_required_in_deployed_envs` was declared as a validator over the three secrets,
documented as *"strict everywhere else"*, and had the body `return v`. It
enforced nothing while presenting as a security control, which is worse than its
absence: absence is visible.

Two failures came out of that, and they compound. `env` defaulted to `local`,
and `is_local` also answered true for `ci` — so a deployment that simply forgot
`NEXUS_ENV` served `/docs` and `/openapi.json` publicly and set `secure=False`
on both the session and the CSRF cookie, over the internet, on a product holding
company financials. Nothing failed. Nothing logged.

`_env_file=None` appears throughout. `Settings` reads the repository's `.env`,
which supplies `NEXUS_ENV=local`, so a test that merely unsets the variable is
not testing a missing variable — it is testing the fallback. Production has no
`.env`, and that is the case worth proving.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import Response
from pydantic import SecretStr, ValidationError

from app.config import REPO_ROOT, Env, Settings, get_settings
from app.main import create_app
from app.routes.auth import _set_session_cookie

DEPLOYED = (Env.staging, Env.production)
UNDEPLOYED = (Env.local, Env.ci)


# What a deployed environment must supply beyond its two secrets, since P3.
# Kept in one place so a test about cookies does not have to know about SMTP —
# it only has to be *deployable*, which keeps growing. Renamed from
# `DEPLOYABLE_EMAIL` once it held a database role and an encryption key: a name
# that describes a third of its contents sends the next person looking for the
# other two somewhere else.
DEPLOYABLE: dict[str, object] = {
    "mailer_backend": "smtp",
    "smtp_host": "smtp.example.invalid",
    "public_base_url": "https://app.example.invalid",
    # ADR 0018. "Deployable" grew again: a deployed environment must have the
    # maintenance role, or the expiry sweep matches zero rows and says nothing.
    "jobs_database_url": SecretStr("postgresql+asyncpg://nexus_jobs:p@h:5432/nexus"),
    # ADR 0032 / D27. Deployable grew again: a deployed environment must be able
    # to seal a provider's refresh token, or it accepts an OAuth callback it
    # cannot store and fails on the first sweep instead of at boot.
    "connector_secret_key": SecretStr(Fernet.generate_key().decode()),
}


def _settings(**overrides: object) -> Settings:
    """Settings built from the overrides alone, with no `.env` underneath.

    A deployed `env` gets `DEPLOYABLE` folded in unless the caller
    overrides it, because P3 made "deployed" mean "can actually send email" —
    a staging environment left on the file backend writes every verification to
    a directory nobody reads. Tests about cookies and `/docs` should not have to
    restate that, and a test that *is* about it passes its own values.
    """
    if overrides.get("env") in DEPLOYED:
        overrides = {**DEPLOYABLE, **overrides}
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


# ── A deployed environment must have its secrets ──────────────


@pytest.mark.parametrize("env", DEPLOYED)
def test_config_refuses_deployed_env_without_secrets(env: Env) -> None:
    """The validator that used to `return v`.

    Both secrets are named in one error rather than one at a time: a deployment
    fixing them one restart at a time is a deployment being told the truth
    slowly.
    """
    with pytest.raises(ValidationError) as raised:
        _settings(
            env=env,
            database_url=SecretStr(""),
            storage_signing_secret=SecretStr(""),
            connector_secret_key=SecretStr(""),
        )

    message = str(raised.value)
    assert "NEXUS_DATABASE_URL" in message
    assert "NEXUS_STORAGE_SIGNING_SECRET" in message
    # ADR 0032 joined the list, and the point of naming them together holds: a
    # deployment fixing three secrets one restart at a time is a deployment
    # being told the truth slowly.
    assert "NEXUS_CONNECTOR_SECRET_KEY" in message
    assert env.value in message


@pytest.mark.parametrize("env", DEPLOYED)
def test_a_deployed_env_with_its_secrets_is_accepted(env: Env) -> None:
    """The other half. A gate that refuses everything is not a gate."""
    settings = _settings(
        env=env,
        database_url=SecretStr("postgresql+asyncpg://u:p@h:5432/nexus"),
        storage_signing_secret=SecretStr("a-real-secret"),
    )
    assert settings.env is env


@pytest.mark.parametrize("env", UNDEPLOYED)
def test_local_and_ci_still_boot_without_secrets(env: Env) -> None:
    """Deliberately permissive, so the app answers a health check before a
    database exists. That was the original intent; only the enforcement
    everywhere else was missing."""
    assert _settings(env=env).env is env


def test_a_missing_env_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """No default. A forgotten `NEXUS_ENV` must not silently mean `local`.

    The plan offered two fixes — drop `ci` from `is_local`, or make cookie
    security independent of it. Neither addresses the default, which is the
    reason a missing variable produced `secure=False` in the first place. So
    `env` is required, and the error names the variable rather than a downstream
    symptom.

    Both sources have to go for this to mean anything. `_env_file=None` removes
    the repository's `.env`; `delenv` removes the variable `conftest` sets for
    every test. Leaving either in place tests the fallback, which is how a
    version of this test passed against a default it was written to forbid.
    """
    monkeypatch.delenv("NEXUS_ENV", raising=False)

    with pytest.raises(ValidationError) as raised:
        _settings()

    assert "env" in str(raised.value).lower()


# ── Cookies ───────────────────────────────────────────────────


@pytest.mark.parametrize("env", DEPLOYED)
def test_cookies_are_secure_outside_local(env: Env) -> None:
    """Asserted on the header, not on the property that decides it.

    Both cookies. The CSRF cookie is deliberately readable by JavaScript, which
    makes it easy to think of as the unimportant one — but it travels on every
    authenticated request, so over plain HTTP it hands an observer the
    double-submit value and the session cookie together.
    """
    settings = _settings(
        env=env,
        database_url=SecretStr("postgresql+asyncpg://u:p@h:5432/nexus"),
        storage_signing_secret=SecretStr("a-real-secret"),
    )

    response = Response()
    _set_session_cookie(response, "a-session-token", settings)

    headers = response.headers.getlist("set-cookie")
    assert len(headers) == 2, "session and CSRF cookies are both set"
    for header in headers:
        assert "Secure" in header, header
        assert "SameSite=lax" in header, header


@pytest.mark.parametrize("env", UNDEPLOYED)
def test_cookies_are_not_secure_locally(env: Env) -> None:
    """Local development and the test suite are served over plain HTTP.

    `ci` is included on purpose and can only be reached by setting `NEXUS_ENV`
    to it explicitly, which is what makes it safe now that there is no default.
    """
    response = Response()
    _set_session_cookie(response, "a-session-token", _settings(env=env))

    for header in response.headers.getlist("set-cookie"):
        assert "Secure" not in header, header


def test_the_session_cookie_is_not_reachable_from_javascript() -> None:
    """Unchanged by Phase 1, asserted here because the two flags are set
    together and a copy-paste between them would be silent."""
    response = Response()
    _set_session_cookie(response, "a-session-token", _settings(env=Env.local))

    session, csrf = response.headers.getlist("set-cookie")
    assert "HttpOnly" in session
    assert "HttpOnly" not in csrf, "the double-submit value must be readable to be echoed"


# ── The API documentation is a local convenience ──────────────


@pytest.mark.parametrize("env", DEPLOYED)
def test_the_api_docs_are_not_served_outside_local(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/docs` and `/openapi.json` enumerate every endpoint and its schema.

    Previously gated on `is_local`, which answered true for `ci` as well — so a
    deployment with `NEXUS_ENV` unset or mis-set published the whole surface.
    """
    monkeypatch.setenv("NEXUS_ENV", env.value)
    monkeypatch.setenv("NEXUS_DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/nexus")
    monkeypatch.setenv("NEXUS_STORAGE_SIGNING_SECRET", "a-real-secret")
    # This test builds Settings from the environment rather than through
    # `_settings`, so it has to state every deployable requirement itself.
    monkeypatch.setenv("NEXUS_CONNECTOR_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("NEXUS_MAILER_BACKEND", "smtp")
    monkeypatch.setenv("NEXUS_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("NEXUS_PUBLIC_BASE_URL", "https://app.example.invalid")
    monkeypatch.setenv("NEXUS_JOBS_DATABASE_URL", "postgresql+asyncpg://nexus_jobs:p@h:5432/nexus")
    get_settings.cache_clear()
    try:
        app = create_app()
        assert app.docs_url is None
        assert app.openapi_url is None
    finally:
        get_settings.cache_clear()


def test_the_api_docs_are_served_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ENV", Env.local.value)
    get_settings.cache_clear()
    try:
        app = create_app()
        assert app.docs_url == "/docs"
    finally:
        get_settings.cache_clear()


def test_ci_does_not_serve_the_api_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ci` is a test environment, not a developer's machine. Nobody reads
    `/docs` there, and treating it as local is what made a mis-set variable
    publish the surface."""
    monkeypatch.setenv("NEXUS_ENV", Env.ci.value)
    get_settings.cache_clear()
    try:
        assert create_app().docs_url is None
    finally:
        get_settings.cache_clear()


# ── `.env.example` cannot drift from `Settings` ────────────────

# Keys in `.env.example` that are deliberately not `Settings` fields, split by
# why. Both need a reason; the difference is whether anything reads them today.
NOT_SETTINGS: dict[str, str] = {
    "NEXUS_DB_SUPERUSER_PASSWORD": "docker-compose.yml, for the container's POSTGRES_PASSWORD",
    "NEXUS_APP_DB_PASSWORD": "docker/postgres/init/01-app-role.sh, for the app role",
}

# Credentials that do not exist yet. Documented so the shape of the environment
# is known, with the phase that will read them. Listing them here rather than
# waving them through keeps `.env.example` from becoming a wishlist.
FUTURE: dict[str, str] = {
    "NEXUS_DATAFORSEO_LOGIN": "P11/P16 — keyword volumes, never estimated (D2)",
    "NEXUS_DATAFORSEO_PASSWORD": "P11/P16 — keyword volumes, never estimated (D2)",
    "NEXUS_GOOGLE_CLIENT_ID": "P18 — GA4 and Search Console OAuth (D3)",
    "NEXUS_GOOGLE_CLIENT_SECRET": "P18 — GA4 and Search Console OAuth (D3)",
    "NEXUS_PAGESPEED_API_KEY": "P18 — PageSpeed Insights (D3)",
    # doc/14 step 9. `NEXUS_CONNECTOR_SECRET_KEY` has left this list: D27 was
    # answered with option A, so it is a real `Settings` field and deployed
    # environments refuse to boot without it. What remains is one provider's
    # OAuth app, which no amount of code can supply.
    "NEXUS_HUBSPOT_CLIENT_ID": "doc/14 S9 — the first connector, over HubSpot's MCP server",
    "NEXUS_HUBSPOT_CLIENT_SECRET": "doc/14 S9 — the first connector, over HubSpot's MCP server",
    "NEXUS_HUBSPOT_REDIRECT_URI": "doc/14 S9 — OAuth callback, must match the app's registration",
}


def _example_keys() -> set[str]:
    """Every `NEXUS_*` key in `.env.example`, commented-out lines included.

    A commented line still documents the variable, which is the point of the
    file — several are commented precisely because no credential exists yet.
    """
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^#?\s*(NEXUS_[A-Z0-9_]+)=", text, re.MULTILINE))


def _settings_keys() -> set[str]:
    return {f"NEXUS_{name.upper()}" for name in Settings.model_fields}


def test_env_example_documents_every_setting() -> None:
    """A field with no line in the file is a setting nobody knows exists."""
    missing = sorted(_settings_keys() - _example_keys())
    assert not missing, (
        f".env.example does not mention {missing}. Add a line for each, "
        "commented out if there is no value to give yet."
    )


def test_env_example_invents_no_settings() -> None:
    """The direction that produced a required-looking `NEXUS_SESSION_SECRET`
    documented in the file, pinned in `conftest.py`, and read by no line of
    code in the repository."""
    unknown = sorted(_example_keys() - _settings_keys() - set(NOT_SETTINGS) - set(FUTURE))
    assert not unknown, (
        f".env.example documents {unknown}, which no Settings field reads. "
        "Delete the lines, or declare them in NOT_SETTINGS with what reads them, "
        "or in FUTURE with the phase that will."
    )


def test_the_example_does_not_ship_debug_on() -> None:
    """`.env.example` is copied verbatim by `setup.ps1`, so its defaults become
    a developer's defaults. `NEXUS_DEBUG=true` there meant debug logging was on
    for everyone who had never thought about it."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "NEXUS_DEBUG=true" not in text


def test_the_example_database_url_names_the_right_database() -> None:
    """It said `/postgres` — the cluster's maintenance database, not ours. A
    developer who pasted credentials in without reading would migrate the wrong
    database and see nothing wrong."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    line = next(row for row in text.splitlines() if row.startswith("NEXUS_DATABASE_URL="))
    assert not line.rstrip().endswith("/postgres"), line


def test_the_example_file_exists_where_setup_expects_it() -> None:
    assert (Path(REPO_ROOT) / ".env.example").is_file()


# ── Email must actually be able to send when deployed (P3) ────


@pytest.mark.parametrize("env", DEPLOYED)
def test_a_deployed_env_refuses_the_file_mailer(env: Env) -> None:
    """The failure this prevents is silent, which is why it is a refusal.

    `FileMailer` writes `.eml` files and returns a message id. Nothing errors,
    nothing logs a warning, and `/health/ready` stays green — while every
    verification email, every password reset and every invitation goes into a
    directory on a container's ephemeral disk. The first symptom is a customer
    saying nobody can sign up, weeks later.
    """
    with pytest.raises(ValidationError, match="MAILER_BACKEND=file"):
        _settings(
            env=env,
            database_url=SecretStr("postgresql+asyncpg://u:p@h:5432/nexus"),
            storage_signing_secret=SecretStr("a-real-secret"),
            mailer_backend="file",
            public_base_url="https://app.example.invalid",
        )


@pytest.mark.parametrize("env", DEPLOYED)
def test_a_deployed_env_refuses_smtp_without_a_host(env: Env) -> None:
    with pytest.raises(ValidationError, match="NEXUS_SMTP_HOST"):
        _settings(
            env=env,
            database_url=SecretStr("postgresql+asyncpg://u:p@h:5432/nexus"),
            storage_signing_secret=SecretStr("a-real-secret"),
            smtp_host="",
        )


@pytest.mark.parametrize("env", DEPLOYED)
def test_a_deployed_env_refuses_smtp_without_tls(env: Env) -> None:
    """Without STARTTLS the credentials and every single-use token in the body
    cross the network in clear text. Permitted in local and ci for a relay that
    has none; not where real addresses are."""
    with pytest.raises(ValidationError, match="SMTP_TLS"):
        _settings(
            env=env,
            database_url=SecretStr("postgresql+asyncpg://u:p@h:5432/nexus"),
            storage_signing_secret=SecretStr("a-real-secret"),
            smtp_tls=False,
        )


@pytest.mark.parametrize("env", DEPLOYED)
def test_a_deployed_env_refuses_a_plaintext_base_url(env: Env) -> None:
    """Every verification and reset link is built from this value, so `http://`
    puts single-use account tokens on the wire — and a reset token *is* the
    account."""
    with pytest.raises(ValidationError, match="PUBLIC_BASE_URL"):
        _settings(
            env=env,
            database_url=SecretStr("postgresql+asyncpg://u:p@h:5432/nexus"),
            storage_signing_secret=SecretStr("a-real-secret"),
            public_base_url="http://app.example.invalid",
        )


@pytest.mark.parametrize("env", UNDEPLOYED)
def test_local_and_ci_keep_the_file_mailer(env: Env) -> None:
    """The other half, and the reason D4 gates deployment rather than
    development: the whole verification and invitation chain works here with no
    provider and no account."""
    settings = _settings(env=env)
    assert settings.mailer_backend == "file"
    assert settings.public_base_url.startswith("http://")


def test_the_link_base_is_configuration_and_never_the_request_host() -> None:
    """`Host` is attacker-controlled. A verification link built from it is a
    working account-takeover primitive: register, receive a link pointing at
    your own host, harvest the token when the real owner clicks it.

    Asserted as an absence, because the mistake is easy and the symptom is
    nothing at all until someone exploits it.
    """
    from pathlib import Path as _Path

    source = (_Path(__file__).resolve().parents[1] / "app" / "routes" / "auth.py").read_text(
        encoding="utf-8"
    )
    assert "public_base_url" in source, "the links must come from configuration"

    # Narrowly `Host` and its proxy equivalents. `request.headers.get(
    # "user-agent")` is read one line away and is fine — it is recorded on the
    # session row, not used to build a URL. A first version of this test
    # forbade `request.headers` outright and failed on exactly that.
    for header in ('"host"', "'host'", '"x-forwarded-host"', '"x-forwarded-proto"'):
        assert header not in source.lower(), (
            f"an auth route reads {header} — every emailed link built from it is "
            "attacker-controlled, which is an account-takeover primitive"
        )
    assert "request.base_url" not in source
    assert "request.url_for" not in source


@pytest.mark.parametrize("env", DEPLOYED)
def test_a_deployed_env_refuses_to_start_without_the_maintenance_role(env: Env) -> None:
    """ADR 0018, and the refusal matters more than the setting.

    The tempting alternative is to fall back to `nexus_app` when
    `NEXUS_JOBS_DATABASE_URL` is unset. That would restore exactly the failure
    D24 was raised about: the expiry sweep would run, match zero rows under the
    `domain_claim` policy, and log a clean pass — in production, while every
    test stayed green.
    """
    with pytest.raises(ValidationError, match="JOBS_DATABASE_URL"):
        _settings(
            env=env,
            database_url=SecretStr("postgresql+asyncpg://u:p@h:5432/nexus"),
            storage_signing_secret=SecretStr("a-real-secret"),
            jobs_database_url=SecretStr(""),
        )


def test_the_jobs_engine_refuses_rather_than_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same rule one layer down, because `local` and `ci` are permitted to
    leave it unset and something has to refuse when a caller then uses it.

    The variable is cleared explicitly: CI *does* set it (the maintenance role
    is bootstrapped there), so without this the engine builds happily and the
    test passes for the wrong reason. It did, on the first run.
    """
    from app.db import get_engine, get_jobs_engine

    monkeypatch.setenv("NEXUS_JOBS_DATABASE_URL", "")
    get_settings.cache_clear()
    get_jobs_engine.cache_clear()
    get_engine.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="NEXUS_JOBS_DATABASE_URL"):
            get_jobs_engine()
    finally:
        get_settings.cache_clear()
        get_jobs_engine.cache_clear()
        get_engine.cache_clear()
