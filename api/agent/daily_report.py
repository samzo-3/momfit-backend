"""에이전트 라우터. 오늘의 운동 리포트를 만든다."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from core.clock import today_kst
from db.session import get_db
from models.user import User
from repositories.agent.team_activity_reader import (
    TeamActivityReader,
    get_team_activity_reader,
)
from schemas.agent.daily_report import DailyReportRequest, DailyReportResponse
from services.agent import daily_report
from services.agent.llm import LlmClient, get_llm_client

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/daily-report", response_model=DailyReportResponse)
def create_daily_report(
    body: DailyReportRequest | None = None,
    user: User = Depends(get_onboarded_user),
    db: Session = Depends(get_db),
    reader: TeamActivityReader = Depends(get_team_activity_reader),
    llm: LlmClient = Depends(get_llm_client),
) -> DailyReportResponse:
    """오늘(또는 요청한 날짜)의 운동 리포트를 만들어 돌려준다.

    사실은 코드가 팀 테이블에서 계산하고, 문장만 LLM이 쓴다. LLM이 실패하면 숫자로 채운
    대체 문장을 돌려준다. 그 이유는 응답에 넣지 않고 서버 로그에만 남긴다.
    그날 마지막 리포트 뒤로 기록이 그대로면 LLM 없이 그 리포트를 돌려준다. 지난 날짜는 다시 만들지 않는다.
    """
    day = body.date if body and body.date else today_kst()
    result = daily_report.build_daily_report(db, user, day, reader, llm)
    return DailyReportResponse.model_validate(result)
