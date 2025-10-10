import sqlite3
import json
from typing import List, Optional
from datetime import datetime
from models import InterviewRequest, InterviewSlot
from config import Config

class DatabaseManager:
    def __init__(self, db_path: str = Config.DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """데이터베이스 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interview_requests (
                    id TEXT PRIMARY KEY,
                    interviewer_id TEXT NOT NULL,
                    candidate_email TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    available_slots TEXT,  -- JSON 형태로 저장
                    selected_slot TEXT,    -- JSON 형태로 저장
                    candidate_note TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interviewers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    department TEXT
                )
            """)
    
    def save_interview_request(self, request: InterviewRequest):
        """면접 요청 저장"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO interview_requests 
                (id, interviewer_id, candidate_email, status, created_at, updated_at, 
                 available_slots, selected_slot, candidate_note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.id,
                request.interviewer_id,
                request.candidate_email,
                request.status,
                request.created_at,
                request.updated_at or datetime.now(),
                json.dumps([{"date": slot.date, "time": slot.time, "duration": slot.duration} 
                           for slot in request.available_slots]),
                json.dumps({"date": request.selected_slot.date, "time": request.selected_slot.time, 
                           "duration": request.selected_slot.duration}) if request.selected_slot else None,
                request.candidate_note
            ))
    
    def get_interview_request(self, request_id: str) -> Optional[InterviewRequest]:
        """면접 요청 조회"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM interview_requests WHERE id = ?", (request_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # JSON 데이터 파싱
            available_slots = []
            if row[6]:  # available_slots
                slots_data = json.loads(row[6])
                available_slots = [InterviewSlot(**slot) for slot in slots_data]
            
            selected_slot = None
            if row[7]:  # selected_slot
                slot_data = json.loads(row[7])
                selected_slot = InterviewSlot(**slot_data)
            
            return InterviewRequest(
                id=row[0],
                interviewer_id=row[1],
                candidate_email=row[2],
                status=row[3],
                created_at=datetime.fromisoformat(row[4]),
                updated_at=datetime.fromisoformat(row[5]) if row[5] else None,
                available_slots=available_slots,
                selected_slot=selected_slot,
                candidate_note=row[8] or ""
            )
    
    def get_all_requests(self) -> List[InterviewRequest]:
        """모든 면접 요청 조회"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id FROM interview_requests ORDER BY created_at DESC")
            request_ids = [row[0] for row in cursor.fetchall()]
            
        return [self.get_interview_request(req_id) for req_id in request_ids if self.get_interview_request(req_id)]