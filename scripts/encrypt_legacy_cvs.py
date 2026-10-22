"""Encrypt legacy plaintext CV files without deleting their originals.

Run after ENCRYPTION_KEY is provisioned and the application is stopped from
accepting uploads. Original plaintext files are retained for operator review;
remove them only after independently verifying encrypted downloads and taking
an encrypted backup.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings  # noqa: E402
from backend.models.database import Candidate, Database  # noqa: E402
from backend.security.cv_encryption import decrypt_cv, encrypt_cv, is_encrypted_cv  # noqa: E402


async def migrate(*, dry_run: bool = False) -> tuple[int, int]:
    settings = get_settings()
    db = Database(settings.database_url)
    await db.init_db()
    encrypted_count = 0
    skipped_count = 0
    try:
        async with db.async_session_factory() as session:
            candidates = (await session.execute(Candidate.__table__.select())).all()
            for row in candidates:
                candidate = await session.get(Candidate, row.id)
                if not candidate or not candidate.cv_file_path:
                    continue
                source = Path(candidate.cv_file_path)
                if not source.is_file():
                    skipped_count += 1
                    continue
                stored = source.read_bytes()
                if is_encrypted_cv(stored):
                    # Authenticate existing ciphertext before considering it migrated.
                    decrypt_cv(stored, settings.encryption_key)
                    skipped_count += 1
                    continue
                encrypted = encrypt_cv(stored, settings.encryption_key)
                if decrypt_cv(encrypted, settings.encryption_key) != stored:
                    raise RuntimeError("Encrypted CV verification failed; original retained")
                if dry_run:
                    encrypted_count += 1
                    continue

                target = source.with_name(f"{source.name}.{uuid.uuid4().hex}.enc")
                fd, temporary = tempfile.mkstemp(prefix=".cv-encrypt-", dir=source.parent)
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(encrypted)
                        output.flush()
                        os.fsync(output.fileno())
                    if decrypt_cv(Path(temporary).read_bytes(), settings.encryption_key) != stored:
                        raise RuntimeError("On-disk encrypted CV verification failed; original retained")
                    os.replace(temporary, target)
                    candidate.cv_file_path = str(target)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    target.unlink(missing_ok=True)
                    raise
                finally:
                    Path(temporary).unlink(missing_ok=True)
                encrypted_count += 1
    finally:
        await db.close()
    return encrypted_count, skipped_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="verify and count without writing files or database rows")
    args = parser.parse_args()
    encrypted, skipped = asyncio.run(migrate(dry_run=args.dry_run))
    print(f"legacy_cv_files_encrypted={encrypted} already_encrypted_or_missing={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
