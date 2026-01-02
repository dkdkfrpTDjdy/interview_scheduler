import threading
import time
from config import Config
from datetime import datetime, timedelta
import logging

# ✅ 로깅 설정 추가
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self, db_manager, email_service):
        self.db = db_manager
        self.email_service = email_service
        self.last_check = datetime.now()
        self.check_interval = 30  # 30초마다 체크
        self.logger = logging.getLogger(__name__)
        
    def start_monitoring(self):
        """구글시트 변경 모니터링 시작"""
        def monitor_loop():
            while True:
                try:
                    self.check_for_pending_candidate_emails()  # ✅ 추가
                    self.check_for_confirmations()
                    time.sleep(self.check_interval)
                except Exception as e:
                    self.logger.error(f"모니터링 오류: {e}")
                    time.sleep(60)

        
        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        self.logger.info("구글시트 모니터링 시작")

    # sync_manager.py에 추가
    def check_for_pending_candidate_emails(self):
        """K1 셀에 값이 있으나 이메일이 발송되지 않은 요청 확인"""
        try:
            requests = self.db.get_all_requests()
            
            for request in requests:
                # K1 셀에 값이 있고, 상태가 "면접자_선택대기"인데 이메일 발송 기록이 없는 경우
                if (request.status == Config.Status.PENDING_CANDIDATE and 
                    request.available_slots and 
                    len(request.available_slots) > 0):
                    
                    # 이메일 발송 시도
                    logger.info(f"주기적 체크: {request.id} 이메일 발송 시도")
                    self.email_service.send_candidate_invitation(request)
                    
        except Exception as e:
            logger.error(f"주기적 이메일 체크 실패: {e}")

    def _find_confirmed_col_idx(self, headers):
        """
        확정일시 컬럼 인덱스를 찾는다.
        우선순위:
        1) 면접자확정일시
        2) 확정일시
        3) '확정일시'가 포함된 컬럼 (fallback)
        """
        # 1) 정확히 일치하는 컬럼 우선
        priority_headers = ["면접자확정일시", "확정일시"]
        
        for target in priority_headers:
            for i, h in enumerate(headers):
                if h.strip() == target:
                    return i
        
        # 2) fallback: 포함되어 있으면 반환
        for i, h in enumerate(headers):
            if "확정일시" in h:
                return i
        
        return None

    
    def check_for_confirmations(self):
        """확정일시 변경 감지 및 이메일 발송"""
        try:
            if not self.db.sheet:
                return
            
            all_values = self.db.sheet.get_all_values()
            if len(all_values) < 2:
                return
            
            headers = all_values[0]
    
            # ✅ 확정일시 컬럼 찾기 (개선된 방식)
            confirmed_col_idx = self._find_confirmed_col_idx(headers)
    
            if confirmed_col_idx is None:
                self.logger.warning("⚠️ 확정일시 컬럼을 찾을 수 없습니다. 헤더를 확인하세요.")
                self.logger.warning(f"현재 헤더: {headers}")
                return
    
            # 데이터 행 체크
            for row_idx, row in enumerate(all_values[1:], start=2):
                if len(row) > confirmed_col_idx and row[confirmed_col_idx]:
                    request_id_short = row[0] if len(row) > 0 else ""
    
                    request = self.find_request_by_short_id(request_id_short)
                    if request and request.status != Config.Status.CONFIRMED:
                        self.process_confirmation(request, row[confirmed_col_idx])
    
        except Exception as e:
            self.logger.error(f"확정 체크 실패: {e}")

    
    def find_request_by_short_id(self, short_id):
        """짧은 ID로 요청 찾기"""
        try:
            requests = self.db.get_all_requests()
            for req in requests:
                if req.id.startswith(short_id.replace('...', '')):
                    return req
            return None
        except:
            return None
    
    def process_confirmation(self, request, confirmed_datetime_str):
        """확정 처리 및 이메일 발송"""
        try:
            # 확정일시 파싱
            # "2025-01-15 14:00(60분)" 형식 처리
            import re
            match = re.match(
                r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\((\d+)분\)',
                confirmed_datetime_str.strip()
            )
            
            if match:
                date_str, time_str, duration_str = match.groups()
                
                # InterviewSlot 생성
                from models import InterviewSlot
                selected_slot = InterviewSlot(
                    date=date_str,
                    time=time_str,
                    duration=int(duration_str)
                )
                
                # 요청 업데이트
                request.selected_slot = selected_slot
                request.status = Config.Status.CONFIRMED
                request.updated_at = datetime.now()
                
                # 데이터베이스 저장
                self.db.save_interview_request(request)
                
                # ✅ 이메일 발송 (모든 관련자에게)
                self.send_confirmation_emails(request)
                
                self.logger.info(f"확정 처리 완료: {request.id[:8]}...")
                
        except Exception as e:
            self.logger.error(f"확정 처리 실패: {e}")
    
    def send_confirmation_emails(self, request):
        """확정 알림 이메일 발송"""
        try:
            # 1. 면접자에게 확정 알림
            success1 = self.email_service.send_confirmation_notification(
                request, sender_type="system"
            )
            
            # 2. 면접관에게 확정 알림  
            success2 = self.email_service.send_interviewer_notification_on_candidate_selection(
                request
            )
            
            if success1 and success2:
                self.logger.info(f"확정 알림 이메일 발송 성공: {request.id[:8]}...")
            else:
                self.logger.warning(f"일부 이메일 발송 실패: {request.id[:8]}...")
                
        except Exception as e:
            self.logger.error(f"확정 알림 이메일 발송 실패: {e}")

