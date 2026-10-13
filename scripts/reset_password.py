"""
Set a new password for a local account.

There is no forgot-password flow, and for a tool that runs on one laptop
there does not need to be - that would mean an email provider, a token
table and an expiry policy for a problem one prompt solves.

The password is typed, never passed as an argument: an argument would sit in
shell history and in the process list for anyone on the machine to read.

    python scripts/reset_password.py                    # lists accounts
    python scripts/reset_password.py you@example.com    # then prompts
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_BACKEND / "src"))

# Settings read `.env` relative to the working directory, so running this
# from the repository root finds no file, falls back to the default database
# password, and fails with "password authentication failed for user
# outreach" - which reads like a database problem and is a path problem.
os.chdir(_BACKEND)

from outreach.db.models.user import User
from outreach.db.session import session_scope
from outreach.security import hash_password
from sqlalchemy import select

#: Matches the check the signup endpoint makes, so a password set here
#: cannot be one the application would have refused.
MIN_LENGTH = 8


async def show_accounts() -> None:
    async with session_scope() as session:
        users = (await session.execute(select(User).order_by(User.created_at))).scalars()
        rows = list(users)

    if not rows:
        print("No accounts yet. Sign up on the login screen instead.")
        return

    print(f"{len(rows)} account(s):\n")
    for user in rows:
        seen = user.last_login_at.strftime("%Y-%m-%d") if user.last_login_at else "never"
        print(f"  {user.email:<40} {user.name!r:<24} last login: {seen}")
    print("\nRun again with one of these addresses to set a new password.")


async def reset(email: str) -> int:
    email = email.strip().lower()

    async with session_scope() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        if user is None:
            print(f"No account for {email}. Run with no arguments to list them.")
            return 1

        print(f"Setting a new password for {user.email} ({user.name}).")
        password = getpass.getpass("New password: ")
        again = getpass.getpass("Again: ")

        if password != again:
            print("Those did not match. Nothing was changed.")
            return 1
        if len(password) < MIN_LENGTH:
            print(f"Too short - use at least {MIN_LENGTH} characters. Nothing was changed.")
            return 1

        # The application's own hasher, so the stored value is exactly what
        # login expects. Re-implementing argon2 here is how you get a hash
        # that verifies nowhere.
        user.password_hash = hash_password(password)

    print("Done. Log in with the new password.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        asyncio.run(show_accounts())
        return 0
    return asyncio.run(reset(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
