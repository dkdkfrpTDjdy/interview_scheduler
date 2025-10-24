import sqlite3
import json
import logging
import streamlit as st
from typing import List, Optional, Tuple
from datetime import datetime
import sys
import os

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import InterviewRequest, InterviewSlot
from config import Config
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import time
import random
from functools import wraps

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retry_on_failure(max_retries=3, delay=1):
    """API 실패 시 재시도 데코레이터"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"시도 {attempt + 1}/{max_retries} 실패: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"최종 실패: {e}")
                        raise e
                    
                    # 지수 백오프 + 지터
                    wait_time = delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.info(f"{wait_time:.2f}초 후 재시도...")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator

class DatabaseManager:
    def __init__(self, db_path: str = Config.DATABASE_PATH):
        self.db_path = db_path
        self.gc = None
        self.sheet = None
        self.init_database()
        self.init_google_sheet()
    
    def init_database(self):
        """데이터베이스 초기화"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 기존 테이블
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS interview_requests (
                        id TEXT PRIMARY KEY,
                        interviewer_id TEXT NOT NULL,
                        candidate_email TEXT NOT NULL,
                        candidate_name TEXT NOT NULL,
                        position_name TEXT NOT NULL,
                        detailed_position_name TEXT,
                        status TEXT NOT NULL,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP,
                        available_slots TEXT,
                        preferred_datetime_slots TEXT,
                        selected_slot TEXT,
                        candidate_note TEXT,
                        candidate_phone TEXT
                    )
                """)

                # ✅ 기존 테이블에 컬럼 추가 (마이그레이션)
                try:
                    conn.execute("ALTER TABLE interview_requests ADD COLUMN detailed_position_name TEXT")
                    logger.info("✅ detailed_position_name 컬럼 추가 완료")
                except Exception as e:
                    if "duplicate column name" not in str(e).lower():
                        logger.warning(f"detailed_position_name 컬럼 추가 시도: {e}")
                
                try:
                    conn.execute("ALTER TABLE interview_requests ADD COLUMN candidate_phone TEXT")
                    logger.info("✅ candidate_phone 컬럼 추가 완료")
                except Exception as e:
                    if "duplicate column name" not in str(e).lower():
                        logger.warning(f"candidate_phone 컬럼 추가 시도: {e}")
                
                # ✅ 면접관 응답 테이블 추가
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS interviewer_responses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id TEXT NOT NULL,
                        interviewer_id TEXT NOT NULL,
                        available_slots TEXT NOT NULL,
                        responded_at TIMESTAMP,
                        UNIQUE(request_id, interviewer_id)
                    )
                """)
                
                logger.info("데이터베이스 초기화 완료")
        except Exception as e:
            logger.error(f"데이터베이스 초기화 실패: {e}")
            raise
    
    @retry_on_failure(max_retries=3, delay=2)
    def init_google_sheet(self):
        """구글 시트 초기화"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            service_account_info = None
            
            # 방법 1: Streamlit Secrets (TOML 구조)
            try:
                if hasattr(st, 'secrets') and "google_credentials" in st.secrets:
                    logger.info("🔍 TOML 구조로 Secrets 읽기 시도...")
                    
                    private_key = st.secrets["google_credentials"]["private_key"]
                    
                    if "\\n" in private_key:
                        private_key = private_key.replace("\\n", "\n")
                    
                    private_key = private_key.strip()
                    lines = private_key.split('\n')
                    cleaned_lines = [line.strip() for line in lines if line.strip()]
                    private_key = '\n'.join(cleaned_lines)
                    
                    service_account_info = {
                        "type": st.secrets["google_credentials"]["type"],
                        "project_id": st.secrets["google_credentials"]["project_id"],
                        "private_key_id": st.secrets["google_credentials"]["private_key_id"],
                        "private_key": private_key,
                        "client_email": st.secrets["google_credentials"]["client_email"],
                        "client_id": st.secrets["google_credentials"]["client_id"],
                        "auth_uri": st.secrets["google_credentials"]["auth_uri"],
                        "token_uri": st.secrets["google_credentials"]["token_uri"],
                        "auth_provider_x509_cert_url": st.secrets["google_credentials"]["auth_provider_x509_cert_url"],
                        "client_x509_cert_url": st.secrets["google_credentials"]["client_x509_cert_url"],
                        "universe_domain": st.secrets["google_credentials"]["universe_domain"]
                    }
                    logger.info("✅ Streamlit Secrets에서 인증 정보 로드")
                    
            except Exception as e:
                logger.warning(f"TOML Secrets 읽기 실패: {e}")
            
            if not service_account_info:
                logger.error("❌ 인증 정보를 가져올 수 없습니다")
                self.gc = None
                self.sheet = None
                return
            
            # Google 인증
            try:
                import tempfile
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                    json.dump(service_account_info, temp_file)
                    temp_path = temp_file.name
                
                credentials = Credentials.from_service_account_file(temp_path, scopes=scope)
                os.unlink(temp_path)
                
                logger.info("✅ Google 인증 성공")
                
            except Exception as e:
                logger.error(f"❌ Google 인증 실패: {e}")
                raise
            
            self.gc = gspread.authorize(credentials)
            
            sheet_id = st.secrets["GOOGLE_SHEET_ID"]
            self.sheet = self.gc.open_by_key(sheet_id).sheet1
            logger.info("✅ 구글 시트 연결 성공")
            
            # 헤더 설정
            headers = [
                "요청ID", "생성일시", "공고명", "상세공고명",
                "면접관ID", "면접관이름", "면접자명", 
                "면접자이메일", "면접자전화번호", 
                "상태", "상태변경일시", "희망일시목록", "제안일시목록", 
                "확정일시", "면접자요청사항", "마지막업데이트", "처리소요시간", "비고"
            ]
            
            try:
                existing_headers = self.sheet.row_values(1)
                
                if not existing_headers or "면접자전화번호" not in existing_headers:
                    self._setup_sheet_headers(headers)
                else:
                    logger.info("구글시트 헤더 이미 존재함")
                    
            except Exception as e:
                self._setup_sheet_headers(headers)
                
            logger.info("🎉 구글 시트 초기화 완료!")
                
        except Exception as e:
            logger.error(f"❌ 구글 시트 초기화 실패: {e}")
            self.gc = None
            self.sheet = None
    
    def _setup_sheet_headers(self, headers):
        """시트 헤더 설정"""
        try:
            if "상세공고명" not in headers:
                headers.insert(3, "상세공고명")
            
            self.sheet.clear()
            self.sheet.append_row(headers)
            
            self.sheet.format('1:1', {
                'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 0.9},
                'textFormat': {
                    'bold': True, 
                    'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}
                }
            })
            logger.info("시트 헤더 설정 완료")
        except Exception as e:
            logger.error(f"헤더 설정 실패: {e}")

    # init_google_sheet() 함수 내 헤더 수정

    headers = [
        "요청ID", "생성일시", "공고명", "상세공고명", "면접관ID", "면접관이름", "면접자명", 
        "면접자이메일", "상태", "상태변경일시", "희망일시목록", "제안일시목록", 
        "확정일시", "면접자요청사항", "마지막업데이트", "처리소요시간", "비고"
    ]
    
    def save_interview_request(self, request: InterviewRequest):
        """면접 요청 저장"""
        try:
            # ✅ 디버깅: 저장 전 확인
            detailed_name = getattr(request, 'detailed_position_name', '')
            phone = getattr(request, 'candidate_phone', '')
            
            logger.info(f"💾 DB 저장 시도")
            logger.info(f"  - ID: {request.id}")
            logger.info(f"  - 공고명: {request.position_name}")
            logger.info(f"  - 상세공고명: '{detailed_name}'")
            logger.info(f"  - 전화번호: '{phone}'")
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO interview_requests 
                    (id, interviewer_id, candidate_email, candidate_name, position_name, 
                    detailed_position_name, status, created_at, updated_at, available_slots, 
                    preferred_datetime_slots, selected_slot, candidate_note, candidate_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    request.id,
                    request.interviewer_id,
                    request.candidate_email,
                    request.candidate_name,
                    request.position_name,
                    detailed_name,  # ✅ 명시적 사용
                    request.status,
                    request.created_at.isoformat(),
                    (request.updated_at or datetime.now()).isoformat(),
                    json.dumps([{"date": slot.date, "time": slot.time, "duration": slot.duration} 
                            for slot in request.available_slots]),
                    json.dumps(request.preferred_datetime_slots) if request.preferred_datetime_slots else None,
                    json.dumps({"date": request.selected_slot.date, "time": request.selected_slot.time, 
                            "duration": request.selected_slot.duration}) if request.selected_slot else None,
                    request.candidate_note or "",
                    phone
                ))
                logger.info(f"면접 요청 저장 완료: {request.id[:8]}...")
            
            try:
                self.update_google_sheet(request)
            except Exception as e:
                logger.warning(f"구글 시트 업데이트 실패: {e}")
                
        except Exception as e:
            logger.error(f"면접 요청 저장 실패: {e}")
            raise
    
    def save_interviewer_response(self, request_id: str, interviewer_id: str, slots: List[InterviewSlot]):
        """개별 면접관의 일정 응답 저장"""
        try:
            slots_json = json.dumps([
                {"date": slot.date, "time": slot.time, "duration": slot.duration} 
                for slot in slots
            ])
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO interviewer_responses 
                    (request_id, interviewer_id, available_slots, responded_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    request_id,
                    interviewer_id,
                    slots_json,
                    datetime.now().isoformat()
                ))
                
            logger.info(f"면접관 {interviewer_id} 응답 저장 완료: {len(slots)}개 슬롯")
            return True
            
        except Exception as e:
            logger.error(f"면접관 응답 저장 실패: {e}")
            return False
    
    def get_interviewer_responses(self, request_id: str) -> dict:
        """특정 요청에 대한 모든 면접관의 응답 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT interviewer_id, available_slots, responded_at FROM interviewer_responses WHERE request_id = ?",
                    (request_id,)
                )
                rows = cursor.fetchall()
            
            responses = {}
            for row in rows:
                interviewer_id = row[0]
                try:
                    slots_data = json.loads(row[1])
                    slots = [InterviewSlot(**slot) for slot in slots_data]
                    responses[interviewer_id] = slots
                    logger.info(f"면접관 {interviewer_id} 응답 로드: {len(slots)}개 슬롯")
                except json.JSONDecodeError as e:
                    logger.warning(f"면접관 {interviewer_id} 슬롯 파싱 실패: {e}")
                    continue
            
            logger.info(f"총 {len(responses)}명의 면접관 응답 조회 완료 (request_id: {request_id[:8]}...)")
            return responses
            
        except Exception as e:
            logger.error(f"면접관 응답 조회 실패: {e}")
            return {}
    
    def check_all_interviewers_responded(self, request: InterviewRequest) -> Tuple[bool, int, int]:
        """
        모든 면접관이 일정을 입력했는지 확인
        
        Returns:
            Tuple[bool, int, int]: (전체 응답 여부, 응답한 면접관 수, 전체 면접관 수)
        """
        try:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            total_count = len(interviewer_ids)
            
            # 단일 면접관인 경우
            if total_count == 1:
                has_slots = request.available_slots and len(request.available_slots) > 0
                responded_count = 1 if has_slots else 0
                logger.info(f"단일 면접관 응답 확인: {responded_count}/{total_count}")
                return (has_slots, responded_count, total_count)
            
            # 복수 면접관인 경우 - interviewer_responses 테이블 확인
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(DISTINCT interviewer_id) FROM interviewer_responses WHERE request_id = ?",
                    (request.id,)
                )
                result = cursor.fetchone()
                responded_count = result[0] if result else 0
            
            all_responded = (responded_count == total_count)
            
            logger.info(f"면접관 응답 현황: {responded_count}/{total_count} (request_id: {request.id[:8]}...)")
            
            return (all_responded, responded_count, total_count)
            
        except Exception as e:
            logger.error(f"면접관 응답 확인 실패: {e}")
            # 에러 발생 시에도 안전한 기본값 반환
            try:
                interviewer_count = len(request.interviewer_id.split(','))
            except Exception:  # ✅
                interviewer_count = 1
            return (False, 0, interviewer_count)
        
    def sync_from_google_sheet_to_db(self):
        """구글시트 데이터를 SQLite DB로 동기화"""
        try:
            if not self.sheet:
                logger.warning("구글 시트가 연결되지 않았습니다.")
                return False
            
            # 구글시트에서 모든 데이터 가져오기
            all_records = self.sheet.get_all_records()
            
            for record in all_records:
                try:
                    # 구글시트 데이터를 InterviewRequest 객체로 변환
                    request_id = record.get('요청ID', '')
                    if not request_id:
                        continue
                    
                    # 이미 DB에 있는지 확인
                    existing = self.get_interview_request(request_id)
                    if existing:
                        logger.info(f"이미 존재하는 요청 건너뜀: {request_id}")
                        continue
                    
                    # InterviewRequest 객체 생성
                    from models import InterviewRequest, InterviewSlot
                    
                    # available_slots 파싱
                    available_slots = []
                    proposed_slots_str = record.get('제안일시목록', '')
                    if proposed_slots_str:
                        from utils import parse_proposed_slots
                        slot_data = parse_proposed_slots(proposed_slots_str)
                        available_slots = [InterviewSlot(**slot) for slot in slot_data]
                    
                    # preferred_datetime_slots 파싱
                    preferred_slots = []
                    preferred_str = record.get('희망일시목록', '')
                    if preferred_str:
                        preferred_slots = [slot.strip() for slot in preferred_str.split('|')]
                    
                    # selected_slot 파싱
                    selected_slot = None
                    confirmed_str = record.get('확정일시', '')
                    if confirmed_str:
                        # "2025-01-15 14:00(30분)" 형식 파싱
                        import re
                        match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})$(\d+)분$', confirmed_str)
                        if match:
                            selected_slot = InterviewSlot(
                                date=match.group(1),
                                time=match.group(2),
                                duration=int(match.group(3))
                            )
                    
                    # 생성일시 파싱
                    created_at = datetime.now()
                    created_str = record.get('생성일시', '')
                    if created_str:
                        try:
                            created_at = datetime.strptime(created_str, '%Y-%m-%d %H:%M')
                        except:
                            pass
                    
                    # 상태 매핑
                    status_map = {
                        '면접관_일정입력대기': Config.Status.PENDING_INTERVIEWER,
                        '면접자_선택대기': Config.Status.PENDING_CANDIDATE,
                        '확정완료': Config.Status.CONFIRMED,
                        '일정재조율요청': Config.Status.PENDING_CONFIRMATION,
                        '취소': Config.Status.CANCELLED
                    }
                    
                    status = status_map.get(record.get('상태', ''), Config.Status.PENDING_INTERVIEWER)
                    
                    # InterviewRequest 객체 생성
                    request = InterviewRequest(
                        id=request_id,
                        interviewer_id=record.get('면접관ID', ''),
                        candidate_email=record.get('면접자이메일', ''),
                        candidate_name=record.get('면접자명', ''),
                        position_name=record.get('공고명', ''),
                        status=status,
                        created_at=created_at,
                        updated_at=datetime.now(),
                        available_slots=available_slots,
                        preferred_datetime_slots=preferred_slots,
                        selected_slot=selected_slot,
                        candidate_note=record.get('면접자요청사항', '')
                    )
                    
                    # SQLite에 저장 (구글시트 업데이트는 하지 않음)
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
                            request.created_at.isoformat(),
                            request.updated_at.isoformat(),
                            json.dumps([{"date": slot.date, "time": slot.time, "duration": slot.duration} 
                                    for slot in request.available_slots]),
                            json.dumps(request.preferred_datetime_slots) if request.preferred_datetime_slots else None,
                            json.dumps({"date": request.selected_slot.date, "time": request.selected_slot.time, 
                                    "duration": request.selected_slot.duration}) if request.selected_slot else None,
                            request.candidate_note or ""
                        ))
                    
                    logger.info(f"구글시트 → DB 동기화 완료: {request_id}")
                    
                except Exception as e:
                    logger.error(f"레코드 동기화 실패: {e}")
                    continue
            
            logger.info("구글시트 → SQLite DB 동기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"동기화 실패: {e}")
            return False
    
    def get_common_available_slots(self, request: InterviewRequest) -> List[InterviewSlot]:
        """모든 면접관이 공통으로 선택한 30분 단위 타임슬롯 반환"""
        try:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            
            # 단일 면접관인 경우
            if len(interviewer_ids) == 1:
                return request.available_slots
            
            # 복수 면접관인 경우
            responses = self.get_interviewer_responses(request.id)
            
            if len(responses) < len(interviewer_ids):
                logger.warning(f"일부 면접관이 아직 응답하지 않았습니다: {len(responses)}/{len(interviewer_ids)}")
                return []
            
            # 각 면접관별 타임슬롯을 set으로 변환
            slot_sets = []
            for interviewer_id in interviewer_ids:
                if interviewer_id in responses:
                    slot_keys = set()
                    for slot in responses[interviewer_id]:
                        key = f"{slot.date}_{slot.time}"
                        slot_keys.add(key)
                    slot_sets.append(slot_keys)
                else:
                    logger.warning(f"면접관 {interviewer_id}의 응답이 없습니다.")
                    return []
            
            # 교집합 계산
            if not slot_sets:
                return []
            
            common_slot_keys = set.intersection(*slot_sets)
            
            # 키를 다시 InterviewSlot 객체로 변환
            common_slots = []
            for key in common_slot_keys:
                date_part, time_part = key.split('_')
                common_slots.append(InterviewSlot(
                    date=date_part,
                    time=time_part,
                    duration=30
                ))
            
            # 날짜/시간 순으로 정렬
            common_slots.sort(key=lambda x: (x.date, x.time))
            
            logger.info(f"공통 타임슬롯 {len(common_slots)}개 발견: {request.position_name}")
            return common_slots
            
        except Exception as e:
            logger.error(f"공통 타임슬롯 찾기 실패: {e}")
            return []
    
    def find_overlapping_time_slots(self, request: InterviewRequest) -> List[InterviewSlot]:
        """모든 면접관이 공통으로 가능한 30분 단위 타임슬롯 찾기"""
        try:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            
            # 단일 면접관인 경우
            if len(interviewer_ids) == 1:
                return request.available_slots
            
            # 복수 면접관인 경우 - get_common_available_slots 재사용
            return self.get_common_available_slots(request)
            
        except Exception as e:
            logger.error(f"중복 타임슬롯 찾기 실패: {e}")
            return []
    
    def get_available_slots_for_candidate(self, request: InterviewRequest) -> List[InterviewSlot]:
        """면접자가 선택 가능한 30분 단위 타임슬롯 조회 (이미 예약된 슬롯 제외)"""
        try:
            # 1. 중복 타임슬롯 가져오기
            all_slots = self.find_overlapping_time_slots(request)
            
            # 2. 동일 포지션의 확정된 타임슬롯 가져오기
            all_requests = self.get_all_requests()
            reserved_slot_keys = set()
            
            for req in all_requests:
                if (req.position_name == request.position_name 
                    and req.status == Config.Status.CONFIRMED 
                    and req.selected_slot 
                    and req.id != request.id):
                    
                    key = f"{req.selected_slot.date}_{req.selected_slot.time}"
                    reserved_slot_keys.add(key)
            
            # 3. 예약되지 않은 타임슬롯만 필터링
            available_slots = []
            for slot in all_slots:
                key = f"{slot.date}_{slot.time}"
                if key not in reserved_slot_keys:
                    available_slots.append(slot)
            
            logger.info(f"선택 가능한 타임슬롯 {len(available_slots)}개 (예약됨: {len(reserved_slot_keys)}개)")
            return available_slots
            
        except Exception as e:
            logger.error(f"선택 가능한 타임슬롯 조회 실패: {e}")
            return []
    
    def reserve_slot_for_candidate(self, request: InterviewRequest, selected_slot: InterviewSlot) -> bool:
        """면접자가 선택한 30분 타임슬롯 예약 (중복 예약 방지)"""
        try:
            # 1. 해당 타임슬롯이 이미 예약되었는지 확인
            all_requests = self.get_all_requests()
            
            for req in all_requests:
                if (req.position_name == request.position_name 
                    and req.status == Config.Status.CONFIRMED 
                    and req.selected_slot 
                    and req.id != request.id):
                    
                    if (req.selected_slot.date == selected_slot.date 
                        and req.selected_slot.time == selected_slot.time):
                        logger.warning(f"타임슬롯 중복 예약 시도: {selected_slot.date} {selected_slot.time}")
                        return False
            
            # 2. 예약 가능 - 요청 업데이트
            request.selected_slot = selected_slot
            request.status = Config.Status.CONFIRMED
            request.updated_at = datetime.now()
            
            self.save_interview_request(request)
            self.update_google_sheet(request)
            
            logger.info(f"타임슬롯 예약 성공: {selected_slot.date} {selected_slot.time}")
            return True
            
        except Exception as e:
            logger.error(f"타임슬롯 예약 실패: {e}")
            return False
    
    def get_interview_request(self, request_id: str) -> Optional[InterviewRequest]:
        """면접 요청 조회"""
        from utils import normalize_request_id
        clean_id = normalize_request_id(request_id)

        try:
            with sqlite3.connect(self.db_path) as conn:
                # 1차: 정확한 매칭
                cursor = conn.execute(
                    "SELECT * FROM interview_requests WHERE id = ?", 
                    (clean_id,)
                )
                row = cursor.fetchone()
                
                # 2차: 부분 매칭
                if not row:
                    cursor = conn.execute(
                        "SELECT * FROM interview_requests WHERE id LIKE ? OR id LIKE ?", 
                        (f"{clean_id}%", f"%{clean_id}%")
                    )
                    row = cursor.fetchone()
                
                # 3차: 정규화된 ID로 재검색
                if not row:
                    cursor = conn.execute("SELECT * FROM interview_requests")
                    all_rows = cursor.fetchall()
                    
                    for r in all_rows:
                        stored_id = normalize_request_id(r[0])
                        if stored_id == clean_id:
                            row = r
                            break
                    
                if not row:
                    logger.warning(f"요청을 찾을 수 없음: {clean_id}")
                    return None

                # ✅ JSON 파싱
                available_slots = []
                if row[9]:  # available_slots
                    try:
                        slots_data = json.loads(row[9])
                        available_slots = [InterviewSlot(**slot) for slot in slots_data]
                    except json.JSONDecodeError as e:
                        logger.warning(f"available_slots 파싱 실패: {e}")
                
                preferred_datetime_slots = []
                if row[10]:  # preferred_datetime_slots
                    try:
                        preferred_datetime_slots = json.loads(row[10])
                    except json.JSONDecodeError as e:
                        logger.warning(f"preferred_datetime_slots 파싱 실패: {e}")
                
                selected_slot = None
                if row[11]:  # selected_slot
                    try:
                        slot_data = json.loads(row[11])
                        selected_slot = InterviewSlot(**slot_data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"selected_slot 파싱 실패: {e}")
                
                # ✅ InterviewRequest 객체 생성 (전화번호 포함)
                return InterviewRequest(
                    id=row[0],
                    interviewer_id=row[1],
                    candidate_email=row[2],
                    candidate_name=row[3],
                    position_name=row[4],
                    detailed_position_name=row[5] if len(row) > 5 else "",
                    status=row[6] if len(row) > 6 else row[5],
                    created_at=datetime.fromisoformat(row[7] if len(row) > 7 else row[6]),
                    updated_at=datetime.fromisoformat(row[8]) if (len(row) > 8 and row[8]) else None,
                    available_slots=available_slots,
                    preferred_datetime_slots=preferred_datetime_slots,
                    selected_slot=selected_slot,
                    candidate_note=row[12] if len(row) > 12 else "",
                    candidate_phone=row[13] if len(row) > 13 else ""  # ✅ 전화번호 추가
                )

        except Exception as e:
            logger.error(f"면접 요청 조회 실패: {e}")
            return None


    def get_all_requests(self) -> List[InterviewRequest]:
        """모든 면접 요청 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT id FROM interview_requests ORDER BY created_at DESC")
                request_ids = [row[0] for row in cursor.fetchall()]
            
            requests = []
            for req_id in request_ids:
                request = self.get_interview_request(req_id)
                if request:
                    requests.append(request)
            
            return requests
        except Exception as e:
            logger.error(f"전체 요청 조회 실패: {e}")
            return []
    
    @retry_on_failure(max_retries=3, delay=1)
    def save_to_google_sheet(self, request: InterviewRequest):
        """구글 시트에 새로운 요청 저장"""
        if not self.sheet:
            logger.warning("구글 시트가 초기화되지 않았습니다.")
            return False
        
        try:
            from utils import get_employee_info
            interviewer_info = get_employee_info(request.interviewer_id)
            
            row_data = self._prepare_sheet_row_data(request, interviewer_info)
            self.sheet.append_row(row_data)
            
            row_num = len(self.sheet.get_all_values())
            self._apply_status_formatting(row_num, request.status)
            
            logger.info(f"구글 시트 저장 완료: {request.id[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"구글 시트 저장 실패: {e}")
            return False
    
    @retry_on_failure(max_retries=3, delay=1)
    def update_google_sheet(self, request: InterviewRequest):
        """구글 시트 실시간 업데이트"""
        if not self.sheet:
            logger.warning("구글 시트가 초기화되지 않았습니다.")
            return False
        
        try:
            row_index = self._find_request_row(request.id)
            
            if row_index:
                # ✅ 기존 행 업데이트
                logger.info(f"📝 기존 행 업데이트: {row_index}번 행")
                updates = self._prepare_batch_updates(request, row_index)
                if updates:
                    self.sheet.batch_update(updates)
                    
                self._apply_status_formatting(row_index, request.status)
                
                logger.info(f"✅ 구글 시트 업데이트 완료: {request.id[:8]}...")
                return True
            else:
                # ✅ 새 행 추가
                logger.info(f"📝 새 행 추가")
                return self.save_to_google_sheet(request)
                
        except Exception as e:
            logger.error(f"❌ 구글 시트 업데이트 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _find_request_row(self, request_id: str) -> Optional[int]:
        """요청 ID로 행 번호 찾기 - 정규화 적용"""
        from utils import normalize_request_id
        
        try:
            clean_id = normalize_request_id(request_id)
            all_records = self.sheet.get_all_records()
            
            for i, record in enumerate(all_records):
                sheet_id = normalize_request_id(record.get('요청ID', ''))
                if sheet_id == clean_id:
                    return i + 2
            return None
        except Exception as e:
            logger.error(f"행 찾기 실패: {e}")
            return None
    
    def _prepare_sheet_row_data(self, request: InterviewRequest, interviewer_info: dict = None) -> list:
        """시트 행 데이터 준비"""
        from utils import normalize_request_id
        from utils import get_employee_info
        
        interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
        interviewer_names = []
        interviewer_departments = []
        
        for interviewer_id in interviewer_ids:
            info = get_employee_info(interviewer_id)
            interviewer_names.append(info.get('name', interviewer_id))
            interviewer_departments.append(info.get('department', '미확인'))
        
        interviewer_id_str = ", ".join(interviewer_ids)
        interviewer_name_str = ", ".join(interviewer_names)
        interviewer_dept_str = ", ".join(set(interviewer_departments))
        
        preferred_datetime_str = ""
        if request.preferred_datetime_slots:
            preferred_datetime_str = " | ".join(request.preferred_datetime_slots)
        
        proposed_slots_str = ""
        if request.available_slots:
            proposed_slots_str = " | ".join([
                f"{slot.date} {slot.time}({slot.duration}분)" 
                for slot in request.available_slots
            ])
        
        confirmed_datetime = ""
        if request.selected_slot:
            confirmed_datetime = f"{request.selected_slot.date} {request.selected_slot.time}({request.selected_slot.duration}분)"
        
        processing_time = ""
        if request.updated_at and request.status == Config.Status.CONFIRMED:
            time_diff = request.updated_at - request.created_at
            hours = int(time_diff.total_seconds() // 3600)
            processing_time = f"{hours}시간" if hours > 0 else "1시간 미만"
        
        status_changed_at = request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else request.created_at.strftime('%Y-%m-%d %H:%M')
        
        remarks = f"담당부서: {interviewer_dept_str}" if len(interviewer_ids) > 1 else ""
        
        # ✅ 전화번호를 면접자이메일 바로 다음에 배치
        return [
            normalize_request_id(request.id),
            request.created_at.strftime('%Y-%m-%d %H:%M'),
            request.position_name,
            getattr(request, 'detailed_position_name', ''),
            interviewer_id_str,
            interviewer_name_str,
            request.candidate_name,
            request.candidate_email,
            getattr(request, 'candidate_phone', ''),  # ✅ 전화번호 추가 (9번째)
            request.status,
            status_changed_at,
            preferred_datetime_str,
            proposed_slots_str,
            confirmed_datetime,
            request.candidate_note or "",
            datetime.now().strftime('%Y-%m-%d %H:%M'),
            processing_time,
            remarks
        ]
    
    def _prepare_batch_updates(self, request: InterviewRequest, row_index: int) -> list:
        """배치 업데이트 데이터 준비"""
        try:
            from utils import get_employee_info
            
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            interviewer_names = []
            
            for interviewer_id in interviewer_ids:
                info = get_employee_info(interviewer_id)
                interviewer_names.append(info.get('name', interviewer_id))
            
            interviewer_name_str = ", ".join(interviewer_names)
            
            confirmed_datetime = ""
            if request.selected_slot:
                confirmed_datetime = f"{request.selected_slot.date} {request.selected_slot.time}({request.selected_slot.duration}분)"
            
            proposed_slots_str = ""
            if request.available_slots:
                proposed_slots_str = " | ".join([
                    f"{slot.date} {slot.time}({slot.duration}분)" 
                    for slot in request.available_slots
                ])
            
            preferred_datetime_str = ""
            if request.preferred_datetime_slots:
                preferred_datetime_str = " | ".join(request.preferred_datetime_slots)
            
            processing_time = ""
            if request.updated_at and request.status == Config.Status.CONFIRMED:
                time_diff = request.updated_at - request.created_at
                hours = int(time_diff.total_seconds() // 3600)
                processing_time = f"{hours}시간" if hours > 0 else "1시간 미만"

            detailed_name = getattr(request, 'detailed_position_name', '')
            phone = getattr(request, 'candidate_phone', '')

            # ✅ 상세공고명과 전화번호 추출
            logger.info(f"📝 배치 업데이트 - detailed_position_name: '{detailed_name}'")
            logger.info(f"📝 배치 업데이트 - candidate_phone: '{phone}'") 
            
            updates = [
                {'range': f'D{row_index}', 'values': [[detailed_name]]},  # ✅ D열: 상세공고명
                {'range': f'F{row_index}', 'values': [[interviewer_name_str]]},  # F열: 면접관이름
                {'range': f'I{row_index}', 'values': [[phone]]},  # ✅ I열: 전화번호
                {'range': f'J{row_index}', 'values': [[request.status]]},  # J열: 상태
                {'range': f'K{row_index}', 'values': [[request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else ""]]},
                {'range': f'L{row_index}', 'values': [[preferred_datetime_str]]},
                {'range': f'M{row_index}', 'values': [[proposed_slots_str]]},
                {'range': f'N{row_index}', 'values': [[confirmed_datetime]]},
                {'range': f'O{row_index}', 'values': [[request.candidate_note or ""]]},
                {'range': f'P{row_index}', 'values': [[datetime.now().strftime('%Y-%m-%d %H:%M')]]},
                {'range': f'Q{row_index}', 'values': [[processing_time]]},
            ]
            
            return updates
            
        except Exception as e:
            logger.error(f"배치 업데이트 데이터 준비 실패: {e}")
            return []
    
    def _apply_status_formatting(self, row_index: int, status: str):
        """상태별 행 색상 적용"""
        try:
            color_map = {
                Config.Status.PENDING_INTERVIEWER: {'red': 1.0, 'green': 0.9, 'blue': 0.8},
                Config.Status.PENDING_CANDIDATE: {'red': 0.8, 'green': 0.9, 'blue': 1.0},
                Config.Status.CONFIRMED: {'red': 0.8, 'green': 1.0, 'blue': 0.8},
                Config.Status.PENDING_CONFIRMATION: {'red': 1.0, 'green': 1.0, 'blue': 0.8},
                Config.Status.CANCELLED: {'red': 0.9, 'green': 0.9, 'blue': 0.9},
            }
            
            color = color_map.get(status)
            if color:
                self.sheet.format(f'{row_index}:{row_index}', {
                    'backgroundColor': color
                })
        except Exception as e:
            logger.warning(f"색상 적용 실패: {e}")
    
    def force_refresh(self):
        """강제 새로고침"""
        try:
            if self.gc and Config.GOOGLE_SHEET_ID:
                self.sheet = self.gc.open_by_key(Config.GOOGLE_SHEET_ID).sheet1
                logger.info("구글 시트 강제 새로고침 완료")
                
                if hasattr(st, 'cache_data'):
                    st.cache_data.clear()
            else:
                logger.warning("구글 시트 연결이 없어 새로고침할 수 없습니다.")
        except Exception as e:
            logger.error(f"강제 새로고침 실패: {e}")
    
    def get_all_requests_realtime(self):
        """실시간 요청 조회"""
        self.force_refresh()
        return self.get_all_requests()
    
    def get_statistics(self) -> dict:
        """통계 데이터 조회"""
        try:
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
                        processing_times.append(time_diff.total_seconds() / 3600)
                elif req.status == Config.Status.CANCELLED:
                    stats['cancelled'] += 1
            
            if processing_times:
                stats['avg_processing_time'] = sum(processing_times) / len(processing_times)
            
            return stats
            
        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")
            return {
                'total': 0, 'pending_interviewer': 0, 'pending_candidate': 0,
                'pending_confirmation': 0, 'confirmed': 0, 'cancelled': 0,
                'avg_processing_time': 0
            }
    
    def health_check(self) -> dict:
        """시스템 상태 체크"""
        status = {
            'database': False,
            'google_sheet': False,
            'last_check': datetime.now().isoformat()
        }
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("SELECT 1").fetchone()
            status['database'] = True
        except Exception as e:
            logger.error(f"데이터베이스 체크 실패: {e}")
        
        try:
            if self.sheet:
                self.sheet.row_values(1)
                status['google_sheet'] = True
        except Exception as e:
            logger.error(f"구글 시트 체크 실패: {e}")
            status['google_sheet'] = False  # ❗반환은 계속됨

        return status
