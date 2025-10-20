import sqlite3
import json
import logging
import streamlit as st
from typing import List, Optional
from datetime import datetime
from models import InterviewRequest, InterviewSlot
from config import Config
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import time
import random
from functools import wraps
import os


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
                        status TEXT NOT NULL,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP,
                        available_slots TEXT,
                        preferred_datetime_slots TEXT,
                        selected_slot TEXT,
                        candidate_note TEXT
                    )
                """)
                
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
        
    def save_interviewer_response(self, request_id: str, interviewer_id: str, slots: List[InterviewSlot]):
        """
        개별 면접관의 일정 응답 저장
        
        Args:
            request_id: 요청 ID
            interviewer_id: 면접관 ID (단일)
            slots: 해당 면접관이 선택한 슬롯
        """
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
        """
        특정 요청에 대한 모든 면접관의 응답 조회
        
        Returns:
            {
                '223286': [InterviewSlot, ...],
                '223287': [InterviewSlot, ...],
            }
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT interviewer_id, available_slots FROM interviewer_responses WHERE request_id = ?",
                    (request_id,)
                )
                rows = cursor.fetchall()
            
            responses = {}
            for row in rows:
                interviewer_id = row[0]
                slots_data = json.loads(row[1])
                slots = [InterviewSlot(**slot) for slot in slots_data]
                responses[interviewer_id] = slots
            
            return responses
            
        except Exception as e:
            logger.error(f"면접관 응답 조회 실패: {e}")
            return {}


    def check_all_interviewers_responded(self, request: InterviewRequest) -> tuple[bool, int, int]:
        """
        모든 면접관이 일정을 입력했는지 확인
        
        Returns:
            (전체 응답 여부, 응답한 면접관 수, 전체 면접관 수)
        """
        try:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            
            # 단일 면접관인 경우
            if len(interviewer_ids) == 1:
                has_slots = request.available_slots and len(request.available_slots) > 0
                return has_slots, (1 if has_slots else 0), 1
            
            # 복수 면접관인 경우 - interviewer_responses 테이블 확인
            responses = self.get_interviewer_responses(request.id)
            responded_count = len(responses)
            total_count = len(interviewer_ids)
            
            all_responded = responded_count == total_count
            
            logger.info(f"면접관 응답 현황: {responded_count}/{total_count}")
            
            return all_responded, responded_count, total_count
            
        except Exception as e:
            logger.error(f"면접관 응답 확인 실패: {e}")
            return False, 0, len(request.interviewer_id.split(','))


    def get_common_available_slots(self, request: InterviewRequest) -> List[InterviewSlot]:
        """
        모든 면접관이 공통으로 선택한 30분 단위 타임슬롯 반환
        
        Returns:
            List[InterviewSlot]: 공통 타임슬롯
        """
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
        
    @retry_on_failure(max_retries=3, delay=2)
    def init_google_sheet(self):
        """구글 시트 초기화"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # 🔧 여러 방법으로 인증 정보 가져오기
            service_account_info = None
            
            # 방법 1: Streamlit Secrets (새로운 TOML 구조)
            try:
                if hasattr(st, 'secrets') and "google_credentials" in st.secrets:
                    logger.info("🔍 TOML 구조로 Secrets 읽기 시도...")
                    
                    # private_key 줄바꿈 처리 및 정리
                    private_key = st.secrets["google_credentials"]["private_key"]
                    logger.info(f"🔧 원본 private_key 길이: {len(private_key)}")
                    
                    # 🔧 키 정리 과정
                    if "\\n" in private_key:
                        private_key = private_key.replace("\\n", "\n")
                        logger.info("🔧 \\n을 실제 줄바꿈으로 변환 완료")
                    
                    # 🔧 추가 정리: 공백 및 특수문자 제거
                    private_key = private_key.strip()
                    lines = private_key.split('\n')
                    cleaned_lines = []
                    
                    for line in lines:
                        line = line.strip()
                        if line:  # 빈 줄 제거
                            cleaned_lines.append(line)
                    
                    private_key = '\n'.join(cleaned_lines)
                    logger.info(f"🔧 정리된 private_key 줄 수: {len(cleaned_lines)}")
                    logger.info(f"🔧 정리된 private_key 시작: {private_key[:50]}")
                    logger.info(f"🔧 정리된 private_key 끝: {private_key[-50:]}")
                    
                    # 🔧 키 유효성 검증
                    if not private_key.startswith("-----BEGIN PRIVATE KEY-----"):
                        logger.error("❌ private_key가 올바른 형식이 아닙니다")
                        raise ValueError("Invalid private key format")
                    
                    if not private_key.endswith("-----END PRIVATE KEY-----"):
                        logger.error("❌ private_key 끝이 올바르지 않습니다")
                        raise ValueError("Invalid private key ending")
                    
                    # 🔧 service_account_info 생성
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
                    logger.info("✅ Streamlit Secrets에서 인증 정보 로드 (TOML 구조)")
                    
            except Exception as e:
                logger.warning(f"TOML Secrets 읽기 실패: {e}")
            
            # 방법 2: 기존 JSON 방식 (하위 호환)
            if not service_account_info:
                try:
                    if hasattr(st, 'secrets') and "GOOGLE_CREDENTIALS_JSON" in st.secrets:
                        json_str = st.secrets["GOOGLE_CREDENTIALS_JSON"]
                        service_account_info = json.loads(json_str)
                        logger.info("✅ Streamlit Secrets에서 인증 정보 로드 (JSON 구조)")
                except Exception as e:
                    logger.warning(f"JSON Secrets 읽기 실패: {e}")
            
            # 방법 3: 환경변수
            if not service_account_info:
                try:
                    json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
                    if json_str:
                        service_account_info = json.loads(json_str)
                        logger.info("✅ 환경변수에서 인증 정보 로드")
                except Exception as e:
                    logger.warning(f"환경변수 읽기 실패: {e}")
            
            # 방법 4: 로컬 파일
            if not service_account_info:
                try:
                    if os.path.exists('service-account.json'):
                        with open('service-account.json', 'r') as f:
                            service_account_info = json.load(f)
                        logger.info("✅ 로컬 파일에서 인증 정보 로드")
                except Exception as e:
                    logger.warning(f"파일 읽기 실패: {e}")
                    
            if not service_account_info:
                logger.error("❌ 모든 방법으로 인증 정보를 가져올 수 없습니다")
                self.gc = None
                self.sheet = None
                return
            
            # Google 인증 (🔧 임시 파일 방식 사용)
            try:
                logger.info("🔄 임시 파일 방식으로 Google 인증 시도...")
                import tempfile
                
                # 임시 파일 생성
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                    json.dump(service_account_info, temp_file)
                    temp_path = temp_file.name
                
                # 임시 파일로 인증
                credentials = Credentials.from_service_account_file(temp_path, scopes=scope)
                
                # 임시 파일 삭제
                os.unlink(temp_path)
                
                logger.info("✅ 임시 파일 방식으로 Google 인증 성공")
                
            except Exception as e:
                logger.error(f"❌ Google 인증 실패: {e}")
                raise
            
            self.gc = gspread.authorize(credentials)
            logger.info("✅ gspread 인증 완료")
            
            # 시트 연결
            sheet_id = st.secrets["GOOGLE_SHEET_ID"]
            self.sheet = self.gc.open_by_key(sheet_id).sheet1
            logger.info("✅ 구글 시트 연결 성공")
            
            # 헤더 설정
            headers = [
                "요청ID", "생성일시", "포지션명", "면접관ID", "면접관이름", "면접자명", 
                "면접자이메일", "상태", "상태변경일시", "희망일시목록", "제안일시목록", 
                "확정일시", "면접자요청사항", "마지막업데이트", "처리소요시간", "비고"
            ]
            
            try:
                existing_headers = self.sheet.row_values(1)
                if not existing_headers or len(existing_headers) < len(headers):
                    self._setup_sheet_headers(headers)
            except Exception as e:
                logger.info(f"새 시트 설정: {e}")
                self._setup_sheet_headers(headers)
                
            logger.info("🎉 구글 시트 초기화 완료!")
                
        except Exception as e:
            logger.error(f"❌ 구글 시트 초기화 실패: {e}")
            import traceback
            logger.error(f"상세 에러: {traceback.format_exc()}")
            self.gc = None
            self.sheet = None
    
    def _setup_sheet_headers(self, headers):
        """시트 헤더 설정"""
        try:
            # 기존 내용 클리어하고 헤더 추가
            self.sheet.clear()
            self.sheet.append_row(headers)
            
            # 헤더 스타일링
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
                    (request.updated_at or datetime.now()).isoformat(),
                    json.dumps([{"date": slot.date, "time": slot.time, "duration": slot.duration} 
                               for slot in request.available_slots]),
                    json.dumps(request.preferred_datetime_slots) if request.preferred_datetime_slots else None,
                    json.dumps({"date": request.selected_slot.date, "time": request.selected_slot.time, 
                               "duration": request.selected_slot.duration}) if request.selected_slot else None,
                    request.candidate_note or ""
                ))
                logger.info(f"면접 요청 저장 완료: {request.id[:8]}...")
            
            # 구글 시트 업데이트 (비동기적으로 처리)
            try:
                self.update_google_sheet(request)
            except Exception as e:
                logger.warning(f"구글 시트 업데이트 실패 (데이터는 저장됨): {e}")
                
        except Exception as e:
            logger.error(f"면접 요청 저장 실패: {e}")
            raise
    def find_overlapping_time_slots(self, request: InterviewRequest) -> List[InterviewSlot]:
        """
        모든 면접관이 공통으로 가능한 30분 단위 타임슬롯 찾기
        
        Returns:
            List[InterviewSlot]: 30분 단위로 분할된 중복 타임슬롯
        """
        try:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            
            # 단일 면접관인 경우 모든 슬롯 반환
            if len(interviewer_ids) == 1:
                return request.available_slots
            
            # 동일 포지션의 모든 요청 가져오기
            all_requests = self.get_all_requests()
            same_position_requests = [
                req for req in all_requests 
                if req.position_name == request.position_name 
                and req.status in [Config.Status.PENDING_CANDIDATE, Config.Status.CONFIRMED]
            ]
            
            # 각 면접관별 30분 단위 슬롯 수집
            interviewer_slot_sets = {}
            
            for req in same_position_requests:
                req_interviewer_ids = [id.strip() for id in req.interviewer_id.split(',')]
                
                for interviewer_id in req_interviewer_ids:
                    if interviewer_id in interviewer_ids:
                        if interviewer_id not in interviewer_slot_sets:
                            interviewer_slot_sets[interviewer_id] = set()
                        
                        # 각 슬롯을 "날짜_시간" 키로 변환
                        for slot in req.available_slots:
                            key = f"{slot.date}_{slot.time}"
                            interviewer_slot_sets[interviewer_id].add(key)
            
            # 모든 면접관이 공통으로 가능한 슬롯 찾기
            if not interviewer_slot_sets or len(interviewer_slot_sets) < len(interviewer_ids):
                logger.warning("일부 면접관의 일정이 없습니다.")
                return []
            
            # 교집합 계산
            common_slot_keys = set.intersection(*interviewer_slot_sets.values())
            
            # 키를 다시 InterviewSlot 객체로 변환
            overlapping_slots = []
            for key in common_slot_keys:
                date_part, time_part = key.split('_')
                overlapping_slots.append(InterviewSlot(
                    date=date_part,
                    time=time_part,
                    duration=30  # 고정 30분
                ))
            
            # 날짜/시간 순으로 정렬
            overlapping_slots.sort(key=lambda x: (x.date, x.time))
            
            logger.info(f"중복 타임슬롯 {len(overlapping_slots)}개 발견: {request.position_name}")
            return overlapping_slots
            
        except Exception as e:
            logger.error(f"중복 타임슬롯 찾기 실패: {e}")
            return []
        
    def get_available_slots_for_candidate(self, request: InterviewRequest) -> List[InterviewSlot]:
        """
        면접자가 선택 가능한 30분 단위 타임슬롯 조회 (이미 예약된 슬롯 제외)
        
        Returns:
            List[InterviewSlot]: 선택 가능한 30분 단위 타임슬롯
        """
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
        """
        면접자가 선택한 30분 타임슬롯 예약 (중복 예약 방지)
        
        Returns:
            bool: 예약 성공 여부
        """
        try:
            # 1. 해당 타임슬롯이 이미 예약되었는지 확인
            all_requests = self.get_all_requests()
            
            for req in all_requests:
                if (req.position_name == request.position_name 
                    and req.status == Config.Status.CONFIRMED 
                    and req.selected_slot 
                    and req.id != request.id):
                    
                    # 동일한 타임슬롯이 이미 예약됨
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
        
    def check_all_interviewers_responded(self, request: InterviewRequest) -> bool:
        """
        모든 면접관이 일정을 입력했는지 확인
        
        Returns:
            bool: 모든 면접관이 응답했으면 True
        """
        try:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            
            # 단일 면접관인 경우
            if len(interviewer_ids) == 1:
                return request.available_slots and len(request.available_slots) > 0
            
            # 복수 면접관인 경우 - 동일 포지션의 모든 요청 확인
            all_requests = self.get_all_requests()
            same_position_requests = [
                req for req in all_requests
                if req.position_name == request.position_name
                and req.interviewer_id == request.interviewer_id
            ]
            
            # 각 면접관별 응답 여부 체크
            responded_interviewers = set()
            
            for req in same_position_requests:
                if req.available_slots and len(req.available_slots) > 0:
                    # 이 요청을 처리한 면접관 ID 추출
                    req_interviewer_ids = [id.strip() for id in req.interviewer_id.split(',')]
                    for interviewer_id in req_interviewer_ids:
                        responded_interviewers.add(interviewer_id)
            
            # 모든 면접관이 응답했는지 확인
            all_responded = all(interviewer_id in responded_interviewers for interviewer_id in interviewer_ids)
            
            logger.info(f"면접관 응답 현황: {len(responded_interviewers)}/{len(interviewer_ids)} - {responded_interviewers}")
            
            return all_responded
            
        except Exception as e:
            logger.error(f"면접관 응답 확인 실패: {e}")
            return False


    def get_common_available_slots(self, request: InterviewRequest) -> List[InterviewSlot]:
        """
        모든 면접관이 공통으로 선택한 30분 단위 타임슬롯 반환
        
        Returns:
            List[InterviewSlot]: 공통 타임슬롯
        """
        try:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            
            # 단일 면접관인 경우
            if len(interviewer_ids) == 1:
                return request.available_slots
            
            # 복수 면접관인 경우
            all_requests = self.get_all_requests()
            same_position_requests = [
                req for req in all_requests
                if req.position_name == request.position_name
                and req.interviewer_id == request.interviewer_id
            ]
            
            # 각 면접관별 타임슬롯 수집
            interviewer_slot_sets = {}
            
            for req in same_position_requests:
                if req.available_slots and len(req.available_slots) > 0:
                    req_interviewer_ids = [id.strip() for id in req.interviewer_id.split(',')]
                    
                    for interviewer_id in req_interviewer_ids:
                        if interviewer_id not in interviewer_slot_sets:
                            interviewer_slot_sets[interviewer_id] = set()
                        
                        # 각 슬롯을 "날짜_시간" 키로 변환
                        for slot in req.available_slots:
                            key = f"{slot.date}_{slot.time}"
                            interviewer_slot_sets[interviewer_id].add(key)
            
            # 모든 면접관이 공통으로 선택한 슬롯 찾기
            if len(interviewer_slot_sets) < len(interviewer_ids):
                logger.warning(f"일부 면접관이 아직 응답하지 않았습니다: {len(interviewer_slot_sets)}/{len(interviewer_ids)}")
                return []
            
            # 교집합 계산
            common_slot_keys = set.intersection(*interviewer_slot_sets.values())
            
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

    
    def get_interview_request(self, request_id: str) -> Optional[InterviewRequest]:
        """면접 요청 조회"""
        try:
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
                    try:
                        slots_data = json.loads(row[8])
                        available_slots = [InterviewSlot(**slot) for slot in slots_data]
                    except json.JSONDecodeError as e:
                        logger.warning(f"available_slots 파싱 실패: {e}")
                
                preferred_datetime_slots = []
                if row[9]:  # preferred_datetime_slots
                    try:
                        preferred_datetime_slots = json.loads(row[9])
                    except json.JSONDecodeError as e:
                        logger.warning(f"preferred_datetime_slots 파싱 실패: {e}")
                
                selected_slot = None
                if row[10]:  # selected_slot
                    try:
                        slot_data = json.loads(row[10])
                        selected_slot = InterviewSlot(**slot_data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"selected_slot 파싱 실패: {e}")
                
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
            
            # 데이터 준비
            row_data = self._prepare_sheet_row_data(request, interviewer_info)
            
            # 시트에 추가
            self.sheet.append_row(row_data)
            
            # 상태별 색상 적용
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
            # 기존 행 찾기
            row_index = self._find_request_row(request.id)
            
            if row_index:
                # 배치 업데이트 실행
                updates = self._prepare_batch_updates(request, row_index)
                if updates:
                    self.sheet.batch_update(updates)
                    
                # 상태별 색상 적용
                self._apply_status_formatting(row_index, request.status)
                
                logger.info(f"구글 시트 업데이트 완료: {request.id[:8]}...")
                return True
            else:
                # 새로 추가
                return self.save_to_google_sheet(request)
                
        except Exception as e:
            logger.error(f"구글 시트 업데이트 실패: {e}")
            return False
    
    def _find_request_row(self, request_id: str) -> Optional[int]:
        """요청 ID로 행 번호 찾기"""
        try:
            short_id = request_id[:8] + "..."
            all_records = self.sheet.get_all_records()
            
            for i, record in enumerate(all_records):
                if record.get('요청ID') == short_id:
                    return i + 2  # 헤더 행 고려
            return None
        except Exception as e:
            logger.error(f"행 찾기 실패: {e}")
            return None
    
    def _prepare_sheet_row_data(self, request: InterviewRequest, interviewer_info: dict = None) -> list:
        """시트 행 데이터 준비 (복수 면접관 지원)"""
        from utils import get_employee_info  # ✅ import 추가
        
        # ✅ 1. 복수 면접관 정보 처리
        interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
        interviewer_names = []
        interviewer_departments = []
        
        for interviewer_id in interviewer_ids:
            info = get_employee_info(interviewer_id)
            interviewer_names.append(info.get('name', interviewer_id))
            interviewer_departments.append(info.get('department', '미확인'))
        
        # 쉼표로 구분된 문자열로 변환
        interviewer_id_str = ", ".join(interviewer_ids)
        interviewer_name_str = ", ".join(interviewer_names)
        interviewer_dept_str = ", ".join(set(interviewer_departments))  # 중복 제거
        
        # ✅ 2. 희망일시 문자열 생성
        preferred_datetime_str = ""
        if request.preferred_datetime_slots:
            preferred_datetime_str = " | ".join(request.preferred_datetime_slots)
        
        # ✅ 3. 제안일시 문자열 생성
        proposed_slots_str = ""
        if request.available_slots:
            proposed_slots_str = " | ".join([
                f"{slot.date} {slot.time}({slot.duration}분)" 
                for slot in request.available_slots
            ])
        
        # ✅ 4. 확정일시
        confirmed_datetime = ""
        if request.selected_slot:
            confirmed_datetime = f"{request.selected_slot.date} {request.selected_slot.time}({request.selected_slot.duration}분)"
        
        # ✅ 5. 처리 소요시간 계산
        processing_time = ""
        if request.updated_at and request.status == Config.Status.CONFIRMED:
            time_diff = request.updated_at - request.created_at
            hours = int(time_diff.total_seconds() // 3600)
            processing_time = f"{hours}시간" if hours > 0 else "1시간 미만"
        
        # ✅ 6. 상태변경일시
        status_changed_at = request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else request.created_at.strftime('%Y-%m-%d %H:%M')
        
        # ✅ 7. 비고 (면접관 부서 정보 추가)
        remarks = f"담당부서: {interviewer_dept_str}" if len(interviewer_ids) > 1 else ""
        
        return [
            request.id[:8] + "...",                    # 요청ID
            request.created_at.strftime('%Y-%m-%d %H:%M'),  # 생성일시
            request.position_name,                     # 포지션명
            interviewer_id_str,                        # 면접관ID (복수 지원)
            interviewer_name_str,                      # 면접관이름 (복수 지원)
            request.candidate_name,                    # 면접자명
            request.candidate_email,                   # 면접자이메일
            request.status,                            # 상태
            status_changed_at,                         # 상태변경일시
            preferred_datetime_str,                    # 희망일시목록
            proposed_slots_str,                        # 제안일시목록
            confirmed_datetime,                        # 확정일시
            request.candidate_note or "",              # 면접자요청사항
            datetime.now().strftime('%Y-%m-%d %H:%M'), # 마지막업데이트
            processing_time,                           # 처리소요시간
            remarks                                    # 비고
        ]
    
    def _prepare_batch_updates(self, request: InterviewRequest, row_index: int) -> list:
        """배치 업데이트 데이터 준비 (복수 면접관 지원)"""
        try:
            from utils import get_employee_info  # ✅ import 추가
            
            # ✅ 복수 면접관 정보 처리
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            interviewer_names = []
            
            for interviewer_id in interviewer_ids:
                info = get_employee_info(interviewer_id)
                interviewer_names.append(info.get('name', interviewer_id))
            
            interviewer_name_str = ", ".join(interviewer_names)
            
            # 확정일시
            confirmed_datetime = ""
            if request.selected_slot:
                confirmed_datetime = f"{request.selected_slot.date} {request.selected_slot.time}({request.selected_slot.duration}분)"
            
            # 제안일시
            proposed_slots_str = ""
            if request.available_slots:
                proposed_slots_str = " | ".join([
                    f"{slot.date} {slot.time}({slot.duration}분)" 
                    for slot in request.available_slots
                ])
            
            # 희망일시
            preferred_datetime_str = ""
            if request.preferred_datetime_slots:
                preferred_datetime_str = " | ".join(request.preferred_datetime_slots)
            
            # 처리 소요시간
            processing_time = ""
            if request.updated_at and request.status == Config.Status.CONFIRMED:
                time_diff = request.updated_at - request.created_at
                hours = int(time_diff.total_seconds() // 3600)
                processing_time = f"{hours}시간" if hours > 0 else "1시간 미만"
            
            # 배치 업데이트 데이터
            updates = [
                {
                    'range': f'E{row_index}', 
                    'values': [[interviewer_name_str]]  # ✅ 복수 면접관 이름
                },
                {
                    'range': f'H{row_index}', 
                    'values': [[request.status]]
                },
                {
                    'range': f'I{row_index}', 
                    'values': [[request.updated_at.strftime('%Y-%m-%d %H:%M') if request.updated_at else ""]]
                },
                {
                    'range': f'J{row_index}', 
                    'values': [[preferred_datetime_str]]
                },
                {
                    'range': f'K{row_index}', 
                    'values': [[proposed_slots_str]]
                },
                {
                    'range': f'L{row_index}', 
                    'values': [[confirmed_datetime]]
                },
                {
                    'range': f'M{row_index}', 
                    'values': [[request.candidate_note or ""]]
                },
                {
                    'range': f'N{row_index}', 
                    'values': [[datetime.now().strftime('%Y-%m-%d %H:%M')]]
                },
                {
                    'range': f'O{row_index}', 
                    'values': [[processing_time]]
                },
            ]
            
            return updates
            
        except Exception as e:
            logger.error(f"배치 업데이트 데이터 준비 실패: {e}")
            return []
    
    def _apply_status_formatting(self, row_index: int, status: str):
        """상태별 행 색상 적용"""
        try:
            color_map = {
                Config.Status.PENDING_INTERVIEWER: {'red': 1.0, 'green': 0.9, 'blue': 0.8},  # 연한 주황색
                Config.Status.PENDING_CANDIDATE: {'red': 0.8, 'green': 0.9, 'blue': 1.0},  # 연한 파란색
                Config.Status.CONFIRMED: {'red': 0.8, 'green': 1.0, 'blue': 0.8},  # 연한 초록색
                Config.Status.PENDING_CONFIRMATION: {'red': 1.0, 'green': 1.0, 'blue': 0.8},  # 연한 노란색
                Config.Status.CANCELLED: {'red': 0.9, 'green': 0.9, 'blue': 0.9},  # 연한 회색
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
                
                # Streamlit 캐시 클리어
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
                        processing_times.append(time_diff.total_seconds() / 3600)  # 시간 단위
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
        
        # 데이터베이스 체크
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("SELECT 1").fetchone()
            status['database'] = True
        except Exception as e:
            logger.error(f"데이터베이스 체크 실패: {e}")
        
        # 구글 시트 체크
        try:
            if self.sheet:
                self.sheet.row_values(1)  # 첫 번째 행 읽기 시도
                status['google_sheet'] = True
        except Exception as e:
            logger.error(f"구글 시트 체크 실패: {e}")
        
        return status






