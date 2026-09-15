from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from omni_retail.ai import EXAMPLE_QUESTIONS, answer_question
from omni_retail.api.dependencies import get_session
from omni_retail.api.schemas import AgentResponseOut, AskRequest, ExampleQuestionsResponse

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post("/ask", response_model=AgentResponseOut)
def ask(request: AskRequest, session: Session = Depends(get_session)) -> AgentResponseOut:
    """Ask the AI Business Analyst a natural-language question. Read-only -- never modifies data."""
    return answer_question(session, request.question)


@router.get("/examples", response_model=ExampleQuestionsResponse)
def get_examples() -> ExampleQuestionsResponse:
    """Example questions the agent can currently answer, for the UI's suggestion chips."""
    return ExampleQuestionsResponse(questions=EXAMPLE_QUESTIONS)
