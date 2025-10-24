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
    
    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            'date': self.date,
            'time': self.time,
            'duration': self.duration
        }
    
@dataclass
class TimeRange:
    """시간 범위 (예: 14:00~18:00)"""
    date: str
    start_time: str  # "14:00"
    end_time: str    # "18:00"
    
    def generate_30min_slots(self) -> List[InterviewSlot]:
        """30분 단위 타임슬롯 생성"""
        slots = []
        
        try:
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
        except Exception as e:
            print(f"슬롯 생성 실패: {e}")
        
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
    preferred_datetime_slots: List[str] = field(default_factory=list)
    preferred_time_ranges: List[TimeRange] = field(default_factory=list)
    selected_slot: Optional[InterviewSlot] = None
    candidate_note: str = ""
    updated_at: Optional[datetime] = None
    detailed_position_name: str = ""  # ✅ 상세 공고명 추가
    candidate_phone: str = ""  # ✅ 전화번호 필드 추가

    def __post_init__(self):
        """초기화 후 데이터 타입 변환"""
        # datetime 변환
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)
        if isinstance(self.updated_at, str):
            self.updated_at = datetime.fromisoformat(self.updated_at)
        
        # available_slots 변환
        if self.available_slots and isinstance(self.available_slots[0], dict):
            self.available_slots = [
                InterviewSlot(**slot) if isinstance(slot, dict) else slot
                for slot in self.available_slots
            ]
        
        # selected_slot 변환
        if self.selected_slot and isinstance(self.selected_slot, dict):
            self.selected_slot = InterviewSlot(**self.selected_slot)
        
        # preferred_time_ranges 변환
        if self.preferred_time_ranges and isinstance(self.preferred_time_ranges[0], dict):
            self.preferred_time_ranges = [
                TimeRange(**tr) if isinstance(tr, dict) else tr
                for tr in self.preferred_time_ranges
            ]

    @classmethod
    def create_new(cls, interviewer_id: str, candidate_email: str, 
                   candidate_name: str, position_name: str, 
                   preferred_dates: List[str] = None,
                   preferred_datetime_slots: List[str] = None,
                   preferred_time_ranges: List[TimeRange] = None,
                   detailed_position_name: str = "",
                   candidate_phone: str = ""):  # ✅ 전화번호 매개변수 추가
        from utils import generate_request_id
        
        return cls(
            id=generate_request_id(),
            interviewer_id=interviewer_id,
            candidate_email=candidate_email,
            candidate_name=candidate_name,
            position_name=position_name,
            status="면접관_일정대기",
            created_at=datetime.now(),
            available_slots=[],
            preferred_dates=preferred_dates or [],
            preferred_datetime_slots=preferred_datetime_slots or [],
            preferred_time_ranges=preferred_time_ranges or [],
            detailed_position_name=detailed_position_name,
            candidate_phone=candidate_phone  # ✅ 전화번호 추가
        )
