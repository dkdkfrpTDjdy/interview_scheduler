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
                    preferred_datetime_slots TEXT,
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
            
            # 헤더 설정 (더 상세하게)
            headers = [
                "요청ID", "생성일시", "포지션명", "면접관ID", "면접관이름", "면접자명", 
                "면접자이메일", "상태", "상태변경일시", "희망일시목록", "제안일시목록", 
                "확정일시", "면접자요청사항", "마지막업데이트", "처리소요시간", "비고"
            ]
            
            # 첫 번째 행이 비어있거나 헤더가 다르면 새로 설정
            existing_headers = self.sheet.row_values(1)
            if not existing_headers or existing_headers != headers:
                self.sheet.clear()
                self.sheet.append_row(headers)
                # 헤더 스타일링
                self.sheet.format('1:1', {
                    'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 0.9},
                    'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}}
                })
                
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
                 status, created_at, updated_at, available_slots, preferred_datetime_slots, 
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
                json.dumps(request.preferred_datetime_slots) if request.preferred_datetime_slots else None,
                json.dumps({"date": request.selected_slot.date, "time": request.selected_slot.time, 
                           "duration": request.selected_slot.duration}) if request.selected_slot else None,
                request.candidate_note
            ))
        
        # 자동으로 구글 시트 업데이트
        self.update_google_sheet(request)
    
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
            
            preferred_datetime_slots = []
            if row[9]:  # preferred_datetime_slots
                preferred_datetime_slots = json.loads(row[9])
            
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
                preferred_datetime_slots=preferred_datetime_slots,
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
        """구글 시트에 새로운 요청 저장"""
        if not self.sheet:
            return False
        
        try:
            from utils import get_employee_info
            interviewer_info = get_employee_info(request.interviewer_id)
            
            # 희망일시 문자열 생성
            preferred_datetime_str = ""
            if request.preferred_datetime_slots:
                preferred_datetime_str = " | ".join(request.preferred_datetime_slots)
            
            # 제안일시 문자열 생성
            proposed_slots_str = ""
            if request.available_slots:
                proposed_slots_str = " | ".join([f"{slot.date} {slot.time}({slot.duration}분)" for slot in request.available_slots])
            
            # 확정일시
            confirmed_datetime = ""
            if request.selected_slot:
                confirmed_datetime = f"{request.selected_slot.date} {request.selected_slot.time}({request.selected_slot.duration}분)"
            
            # 처리 소요시간 계산
            processing_time = ""
            if request.updated_at and request.status == Config.Status.CONFIRMED:
                time_diff = request.updated_at - request.created_at
                hours = int(time_diff.total_seconds() // 3600)
                processing_time = f"{hours}시간" if hours > 0 else "1시간 미만"
            
            row_data = [
                request.id[:8] + "...",  # 요청ID
                request.created_at.strftime('%Y-%m-%d %H:%M'),  # 생성일시
                request.position_name,  # 포지션명
                request.interviewer_id,  # 면접관ID
                interviewer_info['name'],  # 면접관이름
                request.candidate_name,  # 면접자명
                request.candidate_email,  # 면접자이메일
                request.status,  # 상태
                request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else request.created_at.strftime('%Y-%m-%d %H:%M'),  # 상태변경일시
                preferred_datetime_str,  # 희망일시목록
                proposed_slots_str,  # 제안일시목록
                confirmed_datetime,  # 확정일시
                request.candidate_note,  # 면접자요청사항
                datetime.now().strftime('%Y-%m-%d %H:%M'),  # 마지막업데이트
                processing_time,  # 처리소요시간
                ""  # 비고
            ]
            
            self.sheet.append_row(row_data)
            
            # 상태별 색상 적용
            row_num = len(self.sheet.get_all_values())
            self._apply_status_formatting(row_num, request.status)
            
            return True
            
        except Exception as e:
            print(f"구글 시트 저장 실패: {e}")
            return False
    
    def update_google_sheet(self, request: InterviewRequest):
        """구글 시트 실시간 업데이트"""
        if not self.sheet:
            return False
        
        try:
            from utils import get_employee_info
            
            # 기존 행 찾기
            all_records = self.sheet.get_all_records()
            short_id = request.id[:8] + "..."
            
            row_index = None
            for i, record in enumerate(all_records):
                if record.get('요청ID') == short_id:
                    row_index = i + 2  # 헤더 행 고려
                    break
            
            if row_index:
                # 업데이트할 데이터 준비
                interviewer_info = get_employee_info(request.interviewer_id)
                
                confirmed_datetime = ""
                if request.selected_slot:
                    confirmed_datetime = f"{request.selected_slot.date} {request.selected_slot.time}({request.selected_slot.duration}분)"
                
                proposed_slots_str = ""
                if request.available_slots:
                    proposed_slots_str = " | ".join([f"{slot.date} {slot.time}({slot.duration}분)" for slot in request.available_slots])
                
                preferred_datetime_str = ""
                if request.preferred_datetime_slots:
                    preferred_datetime_str = " | ".join(request.preferred_datetime_slots)
                
                # 처리 소요시간 계산
                processing_time = ""
                if request.updated_at and request.status == Config.Status.CONFIRMED:
                    time_diff = request.updated_at - request.created_at
                    hours = int(time_diff.total_seconds() // 3600)
                    processing_time = f"{hours}시간" if hours > 0 else "1시간 미만"
                
                # 배치 업데이트 (한 번에 여러 셀 업데이트)
                updates = [
                    {'range': f'E{row_index}', 'values': [[interviewer_info['name']]]},  # 면접관이름
                    {'range': f'H{row_index}', 'values': [[request.status]]},  # 상태
                    {'range': f'I{row_index}', 'values': [[request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else ""]]},  # 상태변경일시
                    {'range': f'J{row_index}', 'values': [[preferred_datetime_str]]},  # 희망일시목록
                    {'range': f'K{row_index}', 'values': [[proposed_slots_str]]},  # 제안일시목록
                    {'range': f'L{row_index}', 'values': [[confirmed_datetime]]},  # 확정일시
                    {'range': f'M{row_index}', 'values': [[request.candidate_note]]},  # 면접자요청사항
                    {'range': f'N{row_index}', 'values': [[datetime.now().strftime('%Y-%m-%d %H:%M')]]},  # 마지막업데이트
                    {'range': f'O{row_index}', 'values': [[processing_time]]},  # 처리소요시간
                ]
                
                self.sheet.batch_update(updates)
                
                # 상태별 색상 적용
                self._apply_status_formatting(row_index, request.status)
                
                return True
            else:
                # 새로 추가
                return self.save_to_google_sheet(request)
                
        except Exception as e:
            print(f"구글 시트 업데이트 실패: {e}")
            return False
    
    def _apply_status_formatting(self, row_index: int, status: str):
        """상태별 행 색상 적용"""
        try:
            if status == Config.Status.PENDING_INTERVIEWER:
                color = {'red': 1.0, 'green': 0.9, 'blue': 0.8}  # 연한 주황색
            elif status == Config.Status.PENDING_CANDIDATE:
                color = {'red': 0.8, 'green': 0.9, 'blue': 1.0}  # 연한 파란색
            elif status == Config.Status.CONFIRMED:
                color = {'red': 0.8, 'green': 1.0, 'blue': 0.8}  # 연한 초록색
            elif status == Config.Status.PENDING_CONFIRMATION:
                color = {'red': 1.0, 'green': 1.0, 'blue': 0.8}  # 연한 노란색
            elif status == Config.Status.CANCELLED:
                color = {'red': 0.9, 'green': 0.9, 'blue': 0.9}  # 연한 회색
            else:
                return
            
            self.sheet.format(f'{row_index}:{row_index}', {
                'backgroundColor': color
            })
        except Exception as e:
            print(f"색상 적용 실패: {e}")
    
    def get_statistics(self) -> dict:
        """통계 데이터 조회"""
        requests = self.get_all_requests()
        
        stats = {
            'total': len(requests),
            'pending_interviewer': 0,
            'pending_candidate': 0,
            'pending_confirmation': 0,
            'confirmed': 0,
            'cancelled': 0,
            'avg_processing_time': 0
        }
        
        processing_times = []
        
        for req in requests:
            if req.status == Config.Status.PENDING_INTERVIEWER:
                stats['pending_interviewer'] += 1
            elif req.status == Config.Status.PENDING_CANDIDATE:
                stats['pending_candidate'] += 1
            elif req.status == Config.Status.PENDING_CONFIRMATION:
                stats['pending_confirmation'] += 1
            elif req.status == Config.Status.CONFIRMED:
                stats['confirmed'] += 1
                if req.updated_at:
                    time_diff = req.updated_at - req.created_at
                    processing_times.append(time_diff.total_seconds() / 3600)  # 시간 단위
            elif req.status == Config.Status.CANCELLED:
                stats['cancelled'] += 1
        
        if processing_times:
            stats['avg_processing_time'] = sum(processing_times) / len(processing_times)
        
        return stats
