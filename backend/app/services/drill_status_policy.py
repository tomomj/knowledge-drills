from app.schemas import DrillRunStatus

DISTRIBUTABLE_DRILL_STATUSES = frozenset(
    {
        DrillRunStatus.READY,
        DrillRunStatus.ANALYZING,
        DrillRunStatus.ANALYZED,
    }
)


def is_distributable_drill_status(status: DrillRunStatus) -> bool:
    return status in DISTRIBUTABLE_DRILL_STATUSES
