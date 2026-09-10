"""Rolling memory persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RunMemory


async def get(session: AsyncSession, run_id: str) -> RunMemory | None:
    return await session.get(RunMemory, run_id)


async def ensure(session: AsyncSession, run_id: str) -> RunMemory:
    memory = await session.get(RunMemory, run_id)
    if memory is None:
        memory = RunMemory(run_id=run_id, summary="", key_facts={}, open_issues=[])
        session.add(memory)
        await session.commit()
        await session.refresh(memory)
    return memory


async def save(
    session: AsyncSession,
    run_id: str,
    *,
    summary: str | None = None,
    key_facts: dict | None = None,
    open_issues: list | None = None,
    wake_guidance: str | None = None,
    compacted_through_seq: int | None = None,
    compacted: bool = False,
) -> RunMemory:
    memory = await ensure(session, run_id)
    if summary is not None:
        memory.summary = summary
    if key_facts is not None:
        memory.key_facts = key_facts
    if open_issues is not None:
        memory.open_issues = open_issues
    if wake_guidance is not None:
        memory.wake_guidance = wake_guidance
    if compacted_through_seq is not None:
        memory.compacted_through_seq = compacted_through_seq
    if compacted:
        memory.compaction_count = (memory.compaction_count or 0) + 1
    memory.version = (memory.version or 0) + 1
    await session.commit()
    await session.refresh(memory)
    return memory
