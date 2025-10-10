import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import ssl
from typing import List, Optional
from config import Config
from models import InterviewRequest, InterviewSlot
from utils import get_employee_email, get_employee_info, format_date_korean
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
                # 회사 Exchange Server 또는 Gmail
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

    def send_interviewer_invitation(self, request: InterviewRequest):
        """면접관에게 일정 입력 요청 메일 발송 (실제 이메일 주소 사용)"""
        # 실제 면접관 이메일 주소 조회
        interviewer_email = get_employee_email(request.interviewer_id)
        interviewer_info = get_employee_info(request.interviewer_id)
        
        link = f"{Config.APP_URL}?role=interviewer&id={request.id}"
        
        subject = "📅 [면접 일정 조율] 면접 가능 일정 입력 요청"
        
        # 인사팀 제안 일시 테이블 생성
        preferred_schedule_html = ""
        if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
            preferred_schedule_html = """
            <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid #ffc107; margin: 20px 0;">
                <h4 style="color: #856404; margin-top: 0;">⭐ 인사팀 제안 희망일시</h4>
                <table style="width: 100%; border-collapse: collapse; border: 1px solid #ddd;">
                    <thead>
                        <tr style="background-color: #f8f9fa;">
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">번호</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">날짜</th>
                            <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">시간</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            for i, datetime_slot in enumerate(request.preferred_datetime_slots, 1):
                date_part, time_part = datetime_slot.split(' ')
                preferred_schedule_html += f"""
                        <tr>
                            <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">{i}</td>
                            <td style="padding: 10px; border: 1px solid #ddd; text-align: center;">{format_date_korean(date_part)}</td>
                            <td style="padding: 10px; border: 1px solid #ddd; text-align: center;">{time_part}</td>
                        </tr>
                """
            
            preferred_schedule_html += """
                    </tbody>
                </table>
                <p style="margin: 10px 0 0 0; font-size: 14px; color: #856404;"><strong>위 일시 중에서만 선택 가능합니다.</strong></p>
            </div>
            """
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 650px; margin: 0 auto;">
            <div style="background-color: #0078d4; color: white; padding: 25px; text-align: center; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0; font-size: 24px;">📅 면접 일정 입력 요청</h2>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa; border-radius: 0 0 8px 8px;">
                <p style="font-size: 16px; margin-bottom: 20px;">안녕하세요, <strong>{interviewer_info['name']}</strong>님 ({interviewer_info['department']})</p>
                <p style="font-size: 16px;">새로운 면접 일정 조율 요청이 도착했습니다.</p>
                
                <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #0078d4; margin: 25px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h3 style="color: #0078d4; margin-top: 0; margin-bottom: 15px;">📋 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 10px 0; font-weight: bold; width: 120px; color: #333;">포지션</td>
                            <td style="padding: 10px 0; color: #555;">{request.position_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 10px 0; font-weight: bold; color: #333;">면접자</td>
                            <td style="padding: 10px 0; color: #555;">{request.candidate_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px 0; font-weight: bold; color: #333;">이메일</td>
                            <td style="padding: 10px 0; color: #555;">{request.candidate_email}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 10px 0; font-weight: bold; color: #333;">요청 일시</td>
                            <td style="padding: 10px 0; color: #555;">{request.created_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px 0; font-weight: bold; color: #333;">요청 ID</td>
                            <td style="padding: 10px 0; color: #555; font-family: monospace;">{request.id[:8]}...</td>
                        </tr>
                    </table>
                </div>
                
                {preferred_schedule_html}
                
                <div style="text-align: center; margin: 35px 0;">
                    <a href="{link}" 
                       style="background-color: #0078d4; color: white; padding: 15px 35px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 16px; box-shadow: 0 2px 4px rgba(0,120,212,0.3);">
                        🗓️ 면접 가능 일정 입력하기
                    </a>
                </div>
                
                <div style="background-color: #e8f5e8; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745; margin: 25px 0;">
                    <p style="margin: 0; font-weight: bold; color: #155724;">💡 안내사항</p>
                    <ul style="margin: 15px 0; padding-left: 20px; color: #155724;">
                        <li>인사팀에서 제안한 일시 중에서만 선택 가능합니다</li>
                        <li>가능한 면접 일정을 여러 개 선택해주세요</li>
                        <li>일정 입력 후 자동으로 면접자에게 알림이 전송됩니다</li>
                        <li>면접자가 일정을 선택하면 확정 알림을 받게 됩니다</li>
                    </ul>
                </div>
                
                <div style="background-color: #d1ecf1; padding: 20px; border-radius: 8px; border-left: 4px solid #0c5460; margin: 25px 0;">
                    <p style="margin: 0; font-weight: bold; color: #0c5460;">🔗 링크 접속이 안 되는 경우</p>
                    <p style="margin: 10px 0; color: #0c5460;">아래 URL을 브라우저에 직접 복사해서 붙여넣으세요:</p>
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 4px; font-family: monospace; word-break: break-all; margin: 15px 0; border: 1px solid #dee2e6;">
                        {link}
                    </div>
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
        """면접자에게 일정 선택 요청 메일 발송 (HTML 테이블 형식)"""
        interviewer_info = get_employee_info(request.interviewer_id)
        candidate_link = f"{Config.APP_URL.replace('app.py', 'candidate_app.py')}?id={request.id}"
        
        # 가능한 일정 목록 HTML 테이블 생성
        slots_html = ""
        for i, slot in enumerate(request.available_slots, 1):
            slots_html += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 12px; text-align: center; font-weight: bold; background-color: #f8f9fa;">{i}</td>
                <td style="padding: 12px; text-align: center;">{format_date_korean(slot.date)}</td>
                <td style="padding: 12px; text-align: center; font-weight: bold; color: #0078d4;">{slot.time}</td>
                <td style="padding: 12px; text-align: center;">{slot.duration}분</td>
            </tr>
            """
        
        subject = "📅 [면접 일정 선택] 면접 일정을 선택해주세요"
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 650px; margin: 0 auto;">
            <div style="background-color: #28a745; color: white; padding: 25px; text-align: center; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0; font-size: 24px;">📅 면접 일정 선택</h2>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa; border-radius: 0 0 8px 8px;">
                <p style="font-size: 16px; margin-bottom: 10px;">안녕하세요, <strong>{request.candidate_name}</strong>님</p>
                <p style="font-size: 16px; margin-bottom: 25px;">면접관께서 제안하신 면접 일정 중에서 원하시는 시간을 선택해주세요.</p>
                
                <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745; margin: 25px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h3 style="color: #28a745; margin-top: 0; margin-bottom: 15px;">📋 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 10px 0; font-weight: bold; width: 120px; color: #333;">포지션</td>
                            <td style="padding: 10px 0; color: #555;">{request.position_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 10px 0; font-weight: bold; color: #333;">면접관</td>
                            <td style="padding: 10px 0; color: #555;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px 0; font-weight: bold; color: #333;">요청 ID</td>
                            <td style="padding: 10px 0; color: #555; font-family: monospace;">{request.id[:8]}...</td>
                        </tr>
                    </table>
                </div>
                
                <div style="background-color: white; padding: 25px; border-radius: 8px; margin: 25px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h3 style="color: #28a745; margin-top: 0; margin-bottom: 20px;">🗓️ 제안된 면접 일정</h3>
                    <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden;">
                        <thead>
                            <tr style="background-color: #28a745; color: white;">
                                <th style="padding: 15px; text-align: center; font-weight: bold;">번호</th>
                                <th style="padding: 15px; text-align: center; font-weight: bold;">날짜</th>
                                <th style="padding: 15px; text-align: center; font-weight: bold;">시간</th>
                                <th style="padding: 15px; text-align: center; font-weight: bold;">소요시간</th>
                            </tr>
                        </thead>
                        <tbody>
                            {slots_html}
                        </tbody>
                    </table>
                </div>
                
                <div style="text-align: center; margin: 35px 0;">
                    <a href="{candidate_link}" 
                       style="background-color: #28a745; color: white; padding: 15px 35px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; font-size: 16px; box-shadow: 0 2px 4px rgba(40,167,69,0.3);">
                        ✅ 면접 일정 선택하기
                    </a>
                </div>
                
                <div style="background-color: #d1ecf1; padding: 20px; border-radius: 8px; border-left: 4px solid #17a2b8;">
                    <p style="margin: 0; font-weight: bold; color: #0c5460;">📝 참고사항</p>
                    <ul style="margin: 15px 0; padding-left: 20px; color: #0c5460;">
                        <li>제안된 일정 중 선택하시거나, 다른 일정이 필요한 경우 요청사항을 입력해주세요</li>
                        <li>일정 선택 후 자동으로 모든 관련자에게 확정 알림이 전송됩니다</li>
                        <li>궁금한 사항이 있으시면 인사팀으로 연락해주세요</li>
                        <li>면접 당일 10분 전까지 도착해주시기 바랍니다</li>
                    </ul>
                </div>
                
                <div style="background-color: #fff3cd; padding: 20px; border-radius: 8px; border-left: 4px solid #856404; margin: 25px 0;">
                    <p style="margin: 0; font-weight: bold; color: #856404;">🔗 링크가 작동하지 않는 경우</p>
                    <p style="margin: 10px 0; color: #856404;">아래 URL을 복사해서 브라우저에 직접 입력해주세요:</p>
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 4px; font-family: monospace; word-break: break-all; margin: 15px 0; border: 1px solid #dee2e6;">
                        {candidate_link}
                    </div>
                </div>
            </div>
        </div>
        """
        
        interviewer_email = get_employee_email(request.interviewer_id)
        
        return self.send_email(
            to_emails=[request.candidate_email],
            cc_emails=[interviewer_email] + Config.HR_EMAILS,
            subject=subject,
            body=body
        )

    def send_confirmation_notification(self, request: InterviewRequest):
        """면접 확정 알림 메일 발송 (HTML 테이블 기반)"""
        interviewer_email = get_employee_email(request.interviewer_id)
        interviewer_info = get_employee_info(request.interviewer_id)
        
        if request.status == Config.Status.CONFIRMED:
            subject = "✅ [면접 일정 확정] 면접 일정이 확정되었습니다"
            status_color = "#28a745"
            status_text = "확정 완료"
            status_icon = "🎉"
            
        else:
            subject = "⏳ [면접 일정 조율] 추가 조율이 필요합니다"
            status_color = "#ffc107"
            status_text = "추가 조율 필요"
            status_icon = "⏳"
        
        # 확정 일시 테이블
        confirmed_schedule_html = ""
        if request.selected_slot:
            confirmed_schedule_html = f"""
            <div style="background-color: #d4edda; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745; margin: 25px 0;">
                <h3 style="color: #155724; margin-top: 0; margin-bottom: 15px;">{status_icon} 확정된 면접 일시</h3>
                <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden;">
                    <thead>
                        <tr style="background-color: #28a745; color: white;">
                            <th style="padding: 15px; text-align: center;">날짜</th>
                            <th style="padding: 15px; text-align: center;">시간</th>
                            <th style="padding: 15px; text-align: center;">소요시간</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 15px; text-align: center; font-weight: bold; font-size: 16px;">{format_date_korean(request.selected_slot.date)}</td>
                            <td style="padding: 15px; text-align: center; font-weight: bold; font-size: 16px; color: #28a745;">{request.selected_slot.time}</td>
                            <td style="padding: 15px; text-align: center; font-weight: bold; font-size: 16px;">{request.selected_slot.duration}분</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 650px; margin: 0 auto;">
            <div style="background-color: {status_color}; color: white; padding: 25px; text-align: center; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0; font-size: 24px;">{status_icon} 면접 일정 {status_text}</h2>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa; border-radius: 0 0 8px 8px;">
                <div style="background-color: white; padding: 25px; border-radius: 8px; border-left: 4px solid {status_color}; margin: 25px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h3 style="color: {status_color}; margin-top: 0; margin-bottom: 20px;">📋 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 12px 0; font-weight: bold; width: 140px; color: #333;">포지션</td>
                            <td style="padding: 12px 0; color: #555;">{request.position_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 12px 0; font-weight: bold; color: #333;">면접관</td>
                            <td style="padding: 12px 0; color: #555;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; font-weight: bold; color: #333;">면접관 이메일</td>
                            <td style="padding: 12px 0; color: #555;">{interviewer_email}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 12px 0; font-weight: bold; color: #333;">면접자</td>
                            <td style="padding: 12px 0; color: #555;">{request.candidate_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; font-weight: bold; color: #333;">면접자 이메일</td>
                            <td style="padding: 12px 0; color: #555;">{request.candidate_email}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 12px 0; font-weight: bold; color: #333;">상태</td>
                            <td style="padding: 12px 0;"><span style="color: {status_color}; font-weight: bold; font-size: 16px;">{status_text}</span></td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; font-weight: bold; color: #333;">처리 일시</td>
                            <td style="padding: 12px 0; color: #555;">{request.updated_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 12px 0; font-weight: bold; color: #333;">요청 ID</td>
                            <td style="padding: 12px 0; color: #555; font-family: monospace;">{request.id[:8]}...</td>
                        </tr>
                    </table>
                </div>
                
                {confirmed_schedule_html}
        """
        
        if request.candidate_note:
            body += f"""
                <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #17a2b8; margin: 25px 0;">
                    <h4 style="color: #17a2b8; margin-top: 0; margin-bottom: 15px;">💬 면접자 요청사항</h4>
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 4px; border: 1px solid #dee2e6;">
                        <p style="margin: 0; color: #495057; line-height: 1.6;">{request.candidate_note}</p>
                    </div>
                </div>
            """
        
        if request.status == Config.Status.CONFIRMED:
            body += """
                <div style="background-color: #d4edda; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745;">
                    <p style="margin: 0; font-weight: bold; color: #155724; font-size: 16px;">🎉 면접 일정이 확정되었습니다!</p>
                    <ul style="margin: 15px 0; padding-left: 20px; color: #155724;">
                        <li>면접 당일 10분 전까지 도착해주시기 바랍니다</li>
                        <li>면접 준비에 차질이 없도록 미리 준비해주세요</li>
                        <li>일정 변경이 필요한 경우 인사팀에 연락해주세요</li>
                    </ul>
                </div>
            """
        else:
            body += """
                <div style="background-color: #fff3cd; padding: 20px; border-radius: 8px; border-left: 4px solid #ffc107;">
                    <p style="margin: 0; font-weight: bold; color: #856404; font-size: 16px;">⏳ 추가 일정 조율이 필요합니다</p>
                    <p style="margin: 15px 0 0 0; color: #856404;">인사팀에서 면접자 요청사항을 검토한 후 재조율하여 안내드리겠습니다.</p>
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
        """Outlook 달력 초대장 생성 (ICS 형식) - 향후 구현"""
        # ICS 파일 생성 로직은 추후 구현
        # icalendar 라이브러리 사용 권장
        pass

# 기존 EmailService를 OutlookEmailService로 교체
EmailService = OutlookEmailService
