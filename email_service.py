import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import ssl
from typing import List, Optional
from config import Config
from models import InterviewRequest, InterviewSlot
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OutlookEmailService:
    def __init__(self):
        self.email_config = Config.EmailConfig
        self.company_domain = Config.COMPANY_DOMAIN
        
    def _create_smtp_connection(self):
        """Outlook SMTP 연결 생성"""
        try:
            # Exchange Server 또는 Outlook.com 자동 선택
            if "@outlook.com" in self.email_config.EMAIL_USER or "@hotmail.com" in self.email_config.EMAIL_USER:
                server = smtplib.SMTP(self.email_config.OUTLOOK_SMTP_SERVER, self.email_config.OUTLOOK_SMTP_PORT)
            else:
                # 회사 Exchange Server
                server = smtplib.SMTP(self.email_config.EXCHANGE_SERVER, self.email_config.EXCHANGE_PORT)
            
            server.starttls()
            server.login(self.email_config.EMAIL_USER, self.email_config.EMAIL_PASSWORD)
            return server
        except Exception as e:
            logger.error(f"SMTP 연결 실패: {e}")
            return None
    
    def send_email(self, to_emails: List[str], subject: str, body: str, 
                   cc_emails: Optional[List[str]] = None, 
                   bcc_emails: Optional[List[str]] = None,
                   is_html: bool = True):
        """Outlook을 통한 이메일 발송"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_config.EMAIL_USER
            msg['To'] = ', '.join(to_emails) if isinstance(to_emails, list) else to_emails
            msg['Subject'] = subject
            
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
            if bcc_emails:
                msg['Bcc'] = ', '.join(bcc_emails)
            
            # 회사 서명 추가
            company_signature = self._get_company_signature()
            full_body = body + company_signature
            
            # HTML과 텍스트 버전 모두 추가
            if is_html:
                html_part = MIMEText(full_body, 'html', 'utf-8')
                msg.attach(html_part)
                
                # 텍스트 버전도 추가 (호환성을 위해)
                text_body = self._html_to_text(full_body)
                text_part = MIMEText(text_body, 'plain', 'utf-8')
                msg.attach(text_part)
            else:
                text_part = MIMEText(full_body, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # 모든 수신자 목록 생성
            all_recipients = to_emails.copy() if isinstance(to_emails, list) else [to_emails]
            if cc_emails:
                all_recipients.extend(cc_emails)
            if bcc_emails:
                all_recipients.extend(bcc_emails)
            
            # SMTP 연결 및 발송
            server = self._create_smtp_connection()
            if server:
                server.send_message(msg, to_addrs=all_recipients)
                server.quit()
                logger.info(f"이메일 발송 성공: {to_emails}")
                return True
            else:
                logger.error("SMTP 서버 연결 실패")
                return False
                
        except Exception as e:
            logger.error(f"이메일 발송 실패: {e}")
            return False
    
    def _get_company_signature(self) -> str:
        """회사 이메일 서명"""
        return """
        <br><br>
        <div style="border-top: 1px solid #cccccc; padding-top: 10px; margin-top: 20px; font-size: 12px; color: #666666;">
            <p><strong>인사팀 면접 일정 조율 시스템</strong><br>
            본 메일은 자동 발송된 메일입니다.<br>
            문의사항이 있으시면 인사팀(hr@{})으로 연락해주세요.</p>
        </div>
        """.format(self.company_domain)
    
    def _html_to_text(self, html_content: str) -> str:
        """HTML을 텍스트로 변환 (간단한 변환)"""
        import re
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', html_content)
        # 연속된 공백 정리
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _get_interviewer_email(self, interviewer_id: str) -> str:
        """면접관 사번으로 이메일 주소 생성"""
        # 실제 구현시에는 DB에서 조회하거나 AD에서 조회
        return f"{interviewer_id.lower()}@{self.company_domain}"
    
    def send_interviewer_invitation(self, request: InterviewRequest):
        """면접관에게 일정 입력 요청 메일 발송"""
        interviewer_email = self._get_interviewer_email(request.interviewer_id)
        link = f"{Config.APP_URL}?role=interviewer&id={request.id}"
        
        subject = "📅 [면접 일정 조율] 면접 가능 일정 입력 요청"
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #0078d4; color: white; padding: 20px; text-align: center;">
                <h2 style="margin: 0;">📅 면접 일정 입력 요청</h2>
            </div>
            
            <div style="padding: 20px; background-color: #f8f9fa;">
                <p>안녕하세요, <strong>{request.interviewer_id}</strong>님</p>
                <p>새로운 면접 일정 조율 요청이 도착했습니다.</p>
                
                <div style="background-color: white; padding: 15px; border-radius: 8px; border-left: 4px solid #0078d4; margin: 20px 0;">
                    <h3 style="color: #0078d4; margin-top: 0;">📋 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold; width: 120px;">포지션</td>
                            <td style="padding: 8px 0;">{request.position_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">면접자</td>
                            <td style="padding: 8px 0;">{request.candidate_name} ({request.candidate_email})</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">요청 일시</td>
                            <td style="padding: 8px 0;">{request.created_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">요청 ID</td>
                            <td style="padding: 8px 0;">{request.id[:8]}...</td>
                        </tr>
                    </table>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{link}" 
                       style="background-color: #0078d4; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 16px;">
                        🗓️ 면접 가능 일정 입력하기
                    </a>
                </div>
                
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid #ffc107; margin: 20px 0;">
                    <p style="margin: 0;"><strong>💡 안내사항</strong></p>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>가능한 면접 일정을 여러 개 제안해주세요</li>
                        <li>일정 입력 후 자동으로 면접자에게 알림이 전송됩니다</li>
                        <li>면접자가 일정을 선택하면 확정 알림을 받게 됩니다</li>
                    </ul>
                </div>
                
                <div style="background-color: #e8f5e8; padding: 15px; border-radius: 8px; border-left: 4px solid #28a745; margin: 20px 0;">
                    <p style="margin: 0;"><strong>🔗 링크 접속이 안 되는 경우</strong></p>
                    <p style="margin: 5px 0;">아래 URL을 브라우저에 직접 복사해서 붙여넣으세요:</p>
                    <p style="background-color: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; word-break: break-all; margin: 10px 0;">
                        {link}
                    </p>
                </div>
            </div>
        </div>
        """
        
        # 인사팀을 CC에 추가
        return self.send_email(
            to_emails=[interviewer_email],
            cc_emails=Config.HR_EMAILS,
            subject=subject,
            body=body
        )
    
    def send_candidate_invitation(self, request: InterviewRequest):
        """면접자에게 일정 선택 요청 메일 발송"""
        interviewer_email = self._get_interviewer_email(request.interviewer_id)
        link = f"{Config.APP_URL}?role=candidate&id={request.id}"
        
        # 가능한 일정 목록 HTML 생성
        slots_html = ""
        for i, slot in enumerate(request.available_slots, 1):
            slots_html += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 10px; text-align: center; font-weight: bold;">{i}</td>
                <td style="padding: 10px;">{slot.date}</td>
                <td style="padding: 10px;">{slot.time}</td>
                <td style="padding: 10px;">{slot.duration}분</td>
            </tr>
            """
        
        subject = "📅 [면접 일정 조율] 면접 일정 선택 요청"
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #28a745; color: white; padding: 20px; text-align: center;">
                <h2 style="margin: 0;">📅 면접 일정 선택</h2>
            </div>
            
            <div style="padding: 20px; background-color: #f8f9fa;">
                <p>안녕하세요,</p>
                <p>면접관께서 제안하신 면접 일정 중에서 원하시는 시간을 선택해주세요.</p>
                
                <div style="background-color: white; padding: 15px; border-radius: 8px; border-left: 4px solid #28a745; margin: 20px 0;">
                    <h3 style="color: #28a745; margin-top: 0;">📋 면접 정보</h3>
                    <p><strong>면접관:</strong> {request.interviewer_id}</p>
                    <p><strong>담당 부서:</strong> 인사팀</p>
                </div>
                
                <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #28a745; margin-top: 0;">🗓️ 제안된 면접 일정</h3>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #ddd;">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th style="padding: 12px; border-bottom: 2px solid #ddd;">번호</th>
                                <th style="padding: 12px; border-bottom: 2px solid #ddd;">날짜</th>
                                <th style="padding: 12px; border-bottom: 2px solid #ddd;">시간</th>
                                <th style="padding: 12px; border-bottom: 2px solid #ddd;">소요시간</th>
                            </tr>
                        </thead>
                        <tbody>
                            {slots_html}
                        </tbody>
                    </table>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{link}" 
                       style="background-color: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                        ✅ 면접 일정 선택하기
                    </a>
                </div>
                
                <div style="background-color: #d1ecf1; padding: 15px; border-radius: 8px; border-left: 4px solid #17a2b8;">
                    <p style="margin: 0;"><strong>📝 참고사항</strong></p>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        <li>제안된 일정 중 선택하시거나, 다른 일정이 필요한 경우 요청사항을 입력해주세요</li>
                        <li>일정 선택 후 자동으로 모든 관련자에게 확정 알림이 전송됩니다</li>
                        <li>궁금한 사항이 있으시면 인사팀으로 연락해주세요</li>
                    </ul>
                </div>
            </div>
        </div>
        """
        
        return self.send_email(
            to_emails=[request.candidate_email],
            cc_emails=[interviewer_email] + Config.HR_EMAILS,
            subject=subject,
            body=body
        )
    
    def send_confirmation_notification(self, request: InterviewRequest):
        """면접 확정 알림 메일 발송"""
        interviewer_email = self._get_interviewer_email(request.interviewer_id)
        
        if request.status == Config.Status.CONFIRMED:
            subject = "✅ [면접 일정 확정] 면접 일정이 확정되었습니다"
            status_color = "#28a745"
            status_text = "확정 완료"
            
            # Outlook 달력 초대장 생성 (ICS 파일)
            calendar_invite = self._create_calendar_invite(request)
            
        else:
            subject = "⏳ [면접 일정 조율] 추가 조율이 필요합니다"
            status_color = "#ffc107"
            status_text = "추가 조율 필요"
            calendar_invite = None
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: {status_color}; color: white; padding: 20px; text-align: center;">
                <h2 style="margin: 0;">📅 면접 일정 {status_text}</h2>
            </div>
            
            <div style="padding: 20px; background-color: #f8f9fa;">
                <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid {status_color}; margin: 20px 0;">
                    <h3 style="color: {status_color}; margin-top: 0;">📋 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold; width: 120px;">면접관</td>
                            <td style="padding: 8px 0;">{request.interviewer_id} ({interviewer_email})</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">면접자</td>
                            <td style="padding: 8px 0;">{request.candidate_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">상태</td>
                            <td style="padding: 8px 0;"><span style="color: {status_color}; font-weight: bold;">{status_text}</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">처리 일시</td>
                            <td style="padding: 8px 0;">{request.updated_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
                        </tr>
        """
        
        if request.selected_slot:
            body += f"""
                        <tr style="background-color: #e8f5e8;">
                            <td style="padding: 8px 0; font-weight: bold;">확정 일시</td>
                            <td style="padding: 8px 0; font-weight: bold; color: #28a745;">
                                {request.selected_slot.date} {request.selected_slot.time} ({request.selected_slot.duration}분)
                            </td>
                        </tr>
            """
        
        body += """
                    </table>
                </div>
        """
        
        if request.candidate_note:
            body += f"""
                <div style="background-color: white; padding: 15px; border-radius: 8px; border-left: 4px solid #17a2b8; margin: 20px 0;">
                    <h4 style="color: #17a2b8; margin-top: 0;">💬 면접자 요청사항</h4>
                    <p style="margin: 0; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">{request.candidate_note}</p>
                </div>
            """
        
        if request.status == Config.Status.CONFIRMED:
            body += """
                <div style="background-color: #d4edda; padding: 15px; border-radius: 8px; border-left: 4px solid #28a745;">
                    <p style="margin: 0;"><strong>🎉 면접 일정이 확정되었습니다!</strong></p>
                    <p style="margin: 10px 0 0 0;">면접 준비 잘 부탁드립니다.</p>
                </div>
            """
        else:
            body += """
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid #ffc107;">
                    <p style="margin: 0;"><strong>⏳ 추가 일정 조율이 필요합니다</strong></p>
                    <p style="margin: 10px 0 0 0;">인사팀에서 면접자와 재조율 후 안내드리겠습니다.</p>
                </div>
            """
        
        body += """
            </div>
        </div>
        """
        
        # 모든 관련자에게 발송
        all_recipients = [interviewer_email, request.candidate_email]
        
        return self.send_email(
            to_emails=all_recipients,
            cc_emails=Config.HR_EMAILS,
            subject=subject,
            body=body
        )
    
    def _create_calendar_invite(self, request: InterviewRequest) -> str:
        """Outlook 달력 초대장 생성 (ICS 형식)"""
        if not request.selected_slot:
            return None
        
        # 실제 프로덕션에서는 icalendar 라이브러리 사용 권장
        # 여기서는 간단한 ICS 형식 생성
        
        from datetime import datetime, timedelta
        import uuid
        
        # 면접 시간 계산
        interview_date = datetime.strptime(request.selected_slot.date, '%Y-%m-%d')
        interview_time = datetime.strptime(request.selected_slot.time, '%H:%M').time()
        start_datetime = datetime.combine(interview_date.date(), interview_time)
        end_datetime = start_datetime + timedelta(minutes=request.selected_slot.duration)
        
        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//면접 일정 조율 시스템//NONSGML v1.0//EN
BEGIN:VEVENT
UID:{uuid.uuid4()}@{Config.COMPANY_DOMAIN}
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{start_datetime.strftime('%Y%m%dT%H%M%S')}
DTEND:{end_datetime.strftime('%Y%m%dT%H%M%S')}
SUMMARY:면접 - {request.candidate_email}
DESCRIPTION:면접자: {request.candidate_email}\\n면접관: {request.interviewer_id}\\n소요시간: {request.selected_slot.duration}분
LOCATION:회사 면접실
ORGANIZER:MAILTO:{Config.EmailConfig.EMAIL_USER}
ATTENDEE:MAILTO:{request.candidate_email}
ATTENDEE:MAILTO:{self._get_interviewer_email(request.interviewer_id)}
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR"""
        
        return ics_content

# 기존 EmailService를 OutlookEmailService로 교체

EmailService = OutlookEmailService
