# 표준 라이브러리
import sqlite3
import json
import logging
import sys
import os
import time
import random
import threading  
from collections import OrderedDict
from datetime import datetime
from functools import wraps
from typing import List, Optional, Dict, Tuple, Any

# 서드파티 라이브러리
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 프로젝트 내부 모듈
from models import InterviewRequest, InterviewSlot
from config import Config

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
        
        # ✅ 개선된 캐시 설정
        self._cache_timeout = 300  # 5분으로 단축 (기존 1000초 → 300초)
        self._max_cache_size = 100  # 최대 캐시 항목 수 제한
        self._request_cache = OrderedDict()  # LRU 캐시를 위한 OrderedDict
        self._cache_lock = threading.Lock()  # 스레드 안전성
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # 1분마다 캐시 정리
        
        self.init_database()
        self.init_google_sheet()
        self.migrate_database_schema()

    def _cleanup_expired_cache(self):
        """만료된 캐시 항목 정리 (스레드 안전)"""
        with self._cache_lock:
            current_time = time.time()
            
            # 정리 간격 체크
            if current_time - self._last_cleanup < self._cleanup_interval:
                return
            
            # 만료된 항목 찾기
            expired_keys = []
            for key, (cached_data, timestamp) in self._request_cache.items():
                if current_time - timestamp > self._cache_timeout:
                    expired_keys.append(key)
            
            # 만료된 항목 삭제
            for key in expired_keys:
                del self._request_cache[key]
            
            # 크기 제한 적용 (LRU 방식)
            while len(self._request_cache) > self._max_cache_size:
                # 가장 오래된 항목 제거
                oldest_key = next(iter(self._request_cache))
                del self._request_cache[oldest_key]
            
            self._last_cleanup = current_time
            
            if expired_keys:
                logger.info(f"🧹 캐시 정리 완료: {len(expired_keys)}개 만료 항목 삭제")

    def _get_from_cache(self, clean_id: str) -> Optional[Any]:
        """캐시에서 안전하게 조회"""
        with self._cache_lock:
            current_time = time.time()
            
            if clean_id in self._request_cache:
                cached_data, timestamp = self._request_cache[clean_id]
                
                if current_time - timestamp < self._cache_timeout:
                    # LRU 업데이트 (최근 사용된 항목을 맨 뒤로)
                    self._request_cache.move_to_end(clean_id)
                    logger.info(f"📄 캐시 히트: {clean_id}")
                    return cached_data
                else:
                    # 만료된 캐시 삭제
                    del self._request_cache[clean_id]
                    logger.info(f"⏰ 캐시 만료: {clean_id}")
            
            return None

    def _set_to_cache(self, clean_id: str, request_data: Any):
        """캐시에 안전하게 저장"""
        with self._cache_lock:
            current_time = time.time()
            
            # 캐시 크기 제한 체크
            if len(self._request_cache) >= self._max_cache_size:
                # 가장 오래된 항목 제거
                oldest_key = next(iter(self._request_cache))
                del self._request_cache[oldest_key]
                logger.info(f"🗑️ 캐시 크기 제한으로 제거: {oldest_key}")
            
            # 새 데이터 저장
            self._request_cache[clean_id] = (request_data, current_time)
            logger.info(f"💾 캐시 저장: {clean_id} (총 {len(self._request_cache)}개)")

    def migrate_database_schema(self):
        """데이터베이스 스키마 마이그레이션"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 현재 테이블 구조 확인
                cursor.execute("PRAGMA table_info(interview_requests)")
                columns = [column[1] for column in cursor.fetchall()]
                
                logger.info(f"현재 테이블 컬럼: {columns}")
                
                # detailed_position_name 컬럼이 없으면 추가
                if 'detailed_position_name' not in columns:
                    cursor.execute("""
                        ALTER TABLE interview_requests 
                        ADD COLUMN detailed_position_name TEXT DEFAULT ''
                    """)
                    logger.info("✅ detailed_position_name 컬럼 추가 완료")
                
                # candidate_phone 컬럼이 없으면 추가
                if 'candidate_phone' not in columns:
                    cursor.execute("""
                        ALTER TABLE interview_requests 
                        ADD COLUMN candidate_phone TEXT DEFAULT ''
                    """)
                    logger.info("✅ candidate_phone 컬럼 추가 완료")
                
                conn.commit()
                logger.info("🎉 데이터베이스 마이그레이션 완료")
                
        except Exception as e:
            logger.error(f"❌ 데이터베이스 마이그레이션 실패: {e}")
    
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
                "상태", "상태변경일시", "인사팀제안일시", "면접관확정일시",  # ✅ 변경
                "면접자확정일시", "면접자요청사항", "마지막업데이트", "처리소요시간", "비고"  # ✅ 변경
            ]
            
            try:
                existing_headers = self.sheet.row_values(1)
                
                if not existing_headers or "면접자확정일시" not in existing_headers:  # ✅ 변경
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
    
    def save_interview_request(self, request: InterviewRequest):
        """면접 요청 저장"""
        try:
            from utils import normalize_request_id  # ✅ 추가
            
            # ✅ ID 정규화
            normalized_id = normalize_request_id(request.id)
            
            detailed_name = getattr(request, 'detailed_position_name', '')
            phone = getattr(request, 'candidate_phone', '')
            
            logger.info(f"💾 DB 저장 시도")
            logger.info(f"  - 원본 ID: {request.id}")
            logger.info(f"  - 정규화 ID: {normalized_id}")
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
                    normalized_id,  # ✅ 정규화된 ID 저장
                    request.interviewer_id,
                    request.candidate_email,
                    request.candidate_name,
                    request.position_name,
                    detailed_name,
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
                logger.info(f"✅ 면접 요청 저장 완료: {normalized_id}")
            
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
        """모든 면접관이 일정을 입력했는지 확인 (수정된 버전)"""
        try:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            total_count = len(interviewer_ids)
            
            logger.info(f"🔍 면접관 응답 확인 시작: {total_count}명 면접관")
            logger.info(f"  - 면접관 ID: {interviewer_ids}")
            logger.info(f"  - available_slots 수: {len(request.available_slots) if request.available_slots else 0}")
            
            # ✅ 단일 면접관인 경우
            if total_count == 1:
                has_slots = request.available_slots and len(request.available_slots) > 0
                responded_count = 1 if has_slots else 0
                logger.info(f"단일 면접관 응답 확인: {responded_count}/{total_count}")
                return (has_slots, responded_count, total_count)
            
            # ✅ 복수 면접관인 경우 - 로직 개선
            # 1차: available_slots이 있으면 모든 면접관이 응답했다고 간주
            if request.available_slots and len(request.available_slots) > 0:
                logger.info(f"✅ available_slots 존재 → 모든 면접관 응답 완료로 간주")
                return (True, total_count, total_count)
            
            # 2차: interviewer_responses 테이블 확인
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(DISTINCT interviewer_id) FROM interviewer_responses WHERE request_id = ?",
                    (request.id,)
                )
                result = cursor.fetchone()
                responded_count = result[0] if result else 0
            
            logger.info(f"interviewer_responses 테이블 확인: {responded_count}/{total_count}")
            
            # 3차: available_slots이 없고 개별 응답도 부족한 경우
            all_responded = (responded_count == total_count)
            return (all_responded, responded_count, total_count)
                
        except Exception as e:
            logger.error(f"면접관 응답 확인 실패: {e}")
            try:
                interviewer_count = len(request.interviewer_id.split(','))
            except Exception:
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
                        match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\$(\d+)분\$', confirmed_str)
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
        from utils import normalize_request_id
        
        try:
            clean_id = normalize_request_id(request_id)
            current_time = time.time()  # ← 이 줄 추가
            
            # 캐시 정리 (주기적)
            self._cleanup_expired_cache()
            
            # 캐시에서 먼저 조회
            cached_request = self._get_from_cache(clean_id)
            if cached_request is not None:
                return cached_request
            
            logger.info(f"🔍 DB 조회 시작: {clean_id}")
            
            # SQLite에서 조회
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT * FROM interview_requests WHERE id = ?", (clean_id,))
                row = cursor.fetchone()
                
                if row:
                    logger.info(f"✅ SQLite에서 발견: {clean_id}")
                    request = self._row_to_request(row)
                    
                    # ✅ 캐시에 저장 (현재 시간과 함께)
                    if request:
                        current_time = time.time()
                        self._set_to_cache(clean_id, request)
                    
                    return request
            
            # 구글시트에서 조회 (필요한 경우에만)
            logger.warning(f"⚠️ SQLite에서 못 찾음: {clean_id}")
            
            if not self.sheet:
                logger.error("❌ 구글 시트 연결 없음")
                return None
            
            try:
                records = self.sheet.get_all_records()
                logger.info(f"📊 구글 시트 레코드 수: {len(records)}")
                
                for i, record in enumerate(records):
                    sheet_id = normalize_request_id(record.get('요청ID', ''))
                    if sheet_id == clean_id:
                        logger.info(f"✅ 구글 시트에서 요청 발견: {clean_id} (행: {i+2})")
                        
                        # 구글 시트 → InterviewRequest 변환
                        request = self._convert_sheet_record_to_request(record)
                        if request:
                            # SQLite와 동기화
                            self.save_interview_request(request)
                            
                            # ✅ 캐시에도 저장 (추가된 부분!)
                            self._set_to_cache(clean_id, request)
                            
                            logger.info(f"🔄 구글시트 → SQLite 동기화 완료: {clean_id}")
                            return request
                
                logger.error(f"❌ 구글 시트에서도 요청을 찾지 못함: {clean_id}")
                
                # 디버깅: 구글시트 내 모든 요청ID 출력
                all_ids = [normalize_request_id(r.get('요청ID', '')) for r in records[:10]]
                logger.info(f"🔍 구글시트 샘플 ID들: {all_ids}")
                
            except Exception as sheet_error:
                logger.error(f"❌ 구글 시트 조회 중 오류: {sheet_error}")
                
            return None
            
        except Exception as e:
            logger.error(f"❌ 요청 조회 중 예외 발생: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def clear_cache(self):
        """캐시 완전 초기화"""
        with self._cache_lock:
            cleared_count = len(self._request_cache)
            self._request_cache.clear()
            logger.info(f"🧽 캐시 완전 초기화: {cleared_count}개 항목 삭제")

    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 정보"""
        with self._cache_lock:
            current_time = time.time()
            active_count = 0
            expired_count = 0
            
            for _, (cached_data, timestamp) in self._request_cache.items():
                if current_time - timestamp < self._cache_timeout:
                    active_count += 1
                else:
                    expired_count += 1
            
            return {
                'total_items': len(self._request_cache),
                'active_items': active_count,
                'expired_items': expired_count,
                'cache_timeout': self._cache_timeout,
                'max_cache_size': self._max_cache_size,
                'last_cleanup': datetime.fromtimestamp(self._last_cleanup).isoformat()
            }

    def _row_to_request(self, row) -> Optional[InterviewRequest]:
        """SQLite 행을 InterviewRequest 객체로 변환 (호환성 보장)"""
        try:
            # 컬럼 수에 따른 호환성 처리
            if len(row) == 12:  # 기존 스키마
                row = list(row) + ["", ""]  # detailed_position_name, candidate_phone 추가
            elif len(row) != 14:  # 예상과 다른 스키마
                logger.warning(f"⚠️ 예상과 다른 스키마: {len(row)}개 컬럼")
                return None

            # JSON 파싱
            available_slots = []
            if row[9]:
                try:
                    slots_data = json.loads(row[9])
                    available_slots = [InterviewSlot(**slot) for slot in slots_data]
                except json.JSONDecodeError as e:
                    logger.warning(f"available_slots 파싱 실패: {e}")

            preferred_datetime_slots = []
            if row[10]:
                try:
                    preferred_datetime_slots = json.loads(row[10])
                except json.JSONDecodeError as e:
                    logger.warning(f"preferred_datetime_slots 파싱 실패: {e}")

            selected_slot = None
            if row[11]:
                try:
                    slot_data = json.loads(row[11])
                    selected_slot = InterviewSlot(**slot_data)
                except json.JSONDecodeError as e:
                    logger.warning(f"selected_slot 파싱 실패: {e}")

            return InterviewRequest(
                id=row[0],
                interviewer_id=row[1],
                candidate_email=row[2],
                candidate_name=row[3],
                position_name=row[4],
                detailed_position_name=row[5] or "",
                status=row[6],
                created_at=datetime.fromisoformat(row[7]),
                updated_at=datetime.fromisoformat(row[8]) if row[8] else None,
                available_slots=available_slots,
                preferred_datetime_slots=preferred_datetime_slots,
                selected_slot=selected_slot,
                candidate_note=row[12] or "",
                candidate_phone=row[13] or ""
            )
            
        except Exception as e:
            logger.error(f"❌ 행 변환 실패: {e}")
            return None

    def _convert_sheet_record_to_request(self, record: dict) -> Optional[InterviewRequest]:
        """구글 시트 레코드를 InterviewRequest 객체로 변환 (강화)"""
        try:
            from utils import normalize_request_id
            
            # 필수 필드 확인
            required_fields = ['요청ID', '면접관ID', '면접자명', '면접자이메일', '공고명']
            missing_fields = []
            
            for field in required_fields:
                if not str(record.get(field, '')).strip():
                    missing_fields.append(field)
            
            if missing_fields:
                logger.warning(f"⚠️ 필수 필드 누락: {missing_fields}")
                return None

            # 제안 일시 목록 파싱
            preferred_slots = []
            preferred_str = record.get('인사팀제안일시', '')  # ✅ 변경
            if preferred_str:
                preferred_slots = [slot.strip() for slot in preferred_str.split('|') if slot.strip()]

            # 제안 슬롯 파싱
            available_slots = []
            proposed_str = record.get('면접관확정일시', '')  # ✅ 변경
            if proposed_str:
                from utils import parse_proposed_slots
                try:
                    slot_data = parse_proposed_slots(proposed_str)
                    available_slots = [InterviewSlot(**slot) for slot in slot_data]
                except Exception as slot_error:
                    logger.warning(f"제안슬롯 파싱 실패: {slot_error}")

            # 확정 슬롯 파싱
            selected_slot = None
            confirmed_str = record.get('면접자확정일시', '')
            if confirmed_str:
                try:
                    import re
                    # "2025-01-15 14:00(30분)" 형식 파싱
                    match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})$(\d+)분$', confirmed_str)
                    if match:
                        selected_slot = InterviewSlot(
                            date=match.group(1),
                            time=match.group(2),
                            duration=int(match.group(3))
                        )
                except Exception as slot_error:
                    logger.warning(f"확정슬롯 파싱 실패: {slot_error}")

            # 생성일시 파싱
            created_at = datetime.now()
            created_str = record.get('생성일시', '')
            if created_str:
                try:
                    created_at = datetime.strptime(created_str, '%Y-%m-%d %H:%M')
                except ValueError:
                    try:
                        created_at = datetime.fromisoformat(created_str.replace(' ', 'T'))
                    except:
                        pass

            # 상태 매핑
            status_map = {
                '면접관_일정대기': Config.Status.PENDING_INTERVIEWER,
                '면접자_선택대기': Config.Status.PENDING_CANDIDATE,
                '면접자_메일발송': Config.Status.CANDIDATE_EMAIL_SENT,
                '확정완료': Config.Status.CONFIRMED,
                '일정재조율요청': Config.Status.PENDING_CONFIRMATION,
                '취소': Config.Status.CANCELLED
            }
            
            status = status_map.get(record.get('상태', ''), Config.Status.PENDING_INTERVIEWER)

            # InterviewRequest 객체 생성
            request = InterviewRequest(
                id=normalize_request_id(record['요청ID']),  # 정규화 적용
                interviewer_id=record['면접관ID'],
                candidate_email=record['면접자이메일'],
                candidate_name=record['면접자명'],
                position_name=record['공고명'],
                detailed_position_name=record.get('상세공고명', ''),
                status=status,
                created_at=created_at,
                updated_at=datetime.now(),
                available_slots=available_slots,
                preferred_datetime_slots=preferred_slots,
                selected_slot=selected_slot,
                candidate_note=record.get('면접자요청사항', ''),
                candidate_phone=record.get('면접자전화번호', '')
            )

            logger.info(f"✅ 구글시트 레코드 변환 완료: {request.id}")
            return request

        except Exception as e:
            logger.error(f"❌ 시트 레코드 변환 중 오류: {e}")
            import traceback
            logger.error(traceback.format_exc())
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

    def health_check(self) -> dict:
        """시스템 상태 체크 (캐시 정보 포함)"""
        status = {
            'database': False,
            'google_sheet': False,
            'cache_stats': self.get_cache_stats(),
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
            status['google_sheet'] = False

        return status

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
        from utils import normalize_request_id, get_employee_info
        
        # ✅ ID 정규화 (구글시트와 DB 일치)
        normalized_id = normalize_request_id(request.id)
        
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
        
        preferred_datetime_str = " | ".join(request.preferred_datetime_slots) if request.preferred_datetime_slots else ""
        
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
        
        return [
            normalized_id,  # ✅ 정규화된 ID 사용
            request.created_at.strftime('%Y-%m-%d %H:%M'),
            request.position_name,
            getattr(request, 'detailed_position_name', ''),
            interviewer_id_str,
            interviewer_name_str,
            request.candidate_name,
            request.candidate_email,
            getattr(request, 'candidate_phone', ''),
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
                {'range': f'D{row_index}', 'values': [[detailed_name]]},  # D열: 상세공고명
                {'range': f'F{row_index}', 'values': [[interviewer_name_str]]},  # F열: 면접관이름
                {'range': f'I{row_index}', 'values': [[phone]]},  # I열: 면접자전화번호
                {'range': f'J{row_index}', 'values': [[request.status]]},  # J열: 상태
                {'range': f'K{row_index}', 'values': [[request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else ""]]},  # K열: 상태변경일시
                {'range': f'L{row_index}', 'values': [[preferred_datetime_str]]},  # ✅ L열: 인사팀제안일시
                {'range': f'M{row_index}', 'values': [[proposed_slots_str]]},  # ✅ M열: 면접관확정일시
                {'range': f'N{row_index}', 'values': [[confirmed_datetime]]},  # ✅ N열: 면접자확정일시
                {'range': f'O{row_index}', 'values': [[request.candidate_note or ""]]},  # O열: 면접자요청사항
                {'range': f'P{row_index}', 'values': [[datetime.now().strftime('%Y-%m-%d %H:%M')]]},  # P열: 마지막업데이트
                {'range': f'Q{row_index}', 'values': [[processing_time]]},  # Q열: 처리소요시간
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
                Config.Status.CANDIDATE_EMAIL_SENT: {'red': 0.9, 'green': 0.85, 'blue': 1.0},    # ✅ 연보라색 (새로 추가)
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
    
    def update_request_status_after_email(self, request_id: str, new_status: str = None) -> bool:
        """
        면접자 메일 발송 후 상태 업데이트
        
        Args:
            request_id: 요청 ID
            new_status: 새로운 상태 (기본값: "면접자_메일발송")
        
        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            from utils import normalize_request_id
            clean_id = normalize_request_id(request_id)
            
            # 기본 상태 설정
            if new_status is None:
                new_status = Config.Status.CANDIDATE_EMAIL_SENT
            
            # 1. SQLite DB 업데이트
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE interview_requests 
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                """, (new_status, datetime.now().isoformat(), clean_id))
            
            logger.info(f"✅ DB 상태 업데이트 완료: {clean_id} → {new_status}")
            
            # 2. 구글시트 업데이트
            if self.sheet:
                row_index = self._find_request_row(clean_id)
                
                if row_index:
                    # J열: 상태, K열: 상태변경일시
                    updates = [
                        {'range': f'J{row_index}', 'values': [[new_status]]},
                        {'range': f'K{row_index}', 'values': [[datetime.now().strftime('%Y-%m-%d %H:%M')]]}
                    ]
                    
                    self.sheet.batch_update(updates)
                    
                    # 상태별 색상 적용
                    self._apply_status_formatting(row_index, new_status)
                    
                    logger.info(f"✅ 구글시트 상태 업데이트 완료: {clean_id}")
                else:
                    logger.warning(f"⚠️ 구글시트에서 행을 찾을 수 없음: {clean_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 상태 업데이트 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def debug_request_search(self, request_id: str) -> dict:
        """요청 ID 검색 디버깅 정보"""
        from utils import normalize_request_id
        
        debug_info = {
            'original_id': request_id,
            'normalized_id': normalize_request_id(request_id),
            'sqlite_found': False,
            'sheet_found': False,
            'sqlite_total': 0,
            'sheet_total': 0,
            'similar_ids': []
        }
        
        try:
            clean_id = debug_info['normalized_id']
            
            # SQLite 검색
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM interview_requests")
                debug_info['sqlite_total'] = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT id FROM interview_requests WHERE id = ?", (clean_id,))
                debug_info['sqlite_found'] = cursor.fetchone() is not None
                
                # 유사한 ID들 찾기
                cursor = conn.execute("SELECT id FROM interview_requests LIMIT 10")
                all_ids = [row[0] for row in cursor.fetchall()]
                debug_info['similar_ids'] = all_ids

            # 구글 시트 검색
            if self.sheet:
                records = self.sheet.get_all_records()
                debug_info['sheet_total'] = len(records)
                
                for record in records:
                    sheet_id = normalize_request_id(record.get('요청ID', ''))
                    if sheet_id == clean_id:
                        debug_info['sheet_found'] = True
                        break
            
            return debug_info
            
        except Exception as e:
            debug_info['error'] = str(e)
            return debug_info

    def force_sync_specific_request(self, request_id: str) -> bool:
        """특정 요청의 강제 동기화"""
        try:
            from utils import normalize_request_id
            clean_id = normalize_request_id(request_id)
            
            if not self.sheet:
                logger.error("구글 시트 연결 없음")
                return False
            
            records = self.sheet.get_all_records()
            
            for record in records:
                sheet_id = normalize_request_id(record.get('요청ID', ''))
                if sheet_id == clean_id:
                    request = self._convert_sheet_record_to_request(record)
                    if request:
                        self.save_interview_request(request)
                        logger.info(f"✅ 강제 동기화 완료: {clean_id}")
                        return True
            
            logger.error(f"❌ 구글시트에서 요청을 찾을 수 없음: {clean_id}")
            return False
            
        except Exception as e:
            logger.error(f"❌ 강제 동기화 실패: {e}")
            return False











