from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import uuid

@dataclass
class InterviewSlot:
    date: str
    time: str
    duration: int = 60  # 분 단위
    
    def __str__(self):
        return f"{self.date} {self.time} ({self.duration}분)"

@dataclass
class InterviewRequest:
    id: str
    interviewer_id: str
    candidate_email: str
    candidate_name: str
    position_name: str
    status: str
    created_at: datetime
    available_slots: List[InterviewSlot]
    preferred_datetime_slots: List[str] = None  # 인사팀에서 선택한 희망일시 (날짜+시간)
    selected_slot: Optional[InterviewSlot] = None
    candidate_note: str = ""
    updated_at: Optional[datetime] = None
    
    # 하위 호환성을 위해 기존 preferred_dates 속성 유지
    @property
    def preferred_dates(self):
        if self.preferred_datetime_slots:
            return [slot.split(' ')[0] for slot in self.preferred_datetime_slots]
        return []
    
    @classmethod
    def create_new(cls, interviewer_id: str, candidate_email: str, 
                   candidate_name: str, position_name: str, 
                   preferred_datetime_slots: List[str] = None):
        return cls(
            id=str(uuid.uuid4()),
            interviewer_id=interviewer_id,
            candidate_email=candidate_email,
            candidate_name=candidate_name,
            position_name=position_name,
            status="면접관_일정대기",
            created_at=datetime.now(),
            available_slots=[],
            preferred_datetime_slots=preferred_datetime_slots or []
        )
