"""Authentication routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import anyio
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import password_reset
from app.auth.csrf import CSRF_COOKIE_NAME, require_csrf
from app.auth.email_verification import build_email as build_verification_email
from app.auth.email_verification import issue as issue_verification
from app.auth.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
)
from app.auth.service import (
    AuthError,
    EmailAlreadyRegisteredError,
    authenticate,
    issue_session,
    memberships_for_user,
    register_user,
    resolve_session,
    revoke_session,
)
from app.auth.tokens import new_csrf_token
from app.config import Settings, get_settings
from app.connectors.rate_limit import (
    LOGIN_PER_EMAIL,
    LOGIN_PER_IP,
    REGISTER_PER_IP,
    backoff_seconds,
    consume,
    hash_bucket_key,
)
from app.db import _unscoped_session
from app.deps import CurrentScope, CurrentSession
from app.domain import audit
from app.logging import get_logger
from app.mail import Email, Mailer, build_mailer, send_safely
from app.retrieval.scoped import scoped_connection

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


async def _email_for(db: AsyncSession, user_id: UUID) -> str:
    """The stored address for a user.

    Read back rather than echoed from the request: `authenticate` matches on a
    normalised address, so what somebody typed at the login box and what the
    account actually holds are not guaranteed to be the same string, and the
    account's own copy is the one worth showing them.
    """
    row = (
        await db.execute(text("SELECT email FROM app_user WHERE id = :u"), {"u": str(user_id)})
    ).scalar()
    # A resolved session whose user has been deleted is not a state this
    # endpoint can meaningfully report, and it must not 500 while signing
    # somebody out. Empty string renders as absent; every caller is already
    # holding a valid session.
    return str(row) if row else ""


class WorkspaceSummary(BaseModel):
    workspace_id: UUID
    name: str
    role: str


class SessionResponse(BaseModel):
    user_id: UUID
    email: str
    """Who this is, in the form they typed it.

    Finding F8: without it `/account` had only the id to render, so the page
    that promises *"everything below is read from the API"* identified a person
    by a UUID and their company by another one. It discloses nothing — this
    endpoint already requires that person's own session, and the address is the
    one they signed in with.
    """

    workspaces: list[WorkspaceSummary]
    active_workspace_id: UUID | None


def _set_session_cookie(response: Response, token: str, settings: Settings) -> str:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,  # not reachable from JavaScript, so XSS cannot exfiltrate it
        secure=settings.cookies_secure,  # plain HTTP only in local and ci
        samesite="lax",  # blocks cross-site POSTs while keeping normal navigation
        path="/",
    )

    # Double-submit companion. Deliberately readable by JavaScript — the client
    # must be able to echo it into a header, which is precisely what a
    # cross-origin attacker cannot do.
    csrf = new_csrf_token()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf,
        max_age=settings.session_max_age_seconds,
        httponly=False,
        secure=settings.cookies_secure,
        samesite="lax",
        path="/",
    )
    return csrf


def _caller_key(request: Request, settings: Settings) -> str:
    """A hashed, stable identifier for the source of a credential attempt.

    The direct peer, never `X-Forwarded-For`. That header is attacker-controlled
    unless a trusted proxy list says otherwise, and this repository deleted its
    trusted-proxy configuration with the preview product in P2 — so believing it
    now would let one client mint unlimited rate-limit identities and walk
    straight through the per-IP counter.

    The consequence is stated rather than hidden: **behind a proxy every visitor
    shares one bucket**, and the per-IP limit collapses towards a global one.
    That is the safe direction to fail, and the per-email counter is what keeps
    the limit meaningful while it is true. A deployment that terminates TLS
    elsewhere needs the trusted-proxy list back before this counter means
    anything.
    """
    peer = request.client.host if request.client else "unknown"
    return hash_bucket_key(peer, secret=settings.require("storage_signing_secret"))


async def _throttle(delay: float) -> None:
    """Spend the backoff.

    After the work, never instead of it. A delay applied *before* authenticating
    would be separable from the response by anyone timing the two, and the whole
    of D14 rests on a caller being unable to tell one reply from another.
    """
    if delay > 0:
        await anyio.sleep(delay)


def _send_later(background: BackgroundTasks, mailer: Mailer, message: Email) -> None:
    """Queue a message so the response does not wait for the transport.

    This is a security property, not a latency optimisation. If the send happens
    inline, a request for an address that has an account takes an SMTP
    round-trip longer than one that does not — and both of the endpoints below
    are built on the premise that a caller cannot tell those apart. Identical
    bodies do not help if the clock answers the question.
    """
    # `send_safely`, not `mailer.send`. This runs after the response has gone,
    # so an exception here is swallowed by the task runner — the user waits for
    # a message that never arrives and nothing says why.
    background.add_task(send_safely, mailer, message)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Create an account and send the verification email.

    Returns the same response whether or not the email was already registered.
    A distinct "already registered" reply is a membership oracle: it confirms
    which addresses hold accounts here.

    **Delivery is what makes that safe rather than merely quiet.** Until P3 there
    was no email, so the same-response rule protected the address at the cost of
    telling nobody anything — and `email_verified_at` could never be set, which
    left the EMAIL domain-verification method structurally dead. The real owner
    now learns what happened, including that somebody else tried to register
    their address, and a duplicate registration deliberately sends **nothing**:
    a second email would confirm to whoever triggered it that the first account
    exists.
    """
    # Metered per source address. This is the more expensive of the two
    # credential endpoints — every call hashes a password whether or not the
    # address is new — and it is an unbounded `app_user` growth vector besides.
    #
    # Backoff rather than refusal, for the same reason as login: a 429 here
    # would be observable, and the response is supposed to be identical
    # regardless of what the caller has been doing.
    caller = _caller_key(request, settings)
    async with _unscoped_session() as db:
        over = await consume(db, REGISTER_PER_IP, caller)
        await db.commit()
    delay = backoff_seconds(
        over,
        base=settings.login_backoff_base_seconds,
        cap=settings.login_backoff_max_seconds,
    )

    try:
        async with _unscoped_session() as db:
            user_id = await register_user(
                db,
                email=payload.email,
                password=payload.password,
                display_name=payload.display_name,
                phone=payload.phone,
            )
            issued = await issue_verification(db, user_id=user_id, email=payload.email)
            await db.commit()
    except EmailAlreadyRegisteredError:
        log.info("auth.register.duplicate")
        await _throttle(delay)
        return {"status": "check_your_email"}
    except WeakPasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    _send_later(
        background,
        build_mailer(settings),
        build_verification_email(
            to=payload.email, token=issued.token, base_url=settings.public_base_url
        ),
    )
    log.info("auth.register.verification_queued")
    await _throttle(delay)
    return {"status": "check_your_email"}


# ── Password reset ────────────────────────────────────────────


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


@router.post("/password-reset/request")
async def request_password_reset(
    payload: PasswordResetRequest,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Send a reset link, if there is anywhere to send it.

    **The response is byte-identical either way**, and deliberately so: this is
    the cheapest endpoint in the product to query, it needs no account to reach,
    and a one-word difference between "sent" and "no such account" is a complete
    account-enumeration oracle.

    The two paths are kept as short and as similar as possible for that reason —
    `password_reset.request` returns `None` rather than raising, and the send is
    queued rather than awaited, so neither control flow nor the clock
    distinguishes them.
    """
    async with _unscoped_session() as db:
        issued = await password_reset.request(db, email=payload.email)
        await db.commit()

    if issued is not None:
        _send_later(
            background,
            build_mailer(settings),
            password_reset.build_email(
                to=issued.email, token=issued.token, base_url=settings.public_base_url
            ),
        )

    # No `email` field, no count, no timing tell. Logged without the address:
    # which addresses ask for resets is the fact this endpoint protects.
    log.info("auth.password_reset.requested")
    return {"status": "check_your_email"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(payload: PasswordResetConfirm) -> dict[str, str]:
    """Set a new password and sign the account out everywhere.

    One message for expired, already-used and never-existed, exactly as
    `/auth/verify-email` does. Telling them apart would confirm which tokens
    were real.
    """
    try:
        async with _unscoped_session() as db:
            user_id = await password_reset.confirm(
                db, token=payload.token, new_password=payload.password
            )
            await db.commit()
    except WeakPasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    if user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That link is invalid or has expired.")

    log.info("auth.password_reset.confirmed")
    return {"status": "password_updated"}


@router.post("/login", response_model=SessionResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    """Sign in.

    **Rate limited without becoming an oracle** (D14, `doc/11` §5.2). Two
    counters — the caller's address and the address being guessed at — because
    either alone has an obvious defeat: per-IP falls to a botnet, per-email
    falls to rotating the target.

    Being over the limit costs a **delay, then the same 401 as always**. Not a
    429, and not a lock:

    - A **429 keyed by email is a confirmation the address exists**, available
      to anyone for the price of a few requests. It would undo M1's
      account-enumeration work in the act of adding security, which is why the
      status, the body and the headers here are identical whatever the counters
      say.
    - A **lock is a denial-of-service vector against a named user.** Anyone who
      knows an Owner's address could hold them out of their own workspace during
      an incident. Backoff slows an attacker without handing them that.

    The delay is spent *after* authenticating, so it cannot be timed separately
    from the work. `tests/test_login_rate_limit.py` holds all of this.
    """
    caller = _caller_key(request, settings)
    email_key = hash_bucket_key(payload.email, secret=settings.require("storage_signing_secret"))

    async with _unscoped_session() as db:
        # Counted before the attempt, and committed even when it fails — an
        # increment rolled back with a failed login is an attempt that did not
        # count, which is every attempt an attacker makes.
        over_ip = await consume(db, LOGIN_PER_IP, caller)
        over_email = await consume(db, LOGIN_PER_EMAIL, email_key)
        await db.commit()

    delay = backoff_seconds(
        max(over_ip, over_email),
        base=settings.login_backoff_base_seconds,
        cap=settings.login_backoff_max_seconds,
    )

    async with _unscoped_session() as db:
        try:
            user_id = await authenticate(db, email=payload.email, password=payload.password)
        except AuthError as exc:
            await _throttle(delay)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from exc

        memberships = await memberships_for_user(db, user_id=user_id)
        email = await _email_for(db, user_id)
        # Only auto-select when there is no ambiguity. Picking one of several on
        # the user's behalf risks acting in the wrong client's workspace — the
        # reasoning was written before multi-entity existed and it still holds.
        #
        # **But resuming is not picking** (ADR 0026). The sign-in screen says
        # *"your workspace and everything in it stays exactly where you left
        # it"*, and carrying the pointer forward from this person's most recent
        # session is that sentence being true. Without it, somebody holding two
        # companies logs in with no active entity and `current_scope` refuses
        # everything with "No workspace selected" — which the dashboard reads as
        # a dead session and bounces to sign-in. A loop.
        #
        # Filtered against live memberships, so a revoked entity is not resumed
        # into.
        active = memberships[0].workspace_id if len(memberships) == 1 else None
        if active is None and memberships:
            held = {m.workspace_id for m in memberships}
            previous = (
                await db.execute(
                    text(
                        "SELECT active_workspace_id FROM user_session"
                        " WHERE user_id = :u AND active_workspace_id IS NOT NULL"
                        " ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"u": str(user_id)},
                )
            ).scalar_one_or_none()
            if previous is not None and UUID(str(previous)) in held:
                active = UUID(str(previous))

        issued = await issue_session(
            db,
            user_id=user_id,
            ttl_seconds=settings.session_max_age_seconds,
            active_workspace_id=active,
            user_agent=request.headers.get("user-agent"),
        )
        # I9. Only when the session lands in a workspace: `audit_log` is
        # workspace-scoped, and an account with no membership has no tenant to
        # own the row. `app/domain/audit.py` explains why a NULL would be worse
        # than an absence — the isolation predicate makes such a row invisible
        # to everyone, which is a log entry that exists and cannot be read.
        if active is not None:
            await audit.record(
                db,
                workspace_id=active,
                action=audit.AuditAction.LOGIN,
                actor_user_id=user_id,
            )

        await db.commit()

    # A success is throttled on the same curve. Otherwise the *absence* of the
    # delay announces that the password was right, and a guesser who has crossed
    # the limit learns exactly what they were trying to learn.
    await _throttle(delay)

    _set_session_cookie(response, issued.token, settings)
    log.info("auth.login", workspace_count=len(memberships), backed_off=delay > 0)

    return SessionResponse(
        user_id=user_id,
        email=email,
        workspaces=[
            WorkspaceSummary(workspace_id=m.workspace_id, name=m.workspace_name, role=m.role.value)
            for m in memberships
        ],
        active_workspace_id=active,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def logout(
    settings: Annotated[Settings, Depends(get_settings)],
    nexus_session: Annotated[str | None, Cookie(alias="nexus_session")] = None,
) -> Response:
    if nexus_session:
        async with _unscoped_session() as db:
            resolved = await resolve_session(db, token=nexus_session)
            if resolved is not None:
                # Logged before the revocation, while the session still names a
                # workspace. `revoke_session` does not clear the pointer, but
                # reading it first keeps the row's meaning independent of that.
                if resolved.active_workspace_id is not None:
                    await audit.record(
                        db,
                        workspace_id=resolved.active_workspace_id,
                        action=audit.AuditAction.LOGOUT,
                        actor_user_id=resolved.user_id,
                    )
                await revoke_session(db, session_id=resolved.session_id)
                await db.commit()

    # Cookies are cleared on the response that is actually returned.
    #
    # This used to call `delete_cookie` on an injected `response: Response` and
    # then `return Response(...)`. FastAPI only merges the injected response's
    # headers when the handler returns *data*; returning a Response replaces it
    # outright, so both deletions were silently discarded and the browser kept
    # sending a cookie for a session that had been revoked server-side. The
    # revocation always worked, which is why nothing caught it — the session was
    # genuinely dead, but no client could tell.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.session_cookie_name, path="/")
    # The CSRF companion goes too. The session cookie is httponly, so the
    # readable CSRF cookie is the only signed-in signal a client can see; one
    # surviving logout leaves every client believing a dead session is live.
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return response


# `POST /auth/workspace` stood here until P3, with a `_teardown_on_switch` hook
# beside it holding the seam for doc 06 §2.1's agent teardown and cache
# invalidation on switch.
#
# Both are deleted rather than left in place, because `doc/11` §3.2 removed the
# thing they served: **a NEXUS account belongs to one company**, so there is
# never a second workspace to switch to. Keeping a validated, tested endpoint
# for a state the product no longer has would be keeping an attack surface for a
# feature nobody can reach — and keeping the teardown hook would be keeping a
# seam for an invariant (I5) that no longer applies.
#
# I5's cache-invalidation-on-switch requirement is void with it; scope-keyed
# caching remains, and remains necessary, for **role change**, which is still
# immediate (doc 06 §4.15). `ARCHITECTURE-HLD.md` §4.6 records that.
#
# `membership_own_rows` from migration 0003 stays. Login still reads it to find
# the one workspace, and `SessionResponse.workspaces` is still a list — the
# schema is many-to-many by choice (see `app/domain/membership.py`), so the
# shape that carries zero or one entry today can carry more if the agency case
# in doc 06 §2.1 is ever revived.


@router.get("/session", response_model=SessionResponse)
async def session_state(resolved: CurrentSession) -> SessionResponse:
    """The caller's own account, whether or not they have a workspace.

    `/me` cannot answer this. It depends on `CurrentScope`, which requires an
    active workspace — correctly, because it hands back the authority used to
    reach workspace data. But that leaves a signed-in person with no workspace
    unable to retrieve even their own identity, so a client had no way to answer
    "am I logged in?" after a page reload. Every sign-in UI needs that.

    Returns exactly what `/login` returns, from the session cookie rather than
    from credentials. It discloses nothing new: the same user, the same
    memberships, read under the `membership_own_rows` policy that restricts the
    query to the caller's own rows.
    """
    async with _unscoped_session() as db:
        memberships = await memberships_for_user(db, user_id=resolved.user_id)
        email = await _email_for(db, resolved.user_id)

    # The session's pointer, reported only if it still corresponds to a live
    # membership. A revoked membership must not leave the client believing it has
    # an active workspace; `current_scope` would refuse the next real request and
    # the UI would have no idea why.
    known = {m.workspace_id for m in memberships}
    active = resolved.active_workspace_id if resolved.active_workspace_id in known else None

    return SessionResponse(
        user_id=resolved.user_id,
        email=email,
        workspaces=[
            WorkspaceSummary(workspace_id=m.workspace_id, name=m.workspace_name, role=m.role.value)
            for m in memberships
        ],
        active_workspace_id=active,
    )


@router.get("/me", response_model=SessionResponse)
async def me(scope: CurrentScope) -> SessionResponse:
    async with _unscoped_session() as db:
        memberships = await memberships_for_user(db, user_id=scope.user_id)
        email = await _email_for(db, scope.user_id)

    return SessionResponse(
        user_id=scope.user_id,
        email=email,
        workspaces=[
            WorkspaceSummary(workspace_id=m.workspace_id, name=m.workspace_name, role=m.role.value)
            for m in memberships
        ],
        active_workspace_id=scope.workspace_id,
    )


# ── Panel 2: how NEXUS talks to you (`doc/13` §14) ────────────


class PreferencesOut(BaseModel):
    """This person's presentation preferences. **Never authorisation.**

    Every field here is a `persona.*` column, and `doc/06` §2.6 is the rule that
    governs the whole panel: *"no persona field is ever an input to the retrieval
    predicate."* `fields.py` enforces it at import —
    `assert_persona_is_not_authorisation` fails the process if a role-shaped key
    is ever added — and this endpoint is the surface over the same columns.

    So it is scoped per workspace **and** per person, and changing anything here
    cannot widen what anybody sees. That is why it needs no administrator check
    while every other settings panel does.
    """

    language: str
    timezone: str
    communication_style: str | None
    default_landing_screen: str | None
    priority_topics: list[str]


class PreferencesIn(BaseModel):
    language: str = Field(min_length=2, max_length=16)
    timezone: str = Field(min_length=1, max_length=64)
    communication_style: str | None = Field(default=None, max_length=32)
    default_landing_screen: str | None = Field(default=None, max_length=32)


_PREFERENCE_COLUMNS = (
    "language, timezone, communication_style, default_landing_screen, priority_topics"
)


@router.get("/preferences", response_model=PreferencesOut)
async def read_preferences(scope: CurrentScope) -> PreferencesOut:
    """What this person has told us about how to talk to them.

    A row may not exist: the persona is written during onboarding and a person
    who joined by invitation has not been through it. Absent is answered with
    the defaults the columns carry rather than a 404 — the question *"what
    language do you read in?"* has an answer either way, and it is the one the
    product is already using.
    """
    async with scoped_connection(scope) as db:
        row = (
            await db.execute(
                text(
                    f"SELECT {_PREFERENCE_COLUMNS} FROM persona"  # noqa: S608
                    " WHERE user_id = :u"
                ),
                {"u": str(scope.user_id)},
            )
        ).first()

    if row is None:
        return PreferencesOut(
            language="en",
            timezone="Asia/Muscat",
            communication_style=None,
            default_landing_screen=None,
            priority_topics=[],
        )

    return PreferencesOut(
        language=row.language,
        timezone=row.timezone,
        communication_style=row.communication_style,
        default_landing_screen=row.default_landing_screen,
        priority_topics=list(row.priority_topics or []),
    )


@router.put(
    "/preferences",
    response_model=PreferencesOut,
    dependencies=[Depends(require_csrf)],
)
async def update_preferences(payload: PreferencesIn, scope: CurrentScope) -> PreferencesOut:
    """Change them. An upsert, because the row may not exist yet.

    **Not audited**, and that is deliberate rather than an omission. The audit
    trail records what reaches beyond the person doing it — a domain verified, a
    member invited, a department removed, a figure restated. A preference for
    shorter answers reaches nobody, and filling the log with them would bury the
    rows somebody reads it for.

    `priority_topics` is not writable here. It is what the persona interview
    inferred from what the founder said would go wrong, and a checkbox list
    would turn a considered answer into a shopping basket. It is shown, and it
    is changed by talking to the product.
    """
    async with scoped_connection(scope) as db:
        await db.execute(
            text(
                "INSERT INTO persona"
                " (workspace_id, user_id, language, timezone,"
                "  communication_style, default_landing_screen)"
                " VALUES (:ws, :u, :lang, :tz, :style, :landing)"
                " ON CONFLICT (workspace_id, user_id) DO UPDATE"
                "    SET language = EXCLUDED.language,"
                "        timezone = EXCLUDED.timezone,"
                "        communication_style = EXCLUDED.communication_style,"
                "        default_landing_screen = EXCLUDED.default_landing_screen,"
                "        updated_at = now()"
            ),
            {
                "ws": str(scope.workspace_id),
                "u": str(scope.user_id),
                "lang": payload.language,
                "tz": payload.timezone,
                "style": payload.communication_style,
                "landing": payload.default_landing_screen,
            },
        )
        await db.commit()

    return await read_preferences(scope)


# ── Switching entity (ADR 0026) ───────────────────────────────


class WorkspaceChoiceOut(BaseModel):
    workspace_id: UUID
    name: str
    role: str
    active: bool


class WorkspacesOut(BaseModel):
    workspaces: list[WorkspaceChoiceOut]


class SwitchIn(BaseModel):
    workspace_id: UUID


async def _workspaces_for(user_id: UUID, active: UUID | None) -> WorkspacesOut:
    """The list, with `active` computed against an id the caller passes in.

    Split out because `switch_workspace` cannot use the session's own pointer:
    `CurrentSession` is resolved at the start of the request, so after the
    `UPDATE` its `active_workspace_id` still holds the entity being *left*. The
    first version returned that, and the response said the switch had not
    happened while the audit row and the next request both said it had.

    Found by switching in a browser rather than by a test — every test asserted
    the write or the refusal, and none asserted the flag in the reply.
    """
    async with _unscoped_session() as db:
        memberships = await memberships_for_user(db, user_id=user_id)
        rows = {
            row.id: row.name
            for row in (
                await db.execute(
                    text("SELECT id, name FROM workspace WHERE id = ANY(:ids)"),
                    {"ids": [str(m.workspace_id) for m in memberships]},
                )
            ).all()
        }

    return WorkspacesOut(
        workspaces=[
            WorkspaceChoiceOut(
                workspace_id=membership.workspace_id,
                name=rows.get(membership.workspace_id, "Your company"),
                role=membership.role.value,
                active=membership.workspace_id == active,
            )
            for membership in memberships
        ]
    )


@router.get("/workspaces", response_model=WorkspacesOut)
async def list_workspaces(session: CurrentSession) -> WorkspacesOut:
    """The entities this person holds. **Exactly their memberships.**

    Depends on `CurrentSession` rather than `CurrentScope`, because somebody
    switching *away* from a revoked workspace has no valid scope and still needs
    this list — refusing them would trap them on a workspace they cannot open.
    """
    return await _workspaces_for(session.user_id, session.active_workspace_id)


@router.post(
    "/workspace",
    response_model=WorkspacesOut,
    dependencies=[Depends(require_csrf)],
)
async def switch_workspace(payload: SwitchIn, session: CurrentSession) -> WorkspacesOut:
    """Move the session's pointer to another entity this person holds.

    ADR 0026 brings this route back. It was deleted with `doc/11` Q9 — one
    person, one company — along with `_teardown_on_switch` and, with it, **I5's
    cache-invalidation-on-switch requirement**.

    **The membership is re-read here, not trusted from the request.** The
    pointer is only a preference; `current_scope` re-validates it against live
    memberships on every request, so a stale or forged `workspace_id` cannot
    grant anything. Checking it here as well is not redundant — it is the
    difference between a 403 now and a confusing "Workspace access revoked" on
    the next page load.

    **Nothing is cached across the switch, and that is currently true by
    construction.** The only process-level caches are `get_settings`,
    `get_engine` and `get_sessionmaker`, all workspace-agnostic; `scope`,
    including its departments, is rebuilt per request from the active
    membership. `test_nothing_is_cached_across_an_entity_switch` is what stops
    that from silently stopping being true — because entity A's figures under
    entity B's name is the worst failure this product can have, and it would
    look completely normal on screen.
    """
    async with _unscoped_session() as db:
        memberships = await memberships_for_user(db, user_id=session.user_id)
        if not any(m.workspace_id == payload.workspace_id for m in memberships):
            # 403 and not 404: the caller knows this workspace exists, because
            # they named it. What they do not have is a live membership in it.
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "You do not have access to that company.",
            )

        await db.execute(
            text(
                "UPDATE user_session SET active_workspace_id = :w"
                " WHERE id = :s AND revoked_at IS NULL"
            ),
            {"w": str(payload.workspace_id), "s": str(session.session_id)},
        )
        await audit.record(
            db,
            workspace_id=payload.workspace_id,
            action=audit.AuditAction.WORKSPACE_SWITCHED,
            actor_user_id=session.user_id,
            target_type="workspace",
            target_id=str(payload.workspace_id),
            reason="session pointer moved",
        )
        await db.commit()

    log.info("auth.workspace.switched", workspace_id=str(payload.workspace_id))
    # The *new* pointer, not the session's. See `_workspaces_for`.
    return await _workspaces_for(session.user_id, payload.workspace_id)
