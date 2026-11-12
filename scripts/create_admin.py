#!/usr/bin/env python3
"""Securely create or promote the first administrator account.

Administrator access is never granted automatically: registration always
creates a regular ``user``. Run this CLI once on the server (or in the
application container) to provision an operator account.

The password is read interactively with :func:`getpass` and is never accepted as
a command-line argument, so it does not leak through shell history or process
listings. For non-interactive provisioning, pipe the password on stdin with
``--password-stdin`` and make sure the value comes from a secret manager.

Usage::

    python scripts/create_admin.py --email admin@example.com
    python scripts/create_admin.py --email admin@example.com --password-stdin < /run/secrets/admin_password
    python scripts/create_admin.py --email existing@example.com --promote

Exit codes: 0 success, 1 invalid input, 2 account/policy failure.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.models.database import Database, User  # noqa: E402
from backend.security import hash_password, validate_password_strength  # noqa: E402


def _read_password(password_stdin: bool) -> str:
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise ValueError("No password received on stdin")
        return password

    if not sys.stdin.isatty():
        raise ValueError(
            "Refusing to read a password from a non-interactive terminal. "
            "Use --password-stdin with a value supplied by a secret manager."
        )
    first = getpass.getpass("New administrator password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("Passwords do not match")
    return first


async def _provision(email: str, password: str | None, promote_only: bool) -> int:
    settings = get_settings()
    db = Database(settings.database_url)
    await db.init_db()
    try:
        async with db.async_session_factory() as session:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalars().first()

            if user is not None and promote_only:
                if user.role != "admin":
                    user.role = "admin"
                    await session.commit()
                print(f"Promoted existing account {email} to administrator.")
                return 0

            if user is not None:
                # Never overwrite an existing password implicitly.
                user.role = "admin"
                await session.commit()
                print(
                    f"Account {email} already exists and was promoted to administrator. "
                    "Its password was left unchanged."
                )
                return 0

            if not password:
                raise ValueError("A password is required to create a new administrator")

            validate_password_strength(password, email=email)
            session.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    role="admin",
                    token_version=0,
                    is_active=True,
                    is_verified=True,
                )
            )
            await session.commit()
            print(f"Created administrator account {email}.")
            return 0
    finally:
        await db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create or promote a Task Sniffer administrator account.",
    )
    parser.add_argument("--email", help="Administrator email address")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Promote an existing account instead of creating a new one",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from stdin instead of prompting (for secret managers)",
    )
    args = parser.parse_args(argv)

    email = (args.email or input("Administrator email: ")).strip().lower()
    if not email or "@" not in email:
        print("A valid email address is required.", file=sys.stderr)
        return 1

    try:
        password = None
        if not args.promote:
            password = _read_password(args.password_stdin)
        return asyncio.run(_provision(email, password, args.promote))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        # Do not echo connection strings or password material.
        print(f"Failed to provision administrator: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
