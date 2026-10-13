"""Sign up, sign in, sign out."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Response, status

from outreach import mailer, security
from outreach.api.deps import CurrentUser, DbSession
from outreach.config import settings
from outreach.db.models.user import User
from outreach.db.repositories import password_resets as reset_repo
from outreach.db.repositories import users as repo
from outreach.schemas.auth import (
    ForgotPasswordIn,
    ForgotPasswordOut,
    LoginIn,
    ResetPasswordIn,
    SignUpIn,
    UserOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, user: User) -> None:
    """
    httpOnly, so no script can read it. SameSite=lax, so it survives a normal
    navigation but is not sent on a cross-site POST.
    """
    response.set_cookie(
        key=security.COOKIE_NAME,
        value=security.create_session_token(user.id),
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def sign_up(payload: SignUpIn, response: Response, session: DbSession) -> User:
    """Create an account and sign in immediately. Nobody wants two forms."""
    email = repo.normalise_email(payload.email)

    if await repo.get_by_email(session, email) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "There is already an account with that email. Try signing in instead.",
        )

    user = await repo.add(
        session,
        User(
            email=email,
            name=payload.name,
            password_hash=security.hash_password(payload.password),
            last_login_at=datetime.now(UTC),
        ),
    )

    _set_session_cookie(response, user)
    log.info("auth.signed_up", user_id=str(user.id))
    return user


@router.post("/login", response_model=UserOut)
async def log_in(payload: LoginIn, response: Response, session: DbSession) -> User:
    """
    Sign in.

    A wrong email and a wrong password give the same message on purpose:
    "no account with that email" is a free account-existence check for
    anyone with a list of addresses.
    """
    wrong = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "That email and password do not match.",
    )

    user = await repo.get_by_email(session, payload.email)
    if user is None:
        # Hash anyway. Returning instantly for unknown emails and slowly for
        # known ones leaks exactly what the shared message is hiding.
        security.hash_password(payload.password)
        raise wrong

    if not security.verify_password(payload.password, user.password_hash):
        raise wrong

    # Argon2's cost parameters can be raised later. Anyone who signs in after
    # that gets upgraded here, without being asked to change their password.
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(payload.password)

    user.last_login_at = datetime.now(UTC)

    _set_session_cookie(response, user)
    log.info("auth.signed_in", user_id=str(user.id))
    return user


@router.post("/forgot-password", response_model=ForgotPasswordOut)
async def forgot_password(
    payload: ForgotPasswordIn, session: DbSession
) -> ForgotPasswordOut:
    """
    Start a password reset.

    Answers exactly the same way whether or not the address has an account.
    Saying "no account with that email" here would hand anyone with a list
    of addresses a free way to find out which of them are customers - the
    same reason sign-in refuses to tell wrong-email from wrong-password.
    """
    same_answer = "If that email has an account, a reset link is on its way."

    # Both `message` and `sent` are decided before we know whether the
    # account exists, and they are the same either way. They describe this
    # deployment's mail setup, which is not a secret; the account is.
    #
    # Getting this wrong is subtle: answering "sent: true" for an unknown
    # address while a real one answered "sent: false, here is your link"
    # tells an attacker precisely what the shared message is there to hide.
    # The link is the only field that may differ, and it appears only on a
    # local machine that cannot send mail at all.
    configured = mailer.is_configured()

    user = await repo.get_by_email(session, payload.email)
    if user is None:
        log.info("auth.reset_requested_unknown")
        return ForgotPasswordOut(message=same_answer, sent=configured)

    # A new link kills any older one. Otherwise every request made while
    # flustered leaves another working key in another email.
    await reset_repo.invalidate_open(session, user.id)

    token, token_hash = security.new_reset_token()
    await reset_repo.add(session, user.id, token_hash, security.reset_expiry())

    link = mailer.reset_link(token)
    sent = await mailer.send_password_reset(user.email, link)

    log.info("auth.reset_requested", user_id=str(user.id), sent=sent)

    # Handing the link back is a hole - anyone could reset anyone's password
    # by asking - so it happens only when this is a local machine that has
    # no way to send mail. Both conditions, not either.
    show_link = not sent and settings.app_env == "local"
    return ForgotPasswordOut(
        message=same_answer,
        sent=sent,
        link=link if show_link else None,
    )


@router.post("/reset-password", response_model=UserOut)
async def reset_password(
    payload: ResetPasswordIn, response: Response, session: DbSession
) -> User:
    """
    Set a new password from a reset link, and sign in.

    Signing in immediately is deliberate: somebody who has just proved they
    control the mailbox and chosen a new password has done the work twice
    already, and a login form here is the step where people give up.
    """
    reset = await reset_repo.get_usable(
        session, security.hash_reset_token(payload.token)
    )
    if reset is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That reset link has expired or has already been used. "
            "Ask for a new one.",
        )

    user = await repo.get(session, reset.user_id)
    if user is None:
        # The account was deleted between the request and the click.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That account no longer exists."
        )

    user.password_hash = security.hash_password(payload.password)
    await reset_repo.mark_used(session, reset)

    # Every other open reset for this account goes too. If the request was
    # made because somebody else had access, one used link must not leave
    # their spare still working.
    await reset_repo.invalidate_open(session, user.id)

    user.last_login_at = datetime.now(UTC)
    _set_session_cookie(response, user)
    log.info("auth.password_reset", user_id=str(user.id))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def log_out(response: Response) -> None:
    response.delete_cookie(security.COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    """Who is signed in. The frontend calls this once on load."""
    return user
