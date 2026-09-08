"""Application settings.

Everything comes from the environment. No secret has a usable default — a
missing one fails at startup rather than silently running with a placeholder.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _data_root() -> Path:
    """Where the filesystem drivers keep `.storage` and `.mail`.

    In the repository this file is `services/api/app/config.py`, so the root is
    four levels up. **In the container it is `/app/app/config.py`** — the image
    does not mirror the repository layout, and there is no fourth parent, so a
    fixed `parents[3]` raised `IndexError` before anything could report a better
    error. It failed at import, inside alembic, with a traceback that named
    neither the setting nor the container.

    So: the repository root when this is running from a checkout, and the
    package's own parent otherwise. `NEXUS_DATA_ROOT` overrides both, because
    the right answer in a deployment is a mounted volume rather than anything
    inferred from a file path.
    """
    if override := os.environ.get("NEXUS_DATA_ROOT"):
        return Path(override)

    here = Path(__file__).resolve()
    parents = here.parents
    # `pyproject.toml` four levels up means a checkout; anything else is an
    # installed layout, where `/app` (the parent of the package) is the root.
    if len(parents) > 3 and (parents[1] / "pyproject.toml").exists():
        return parents[3]
    return parents[1]


REPO_ROOT = _data_root()


class Env(StrEnum):
    local = "local"
    ci = "ci"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="NEXUS_",
        extra="ignore",
    )

    env: Env
    """Required, with no default, and that is the fix for a real failure.

    It defaulted to `local`, and `is_local` also answered true for `ci`. So a
    deployment that simply forgot `NEXUS_ENV` served `/docs` and
    `/openapi.json` publicly and set `secure=False` on both the session and the
    CSRF cookie, over the internet, on a product holding company financials.
    Nothing failed and nothing logged.

    The plan offered two fixes — drop `ci` from `is_local`, or make cookie
    security independent of it. Neither addresses the default, which is what
    turned a forgotten variable into insecure cookies. So there is no default:
    a missing `NEXUS_ENV` is a startup error naming the variable, rather than a
    silent choice of the most permissive environment. See ADR 0015.
    """

    debug: bool = False

    # ── Database ──────────────────────────────────────────────
    # A pgvector-enabled Postgres. See ADR 0001 — hosted free tier locally.
    database_url: SecretStr = Field(
        default=SecretStr(""),
        description="postgresql+asyncpg://... — must have the vector extension available",
    )
    db_transaction_pooler: bool = False
    """Whether the URL points at a transaction-mode pooler.

    Was inferred from `"-pooler" in url`, which is a guess about a hostname: it
    is true of Neon's pooled endpoint and of nothing else. PgBouncer in front of
    RDS, a Cloud SQL proxy, or Neon renaming the endpoint all leave it silently
    false — and the failure it prevents is `prepared statement ... does not
    exist` appearing only under concurrency."""

    db_statement_timeout: str = "15s"
    """Bounds a single query. A request that hangs otherwise holds one of five
    pooled connections until the process restarts."""

    db_lock_timeout: str = "5s"
    """Bounds *waiting* for a lock, which the statement timeout does not: a
    statement blocked on a lock has not begun executing."""

    db_idle_in_transaction_timeout: str = "180s"
    """Bounds an open transaction doing nothing — the shape a request that died
    mid-flight leaves behind, and the one that blocks every later migration.

    **It was 30s, which is shorter than the model calls this application makes
    inside a transaction.** `scoped_connection` opens one transaction around a
    whole handler, and onboarding's handlers then spend tens of seconds waiting
    on a provider with that transaction sitting idle. Measured on one `/read`:
    27.7s for `company-research` plus 8.0s for `company-summary`, so the session
    was idle-in-transaction for 35.7s — and Postgres closed the connection
    underneath it. The `UPDATE` that followed raised `InterfaceError: connection
    is closed`, the request 500'd, and both model calls were paid for and
    discarded.

    180s clears every stage measured so far (the slowest is a ~45s assembly
    call) and stays well under the client's 240s proxy timeout, so the proxy
    remains the outer bound rather than this.

    **This is a mitigation, not the fix.** The fix is to stop holding a
    transaction across a third-party network call at all — do the model work,
    *then* open the transaction to write. Until that happens this number has to
    stay above the slowest skill, which is a coupling between a database setting
    and a provider's latency that nobody should have to remember. The cost of
    raising it is real: a genuinely abandoned transaction now holds its locks
    for three minutes instead of thirty seconds."""

    db_command_timeout_seconds: float = 20.0
    """asyncpg's own, client-side. It still fires when the server is
    unreachable rather than merely slow, which a server-side timeout cannot."""

    db_pool_timeout_seconds: float = 10.0
    """How long a request waits for a connection from the pool before failing.
    SQLAlchemy's default is 30s, which is longer than most callers will wait."""

    # ── The pool itself (finding B1/B5) ───────────────────────
    #
    # These four were hardcoded in `get_engine`, which made them untunable in
    # the one place tuning matters: the cost of every one of them is a function
    # of the round trip to the database, and that number is a deployment fact
    # rather than a code fact. Measured against the Neon instance in `.env`
    # (us-east-2, from a laptop):
    #
    #     cold connect + first statement   7,148 ms
    #     warm statement                     529 ms
    #     one argon2 hash                     19 ms
    #
    # The third line is the one that matters for the breaking-point report:
    # a password hash is 1/370th of a connection, so login latency under load
    # was never argon2 serialising on CPU. It was connections.

    db_pool_size: int = 10
    """Connections kept open per process.

    Was 5. At ~0.5s per statement a single connection sustains about two
    statements a second, so five of them capped this API at roughly ten — and a
    request that runs four or five statements is then one of two concurrent
    requests before the sixth waits. Ten doubles the ceiling and stays far
    below any managed provider's per-role limit for one process.

    **Raising it is not free and not a substitute for co-location.** Each
    connection is server-side memory, and twenty of them against a database
    500ms away still gives every request a 500ms floor. This buys concurrency,
    not latency."""

    db_pool_max_overflow: int = 10
    """Extra connections allowed above `db_pool_size` under burst, then closed.

    Was 5. Kept equal to the pool size so a burst can double capacity briefly
    without the overflow becoming the steady state — an overflow connection is
    discarded on return rather than pooled, so it pays the full connect cost
    every time and is a worse deal than a larger pool for sustained load."""

    db_pool_recycle_seconds: int = 120
    """Discard a pooled connection older than this, without asking the server.

    Was 300, which sits right on the boundary a managed provider is likely to
    close an idle connection at — so the recycle was as likely to run after the
    provider had already gone as before. 120s is comfortably inside it.

    **This is the cheap half of staying ahead of a dead connection.** It costs
    nothing at all: no round trip, no ping, just an age check in the pool. It is
    what makes `db_pool_pre_ping` optional rather than mandatory."""

    db_pool_pre_ping: bool = True
    """Test a pooled connection before handing it to a request.

    **Correct on a co-located database and very expensive on a remote one**,
    because what it costs is round trips. Measured on a warm pool, checkout plus
    one statement:

        pre_ping on    2,249 ms
        pre_ping off     977 ms

    ~1.27s per request, on every request, and that single line is most of the
    "4s to return a 409" in the breaking-point report. On a database in the same
    region — where a round trip is a millisecond or two — the same setting costs
    about 2ms and is obviously worth it.

    So it stays **on by default**, because the default has to be the safe one
    and production is meant to be co-located (ADR 0008's region choice is the
    real fix). Set `NEXUS_DB_POOL_PRE_PING=false` when the database is a long
    way away and you would rather have the latency back.

    What you give up by turning it off: `db_pool_recycle_seconds` still discards
    connections *before* a provider's idle timeout, so the ordinary
    idle-close case is covered without it. The case it does not cover is a
    provider suspending its compute — Neon scales to zero — which kills
    connections of any age. There, the first request after a suspend fails once
    while the pool invalidates, and then recovers. That is a fair trade for a
    busy service and a bad one for a demo box that idles, which is exactly why
    this is a setting and not a constant."""

    # ── Sessions ──────────────────────────────────────────────
    #
    # There is deliberately no `session_secret`. One was declared here,
    # documented in `.env.example`, required by the validator below, pinned in
    # `conftest.py` — and read by no line of code in the repository. A
    # required-looking secret that nothing reads is worse than none: it teaches
    # whoever provisions the environment that the list of secrets is
    # approximate.
    #
    # Nothing signs a session token because there is nothing to sign. The token
    # is 256 bits of CSPRNG output and only its SHA-256 hash is stored, so
    # presenting it is authenticated by the lookup itself; an HMAC over a random
    # opaque string adds no property. See `app/auth/tokens.py` and ADR 0015.
    session_cookie_name: str = "nexus_session"
    session_max_age_seconds: int = 60 * 60 * 12

    # ── Local infrastructure substitutes (ADR 0001) ───────────
    storage_backend: str = "filesystem"
    storage_root: Path = REPO_ROOT / ".storage"
    storage_signing_secret: SecretStr = Field(default=SecretStr(""))
    signed_url_ttl_seconds: int = 300

    # ── Email (P3) ────────────────────────────────────────────
    # `file` writes RFC-822 `.eml` files to `mail_root`; `smtp` sends. The file
    # backend is not a stub — it is what makes the whole verification and
    # invitation chain testable end to end with no provider and no account, so
    # **D4 gates deployment rather than development**.
    mailer_backend: str = "file"
    mail_root: Path = REPO_ROOT / ".mail"

    run_scheduler: bool = False
    """Whether this process runs the scheduled jobs. **Off by default.**

    It used to be every API process, unconditionally — the note in
    `AUDIT-FINDINGS.md` under "by design" said so and named the threshold at
    which it stops being acceptable. That threshold is a second replica: three
    API containers behind a proxy means three copies of every sweep, and the
    jobs are idempotent rather than exclusive, so the symptom is triple the load
    rather than an error anybody sees.

    The other reason is the ~2 GB embedding model. Once `[embeddings]` is
    installed, the process that runs the embedding pass holds those weights
    resident — and that must not be the process serving requests.

    `docker-compose.yml` sets this true on exactly one container: the worker."""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = Field(default=SecretStr(""))
    smtp_from: str = "NEXUS OS <no-reply@nexusos.local>"
    # STARTTLS on the port above. Off only for a local relay, and the validator
    # refuses that combination in a deployed environment.
    smtp_tls: bool = True

    # ── The maintenance role (ADR 0018, D24) ──────────────────
    # A second connection string, for `nexus_jobs`. It exists so RLS on
    # `domain_claim` can be `user_id`-scoped without breaking the two writes
    # that are legitimately nobody's in particular — the expiry sweep and the
    # dispute record.
    #
    # Empty is permitted in `local` and `ci` only, and `require_jobs_url()`
    # refuses rather than falling back. Falling back to `nexus_app` would
    # restore the exact silent failure ADR 0018 exists to prevent: the sweep
    # would run, match zero rows under the policy, and log a clean pass.
    jobs_database_url: SecretStr = Field(default=SecretStr(""))

    # ── Credential backoff (D14) ──────────────────────────────
    # The curve `app/routes/auth.py` spends when a caller is over the login or
    # register limit: doubling from `base`, capped at `max`.
    #
    # Configurable because the cap is a real operational trade-off — too low and
    # a determined guesser is barely slowed, too high and each attempt holds a
    # worker long enough that the backoff becomes a way to exhaust the service
    # it protects. And because the suite would otherwise spend minutes asleep
    # proving a property that has nothing to do with the wall clock.
    login_backoff_base_seconds: float = 0.25
    login_backoff_max_seconds: float = 8.0

    # Where the links in those emails point. Not derived from the request:
    # `Host` is attacker-controlled, and a verification link built from it is a
    # working account-takeover primitive — the attacker registers, receives a
    # link to their own host, and harvests the token when the real owner clicks.
    public_base_url: str = "http://localhost:3000"

    # ── Embeddings (ADR 0003) ─────────────────────────────────
    embedding_model_id: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024
    model_cache_dir: Path = REPO_ROOT / "models"
    embeddings_enabled: bool = True
    """Environment-level off switch, separate from the library being absent.

    Same distinction as `ai_enabled`: "not installed yet" and "deliberately
    switched off" are different messages to a user. An absent library is never
    an error — the model is a ~2GB download and running without it is a
    supported state, in which documents still upload, parse and classify but are
    not yet searchable."""

    # ── Language model (ADR 0011) ─────────────────────────────
    # Deliberately has no usable default and is NOT passed through `require()`.
    # Every other secret here fails loudly when absent because the application
    # cannot work without it; this one is different — an empty key is a
    # supported operating state. `app/ai/registry.py` returns a provider that
    # reports `unconfigured` and the product runs without AI features.
    anthropic_api_key: SecretStr = Field(default=SecretStr(""))

    anthropic_model: str = "claude-sonnet-5"
    """The fallback tier, for any call that does not pin one.

    Every skill pins its own model in `manifest.toml` (`app/ai/skills/*`), and a
    skill's tier is part of its definition — the eval that approved it on one
    tier says nothing about another. So this is reached only by calls made
    outside the skill runtime.

    Kept current deliberately. A stale default is not a neutral choice: Opus 4.7
    and later, and Sonnet 5, reject `temperature` outright, so a default left on
    an older id quietly changes which request shape the provider builds.
    """
    ai_enabled: bool = True
    """Environment-level off switch, separate from the key being absent.
    Distinguishes "not configured yet" from "deliberately switched off"."""

    disabled_ai_skills: str = ""
    """Comma-separated skill names — the per-skill kill switch (doc 07 M8 task
    8.7). Per-skill rather than global so one misbehaving prompt can be stopped
    without taking down every AI feature in the product."""

    # ── Guardrails (doc 06 §8.4) ──────────────────────────────
    tenant_daily_token_budget: int = 2_000_000
    user_daily_token_budget: int = 200_000

    # ── Crawl budget (doc 06 §1.2) ────────────────────────────
    # `trusted_proxy_ips` and `preview_ttl_hours` sat here until Phase 2. Both
    # existed only for the unauthenticated audit: the first decided whose
    # `X-Forwarded-For` to believe when rate-limiting anonymous callers, the
    # second bounded how long a third party's crawled data was retained. With
    # no anonymous crawl there is no address to attribute and no third-party
    # data to expire (`doc/11` Q1, D9 void). The limits below survive because a
    # crawl still has to be bounded, whoever asked for it.
    crawl_max_bytes: int = 5_000_000
    crawl_timeout_seconds: int = 15
    crawl_max_redirects: int = 5

    # Secrets the application cannot work without once it is deployed.
    # `anthropic_api_key` is deliberately absent: an empty key is a supported
    # operating state (ADR 0011), and listing it here would turn "no AI yet"
    # into a refusal to boot.
    _DEPLOYED_REQUIRES = ("database_url", "storage_signing_secret")

    @model_validator(mode="after")
    def _required_in_deployed_envs(self) -> Settings:
        """Refuse to start in a deployed environment with a secret missing.

        This replaces a `field_validator` over the same secrets whose body was
        `return v`. It enforced nothing while presenting as a security control,
        which is worse than its absence, because absence is visible.

        A model validator rather than a field one for two reasons: it can read
        `env` without depending on field declaration order, and it can name
        every missing secret in one error. A deployment fixing them one restart
        at a time is a deployment being told the truth slowly.

        Local and `ci` stay permissive on purpose, so the process boots and
        answers a health check before a database exists. That was always the
        intent; only the enforcement everywhere else was missing.
        """
        if self.env in (Env.local, Env.ci):
            return self

        missing = [
            f"NEXUS_{name.upper()}"
            for name in self._DEPLOYED_REQUIRES
            if not getattr(self, name).get_secret_value()
        ]
        if missing:
            names = " and ".join(missing) if len(missing) < 3 else ", ".join(missing)
            raise ValueError(
                f"NEXUS_ENV={self.env.value} requires {names}, which "
                f"{'is' if len(missing) == 1 else 'are'} empty or unset. These "
                "are only optional in local and ci, where the app must boot "
                "before a database exists."
            )

        # Email is separate from the secret list because what it requires
        # depends on which backend is selected, and because getting it wrong is
        # silent rather than loud: a deployed environment left on the `file`
        # backend writes verification emails to a directory nobody reads, and
        # every new account is stuck unverified with no error anywhere.
        if self.mailer_backend == "file":
            raise ValueError(
                f"NEXUS_ENV={self.env.value} cannot use NEXUS_MAILER_BACKEND=file. "
                "It writes .eml files to disk instead of sending them, so every "
                "verification and invitation would silently go nowhere. Set "
                "smtp, or say so explicitly by pointing mail_root at a volume "
                "someone reads."
            )
        if self.mailer_backend == "smtp" and not self.smtp_host:
            raise ValueError(
                f"NEXUS_ENV={self.env.value} with NEXUS_MAILER_BACKEND=smtp "
                "requires NEXUS_SMTP_HOST."
            )
        if self.mailer_backend == "smtp" and not self.smtp_tls:
            raise ValueError(
                "NEXUS_SMTP_TLS=false sends credentials and every verification "
                "token in clear text. It is allowed in local and ci for a "
                f"local relay; NEXUS_ENV={self.env.value} is not."
            )
        if not self.jobs_database_url.get_secret_value():
            raise ValueError(
                f"NEXUS_ENV={self.env.value} requires NEXUS_JOBS_DATABASE_URL. "
                "The expiry sweep connects as nexus_jobs, which holds the only "
                "policy permitting it to see another user's domain claim (ADR "
                "0018). Without it the sweep matches zero rows and reports "
                "success, which is the failure that decision was made to avoid."
            )
        if self.public_base_url.startswith("http://"):
            raise ValueError(
                f"NEXUS_ENV={self.env.value} requires an https NEXUS_PUBLIC_BASE_URL. "
                "Every verification and password-reset link is built from it, so "
                "plain http puts single-use account tokens on the wire."
            )
        return self

    @property
    def cookies_secure(self) -> bool:
        """Whether the session and CSRF cookies carry `Secure`.

        False for `local` and `ci`, which are served over plain HTTP. Safe now
        only because `env` has no default: previously a forgotten `NEXUS_ENV`
        landed here as `local` and produced insecure cookies in production.
        """
        return self.env not in (Env.local, Env.ci)

    @property
    def docs_enabled(self) -> bool:
        """Whether `/docs` and `/openapi.json` are served.

        Narrower than cookie security, and deliberately so. Together they
        enumerate every endpoint and its schema; a developer's machine is the
        only place that is a convenience rather than a disclosure. `ci` is
        excluded — nobody reads `/docs` there.
        """
        return self.env is Env.local

    @property
    def disabled_ai_skills_set(self) -> frozenset[str]:
        return frozenset(s.strip() for s in self.disabled_ai_skills.split(",") if s.strip())

    def require(self, name: str) -> str:
        """Fetch a secret, failing loudly if it was never configured.

        Note `anthropic_api_key` is deliberately never fetched through here. An
        absent language model is a supported state, not a misconfiguration, and
        routing it through `require()` would turn "no AI yet" into a crash.
        """
        value = getattr(self, name)
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw:
            raise RuntimeError(
                f"NEXUS_{name.upper()} is not set. Copy .env.example to .env and fill it in."
            )
        return str(raw)


@lru_cache
def get_settings() -> Settings:
    return Settings()
