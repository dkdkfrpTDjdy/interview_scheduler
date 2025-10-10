import sqlite3
import json
from typing import List, Optional
from datetime import datetime
from models import InterviewRequest, InterviewSlot
from config import Config
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

class DatabaseManager:
    def __init__(self, db_path: str = Config.DATABASE_PATH):
        self.db_path = db_path
        self.init_database()
        self.init_google_sheet()
    
    def init_database(self):
        """데이터베이스 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interview_requests (
                    id TEXT PRIMARY KEY,
                    interviewer_id TEXT NOT NULL,
                    candidate_email TEXT NOT NULL,
                    candidate_name TEXT NOT NULL,
                    position_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    available_slots TEXT,
                    preferred_dates TEXT,
                    selected_slot TEXT,
                    candidate_note TEXT
                )
            """)
    
    def init_google_sheet(self):
        """구글 시트 초기화"""
        try:
            scope = ['https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive']
            
            credentials = Credentials.from_service_account_file(
                Config.GOOGLE_CREDENTIALS_PATH, scopes=scope)
            
            self.gc = gspread.authorize(credentials)
            self.sheet = self.gc.open_by_key(Config.GOOGLE_SHEET_ID).sheet1
            
            # 헤더 설정
            headers = [
                "요청ID", "생성일시", "포지션명", "면접관ID", "면접자명", "면접자이메일",
                "상태", "희망일자", "제안일시", "확정일시", "면접자요청사항", "업데이트일시"
            ]
            
            # 첫 번째 행이 비어있으면 헤더 추가
            if not self.sheet.get_all_values():
                self.sheet.append_row(headers)
                
        except Exception as e:
            print(f"구글 시트 초기화 실패: {e}")
            self.gc = None
            self.sheet = None
    
    def save_interview_request(self, request: InterviewRequest):
        """면접 요청 저장"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO interview_requests 
                (id, interviewer_id, candidate_email, candidate_name, position_name, 
                 status, created_at, updated_at, available_slots, preferred_dates, 
                 selected_slot, candidate_note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.id,
                request.interviewer_id,
                request.candidate_email,
                request.candidate_name,
                request.position_name,
                request.status,
                request.created_at,
                request.updated_at or datetime.now(),
                json.dumps([{"date": slot.date, "time": slot.time, "duration": slot.duration} 
                           for slot in request.available_slots]),
                json.dumps(request.preferred_dates) if request.preferred_dates else None,
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
            if row[8]:  # available_slots
                slots_data = json.loads(row[8])
                available_slots = [InterviewSlot(**slot) for slot in slots_data]
            
            preferred_dates = []
            if row[9]:  # preferred_dates
                preferred_dates = json.loads(row[9])
            
            selected_slot = None
            if row[10]:  # selected_slot
                slot_data = json.loads(row[10])
                selected_slot = InterviewSlot(**slot_data)
            
            return InterviewRequest(
                id=row[0],
                interviewer_id=row[1],
                candidate_email=row[2],
                candidate_name=row[3],
                position_name=row[4],
                status=row[5],
                created_at=datetime.fromisoformat(row[6]),
                updated_at=datetime.fromisoformat(row[7]) if row[7] else None,
                available_slots=available_slots,
                preferred_dates=preferred_dates,
                selected_slot=selected_slot,
                candidate_note=row[11] or ""
            )
    
    def get_all_requests(self) -> List[InterviewRequest]:
        """모든 면접 요청 조회"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id FROM interview_requests ORDER BY created_at DESC")
            request_ids = [row[0] for row in cursor.fetchall()]
            
        return [self.get_interview_request(req_id) for req_id in request_ids if self.get_interview_request(req_id)]
    
    def save_to_google_sheet(self, request: InterviewRequest):
        """구글 시트에 저장"""
        if not self.sheet:
            return False
        
        try:
            # 희망일자 문자열 생성
            preferred_dates_str = ", ".join(request.preferred_dates) if request.preferred_dates else ""
            
            # 제안일시 문자열 생성
            proposed_slots_str = ""
            if request.available_slots:
                proposed_slots_str = " | ".join([f"{slot.date} {slot.time}" for slot in request.available_slots])
            
            # 확정일시
            confirmed_datetime = ""
            if request.selected_slot:
                confirmed_datetime = f"{request.selected_slot.date} {request.selected_slot.time}"
            
            row_data = [
                request.id[:8] + "...",
                request.created_at.strftime('%Y-%m-%d %H:%M'),
                request.position_name,
                request.interviewer_id,
                request.candidate_name,
                request.candidate_email,
                request.status,
                preferred_dates_str,
                proposed_slots_str,
                confirmed_datetime,
                request.candidate_note,
                request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else ""
            ]
            
            self.sheet.append_row(row_data)
            return True
            
        except Exception as e:
            print(f"구글 시트 저장 실패: {e}")
            return False
    
    def update_google_sheet(self, request: InterviewRequest):
        """구글 시트 업데이트"""
        if not self.sheet:
            return False
        
        try:
            # 기존 행 찾기
            all_records = self.sheet.get_all_records()
            short_id = request.id[:8] + "..."
            
            row_index = None
            for i, record in enumerate(all_records):
                if record.get('요청ID') == short_id:
                    row_index = i + 2  # 헤더 행 고려
                    break
            
            if row_index:
                # 업데이트할 데이터
                confirmed_datetime = ""
                if request.selected_slot:
                    confirmed_datetime = f"{request.selected_slot.date} {request.selected_slot.time}"
                
                proposed_slots_str = ""
                if request.available_slots:
                    proposed_slots_str = " | ".join([f"{slot.date} {slot.time}" for slot in request.available_slots])
                
                # 특정 컬럼만 업데이트
                self.sheet.update(f'G{row_index}', request.status)  # 상태
                self.sheet.update(f'I{row_index}', proposed_slots_str)  # 제안일시
                self.sheet.update(f'J{row_index}', confirmed_datetime)  # 확정일시
                self.sheet.update(f'K{row_index}', request.candidate_note)  # 면접자요청사항
                self.sheet.update(f'L{row_index}', 
                                request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else "")  # 업데이트일시
                
                return True
            else:
                # 새로 추가
                return self.save_to_google_sheet(request)
                
        except Exception as e:
            print(f"구글 시트 업데이트 실패: {e}")
            return False
