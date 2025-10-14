import threading
import time
from datetime import datetime, timedelta
import logging

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
                    self.check_for_confirmations()
                    time.sleep(self.check_interval)
                except Exception as e:
                    self.logger.error(f"모니터링 오류: {e}")
                    time.sleep(60)  # 오류 시 1분 대기
        
        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        self.logger.info("구글시트 모니터링 시작")
    
    def check_for_confirmations(self):
        """L열(확정일시) 변경 감지 및 이메일 발송"""
        try:
            if not self.db.sheet:
                return
            
            # 전체 데이터 조회
            all_values = self.db.sheet.get_all_values()
            if len(all_values) < 2:
                return
            
            headers = all_values[0]
            confirmed_col_idx = None
            
            # L열(확정일시) 인덱스 찾기
            for i, header in enumerate(headers):
                if '확정일시' in header:
                    confirmed_col_idx = i
                    break
            
            if confirmed_col_idx is None:
                return
            
            # 데이터 행 체크
            for row_idx, row in enumerate(all_values[1:], start=2):
                if len(row) > confirmed_col_idx and row[confirmed_col_idx]:
                    # 확정일시가 있는 경우
                    request_id_short = row[0] if len(row) > 0 else ""
                    
                    # 해당 요청 찾기
                    request = self.find_request_by_short_id(request_id_short)
                    if request and request.status != "확정완료":
                        # 상태 업데이트 및 이메일 발송
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
            match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})$(\d+)분$', confirmed_datetime_str)
            
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
                request.status = "확정완료"
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
