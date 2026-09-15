from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from omni_retail.actions import ActionNotProposedError, approve_action, create_proposals, reject_action
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import AgentActionOut, ApproveActionRequest, RejectActionRequest
from omni_retail.models import ActionStatus
from omni_retail.models.agent_action import AgentAction

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.post("/generate", response_model=list[AgentActionOut])
def generate_actions(session: Session = Depends(get_session)) -> list[AgentActionOut]:
    """Runs the AI's proposal pass against current alerts and persists any
    new ones. Returns only the proposals just created; existing proposals
    (and their approval state) are never touched or duplicated."""
    return create_proposals(session)


@router.get("", response_model=list[AgentActionOut])
def list_actions(status: Optional[str] = None, session: Session = Depends(get_session)) -> list[AgentActionOut]:
    """All agent actions, most recently created first. Optionally filter by status."""
    stmt = select(AgentAction).order_by(AgentAction.created_at.desc())
    if status is not None:
        try:
            status_enum = ActionStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status!r}") from None
        stmt = stmt.where(AgentAction.status == status_enum)
    return session.execute(stmt).scalars().all()


@router.get("/{action_id}", response_model=AgentActionOut)
def get_action(action_id: int, session: Session = Depends(get_session)) -> AgentActionOut:
    action = session.get(AgentAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found.")
    return action


@router.post("/{action_id}/approve", response_model=AgentActionOut)
def approve(
    action_id: int, payload: ApproveActionRequest, session: Session = Depends(get_session)
) -> AgentActionOut:
    """Approves a proposed action and immediately executes it (simulated)."""
    try:
        return approve_action(session, action_id, payload.decided_by, payload.edited_parameters)
    except LookupError:
        raise HTTPException(status_code=404, detail="Action not found.") from None
    except ActionNotProposedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/{action_id}/reject", response_model=AgentActionOut)
def reject(action_id: int, payload: RejectActionRequest, session: Session = Depends(get_session)) -> AgentActionOut:
    try:
        return reject_action(session, action_id, payload.decided_by, payload.reason)
    except LookupError:
        raise HTTPException(status_code=404, detail="Action not found.") from None
    except ActionNotProposedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
