"""Supervisor template CRUD."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.enums import BUSINESS_ACTIONS
from app.repositories import supervisor_repo
from app.schemas.supervisor import SupervisorCreate, SupervisorOut, SupervisorUpdate

router = APIRouter(prefix="/api/supervisors", tags=["supervisors"])


@router.get("/available-actions")
async def available_actions():
    return {"actions": list(BUSINESS_ACTIONS)}


@router.get("", response_model=list[SupervisorOut])
async def list_supervisors(session: AsyncSession = Depends(get_session)):
    return await supervisor_repo.list_all(session)


@router.post("", response_model=SupervisorOut, status_code=201)
async def create_supervisor(
    body: SupervisorCreate, session: AsyncSession = Depends(get_session)
):
    unknown = set(body.allowed_actions) - set(BUSINESS_ACTIONS)
    if unknown:
        raise HTTPException(400, f"Unknown actions: {sorted(unknown)}")
    return await supervisor_repo.create(session, **body.model_dump())


@router.get("/{supervisor_id}", response_model=SupervisorOut)
async def get_supervisor(
    supervisor_id: str, session: AsyncSession = Depends(get_session)
):
    supervisor = await supervisor_repo.get(session, supervisor_id)
    if supervisor is None:
        raise HTTPException(404, "Supervisor not found")
    return supervisor


@router.patch("/{supervisor_id}", response_model=SupervisorOut)
async def update_supervisor(
    supervisor_id: str,
    body: SupervisorUpdate,
    session: AsyncSession = Depends(get_session),
):
    supervisor = await supervisor_repo.update(
        session, supervisor_id, **body.model_dump(exclude_unset=True)
    )
    if supervisor is None:
        raise HTTPException(404, "Supervisor not found")
    return supervisor
