"""Candidate profile routes."""

from __future__ import annotations

import io
import json
import os
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.api.schemas import CandidateProfile, CVUploadResponse
from backend.config import get_settings
from backend.models.database import Candidate, User
from backend.matching.scoring import rescore_candidate
from backend.security.cv_encryption import (
    CVEncryptionError,
    LegacyPlaintextCVError,
    decrypt_cv,
    encrypt_cv,
)

router = APIRouter()

MAX_CV_BYTES = 10 * 1024 * 1024
_CV_CHUNK_BYTES = 64 * 1024
_ALLOWED_CV_SUFFIXES = {".pdf", ".doc", ".docx"}
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _validate_cv_signature(content: bytes, suffix: str) -> None:
    """Validate file magic independently of the client-supplied MIME type."""
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="File is not a valid PDF")
        return
    if suffix == ".doc":
        if not content.startswith(_OLE_MAGIC):
            raise HTTPException(status_code=400, detail="File is not a valid DOC document")
        return
    if suffix == ".docx":
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(status_code=400, detail="File is not a valid DOCX document")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
        except (zipfile.BadZipFile, OSError) as exc:
            raise HTTPException(status_code=400, detail="File is not a valid DOCX document") from exc
        if "[Content_Types].xml" not in names or not any(name.startswith("word/") for name in names):
            raise HTTPException(status_code=400, detail="File is not a valid DOCX document")


async def _candidate_for_user(db: AsyncSession, user_id: str) -> Candidate | None:
    result = await db.execute(select(Candidate).where(Candidate.user_id == user_id))
    return result.scalars().first()


def _candidate_to_response(c: Candidate) -> CandidateProfile:
    return CandidateProfile(
        id=c.id,
        name=c.name,
        email=c.email,
        location="",
        preferred_locations=c.preferred_locations_list,
        preferred_roles=c.preferred_roles_list if hasattr(c, "preferred_roles_list") else [],
        skills=c.skills_list,
        experience_level=c.experience_level or "",
        experience_years=None,
        salary_min=c.salary_min,
        salary_max=c.salary_max,
        remote_ok=c.remote_preference == "full",
        bio="",
        updated_at=c.updated_at,
    )


@router.get("/profile", response_model=CandidateProfile)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> CandidateProfile:
    candidate = await _candidate_for_user(db, _user["user_id"])
    if not candidate:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _candidate_to_response(candidate)


@router.post("/profile", response_model=CandidateProfile)
async def create_or_update_profile(
    profile: CandidateProfile,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> CandidateProfile:
    candidate = await _candidate_for_user(db, _user["user_id"])

    if candidate:
        candidate.name = profile.name or candidate.name
        candidate.email = profile.email or candidate.email
        candidate.skills_list = profile.skills
        candidate.preferred_locations_list = profile.preferred_locations
        try:
            candidate.preferred_roles_list = getattr(profile, "preferred_roles", []) or []
        except Exception:
            pass
        candidate.experience_level = profile.experience_level
        candidate.salary_min = int(profile.salary_min) if profile.salary_min and profile.salary_min > 0 else None
        candidate.salary_max = int(profile.salary_max) if profile.salary_max and profile.salary_max > 0 else None
        candidate.remote_preference = "full" if profile.remote_ok else "onsite"
    else:
        user_result = await db.execute(select(User).where(User.id == _user["user_id"]))
        user = user_result.scalars().first()
        if not user:
            user = User(email=_user["email"], hashed_password="placeholder")
            db.add(user)
            await db.flush()

        candidate = Candidate(
            user_id=user.id,
            name=profile.name,
            email=profile.email,
            skills=json.dumps(profile.skills),
            preferred_locations=json.dumps(profile.preferred_locations),
            preferred_roles=json.dumps(getattr(profile, "preferred_roles", []) or []),
            experience_level=profile.experience_level,
            salary_min=int(profile.salary_min) if profile.salary_min and profile.salary_min > 0 else None,
            salary_max=int(profile.salary_max) if profile.salary_max and profile.salary_max > 0 else None,
            remote_preference="full" if profile.remote_ok else "onsite",
        )
        db.add(candidate)

    await db.flush()
    await rescore_candidate(db, candidate)
    await db.commit()
    await db.refresh(candidate)
    return _candidate_to_response(candidate)


@router.post("/cv", response_model=CVUploadResponse)
async def upload_cv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> CVUploadResponse:
    candidate = await _candidate_for_user(db, _user["user_id"])
    if not candidate:
        raise HTTPException(status_code=400, detail="Create a candidate profile before uploading a CV")
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    allowed_types = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, DOC, DOCX",
        )

    # Bound the read so a malicious or accidental huge upload cannot force the
    # entire body into memory before the limit is checked.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CV_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_CV_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"CV exceeds the {MAX_CV_BYTES // (1024 * 1024)} MB limit",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    # Never trust the client filename: strip any path components and derive the
    # stored name from a server-generated UUID so uploads cannot escape the
    # storage directory (path traversal) or collide.
    safe_name = os.path.basename(file.filename or "").strip()
    suffix = Path(safe_name).suffix.lower()
    if suffix not in _ALLOWED_CV_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{suffix or safe_name}'. Allowed: .pdf, .doc, .docx",
        )

    # The extension and the client Content-Type are both attacker-controlled;
    # the file signature is the authoritative format check.
    _validate_cv_signature(content, suffix)

    settings = get_settings()
    try:
        encrypted_content = encrypt_cv(content, settings.encryption_key)
    except CVEncryptionError as exc:
        raise HTTPException(status_code=503, detail="CV encryption is not configured") from exc

    dest_dir = Path(settings.cv_storage_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    cv_path = str(dest_dir / f"{uuid.uuid4().hex}{suffix}")
    with open(cv_path, "wb") as f:
        f.write(encrypted_content)

    old_cv_path = candidate.cv_file_path
    candidate.cv_file_path = cv_path
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if os.path.exists(cv_path):
            os.remove(cv_path)
        raise
    if old_cv_path and old_cv_path != cv_path and os.path.exists(old_cv_path):
        os.remove(old_cv_path)

    return CVUploadResponse(
        filename=file.filename,
        size=len(content),
        content_type=file.content_type or "application/octet-stream",
        message="CV uploaded successfully",
    )


@router.delete("/cv")
async def delete_cv(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> dict[str, str]:
    candidate = await _candidate_for_user(db, _user["user_id"])
    if candidate and candidate.cv_file_path:
        if os.path.exists(candidate.cv_file_path):
            os.remove(candidate.cv_file_path)
        candidate.cv_file_path = None
        await db.commit()
    return {"message": "CV deleted successfully"}


@router.get("/cv")
async def get_cv_metadata(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> dict[str, str | int | None]:
    candidate = await _candidate_for_user(db, _user["user_id"])
    path = Path(candidate.cv_file_path) if candidate and candidate.cv_file_path else None
    if not path or not path.is_file():
        return {"filename": None, "size": None}
    return {"filename": path.name, "size": path.stat().st_size}


@router.get("/cv/file")
async def download_cv(
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> FileResponse:
    candidate = await _candidate_for_user(db, _user["user_id"])
    path = Path(candidate.cv_file_path) if candidate and candidate.cv_file_path else None
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="No CV uploaded")
    try:
        plaintext = decrypt_cv(path.read_bytes(), get_settings().encryption_key)
    except LegacyPlaintextCVError as exc:
        raise HTTPException(
            status_code=409,
            detail="This CV needs the administrator's legacy-file encryption migration before it can be downloaded",
        ) from exc
    except CVEncryptionError as exc:
        raise HTTPException(status_code=500, detail="Stored CV could not be decrypted") from exc

    return Response(
        content=plaintext,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )
