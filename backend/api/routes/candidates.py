"""Candidate profile routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.api.schemas import CandidateProfile, CVUploadResponse
from backend.models.database import Candidate, User

router = APIRouter()


def _candidate_to_response(c: Candidate) -> CandidateProfile:
    return CandidateProfile(
        id=c.id,
        name=c.name,
        email=c.email,
        location="",
        preferred_locations=c.preferred_locations_list,
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
    result = await db.execute(
        select(Candidate).join(User, Candidate.user_id == User.id).where(User.email == _user["email"])
    )
    candidate = result.scalars().first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _candidate_to_response(candidate)


@router.post("/profile", response_model=CandidateProfile)
async def create_or_update_profile(
    profile: CandidateProfile,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> CandidateProfile:
    result = await db.execute(
        select(Candidate).join(User, Candidate.user_id == User.id).where(User.email == _user["email"])
    )
    candidate = result.scalars().first()

    if candidate:
        candidate.name = profile.name or candidate.name
        candidate.email = profile.email or candidate.email
        candidate.skills_list = profile.skills
        candidate.preferred_locations_list = profile.preferred_locations
        candidate.preferred_roles_list = profile.preferred_roles if hasattr(profile, "preferred_roles") else []
        candidate.experience_level = profile.experience_level
        candidate.salary_min = int(profile.salary_min) if profile.salary_min else candidate.salary_min
        candidate.salary_max = int(profile.salary_max) if profile.salary_max else candidate.salary_max
        candidate.remote_preference = "full" if profile.remote_ok else "onsite"
    else:
        user_result = await db.execute(select(User).where(User.email == _user["email"]))
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
            experience_level=profile.experience_level,
            salary_min=int(profile.salary_min) if profile.salary_min else None,
            salary_max=int(profile.salary_max) if profile.salary_max else None,
            remote_preference="full" if profile.remote_ok else "onsite",
        )
        db.add(candidate)

    await db.commit()
    await db.refresh(candidate)
    return _candidate_to_response(candidate)


@router.post("/cv", response_model=CVUploadResponse)
async def upload_cv(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> CVUploadResponse:
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

    content = await file.read()
    cv_path = f"/tmp/cvs/{file.filename}"
    import os
    os.makedirs("/tmp/cvs", exist_ok=True)
    with open(cv_path, "wb") as f:
        f.write(content)

    result = await db.execute(
        select(Candidate).join(User, Candidate.user_id == User.id).where(User.email == _user["email"])
    )
    candidate = result.scalars().first()
    if candidate:
        candidate.cv_file_path = cv_path
        await db.commit()

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
    result = await db.execute(
        select(Candidate).join(User, Candidate.user_id == User.id).where(User.email == _user["email"])
    )
    candidate = result.scalars().first()
    if candidate and candidate.cv_file_path:
        import os
        if os.path.exists(candidate.cv_file_path):
            os.remove(candidate.cv_file_path)
        candidate.cv_file_path = None
        await db.commit()
    return {"message": "CV deleted successfully"}
