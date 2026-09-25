from typing import Optional

from sqlalchemy.orm import Session

from .models import AuditLog


def audit(db: Session, username: str, action: str, entity: str, entity_id: str = "", detail: Optional[dict] = None) -> None:
    db.add(AuditLog(username=username, action=action, entity=entity, entity_id=entity_id, detail=detail))
