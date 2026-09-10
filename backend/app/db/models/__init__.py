"""Importing this package registers every table on ``Base.metadata``."""

from app.db.models.activity import Activity
from app.db.models.instruction import RunInstruction
from app.db.models.memory import RunMemory
from app.db.models.output import RunOutput
from app.db.models.run import Run
from app.db.models.supervisor import Supervisor

__all__ = [
    "Activity",
    "Run",
    "RunInstruction",
    "RunMemory",
    "RunOutput",
    "Supervisor",
]
