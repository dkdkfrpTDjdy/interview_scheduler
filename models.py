from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
class TimeRange:
    """시간 범위 (예: 14:00~18:00)"""
    date: str
    start_time: str  # "14:00"
    end_time: str    # "18:00"
    
    def generate_30min_slots(self) -> List[InterviewSlot]:
        """30분 단위 타임슬롯 생성"""
        slots = []
        
        # 시작/종료 시간 파싱
        start_hour, start_min = map(int, self.start_time.split(':'))
        end_hour, end_min = map(int, self.end_time.split(':'))
        
        current = datetime.strptime(self.start_time, '%H:%M')
        end = datetime.strptime(self.end_time, '%H:%M')
        
        while current < end:
            slot_time = current.strftime('%H:%M')
            slots.append(InterviewSlot(
                date=self.date,
                time=slot_time,
                duration=30  # 고정 30분
            ))
            current += timedelta(minutes=30)
        
        return slots
    
    def __str__(self):
        return f"{self.date} {self.start_time}~{self.end_time}"

@dataclass
class InterviewRequest:
    id: str
    interviewer_id: str
    candidate_email: str
    candidate_name: str
    position_name: str
    status: str
    created_at: datetime
    available_slots: List[InterviewSlot] = field(default_factory=list)
    preferred_dates: List[str] = field(default_factory=list)
    preferred_datetime_slots: List[str] = field(default_factory=list)  # ✅ 추가
    preferred_time_ranges: List[TimeRange] = field(default_factory=list)
    selected_slot: Optional[InterviewSlot] = None
    candidate_note: str = ""
    updated_at: Optional[datetime] = None

    @classmethod
    def create_new(cls, interviewer_id: str, candidate_email: str, 
                   candidate_name: str, position_name: str, 
                   preferred_dates: List[str] = None,
                   preferred_datetime_slots: List[str] = None,
                   preferred_time_ranges: List[TimeRange] = None):
        return cls(
            id=str(uuid.uuid4()),
            interviewer_id=interviewer_id,
            candidate_email=candidate_email,
            candidate_name=candidate_name,
            position_name=position_name,
            status="면접관_일정대기",
            created_at=datetime.now(),
            available_slots=[],
            preferred_dates=preferred_dates or [],
            preferred_datetime_slots=preferred_datetime_slots or [],
            preferred_time_ranges=preferred_time_ranges or []
        )