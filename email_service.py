import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import ssl
from typing import List, Optional
from config import Config
from models import InterviewRequest, InterviewSlot
from utils import get_employee_email, get_employee_info, format_date_korean, create_calendar_invite
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.email_config = Config.EmailConfig
        self.company_domain = Config.COMPANY_DOMAIN

    def _create_smtp_connection(self):
        """SMTP 연결 생성 (Gmail/Outlook 자동 감지)"""
        try:
            if "gmail.com" in self.email_config.EMAIL_USER:
                server = smtplib.SMTP("smtp.gmail.com", 587)
            elif "@outlook.com" in self.email_config.EMAIL_USER or "@hotmail.com" in self.email_config.EMAIL_USER:
                server = smtplib.SMTP("smtp-mail.outlook.com", 587)
            else:
                # 사용자 정의 SMTP 서버
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
                   is_html: bool = True,
                   attachment_data: Optional[bytes] = None,
                   attachment_name: Optional[str] = None,
                   attachment_mime_type: Optional[str] = None):
        """이메일 발송 (첨부파일 지원 추가)"""
        try:
            msg = MIMEMultipart('mixed')  # 첨부파일을 위해 mixed로 변경
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
            
            # 본문 첨부
            msg_body = MIMEMultipart('alternative')
            if is_html:
                html_part = MIMEText(full_body, 'html', 'utf-8')
                msg_body.attach(html_part)
                
                # 텍스트 버전도 추가 (호환성을 위해)
                text_body = self._html_to_text(full_body)
                text_part = MIMEText(text_body, 'plain', 'utf-8')
                msg_body.attach(text_part)
            else:
                text_part = MIMEText(full_body, 'plain', 'utf-8')
                msg_body.attach(text_part)
            
            msg.attach(msg_body)
            
            # 첨부파일 추가
            if attachment_data and attachment_name:
                attachment = MIMEBase('application', 'octet-stream')
                attachment.set_payload(attachment_data)
                encoders.encode_base64(attachment)
                attachment.add_header(
                    'Content-Disposition',
                    f'attachment; filename= "{attachment_name}"'
                )
                msg.attach(attachment)
            
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
        return f"""
        <br><br>
        <div style="border-top: 3px solid #e9ecef; padding-top: 25px; margin-top: 40px; font-size: 14px; color: #6c757d; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            <div style="text-align: center;">
                <div style="font-size: 2rem; margin-bottom: 15px;">🏢</div>
                <h3 style="margin: 0 0 10px 0; font-weight: bold; color: #495057; font-size: 18px;">AI 면접 일정 조율 시스템</h3>
                <p style="margin: 8px 0; color: #6c757d; font-size: 14px;">본 메일은 자동 발송된 메일입니다.</p>
                <p style="margin: 8px 0; color: #6c757d; font-size: 14px;">문의사항이 있으시면 인사팀(<a href="mailto:hr@{self.company_domain}" style="color: #007bff; text-decoration: none; font-weight: bold;">hr@{self.company_domain}</a>)으로 연락해주세요.</p>
                <div style="margin-top: 20px; padding-top: 20px; border-top: 2px solid #dee2e6;">
                    <p style="margin: 0; font-size: 13px; color: #adb5bd;">© 2024 {self.company_domain.upper()} - All rights reserved</p>
                </div>
            </div>
        </div>
        """

    def _html_to_text(self, html_content: str) -> str:
        """HTML을 텍스트로 변환"""
        import re
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', html_content)
        # 연속된 공백 정리
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def send_interviewer_invitation(self, request: InterviewRequest):
        """면접관에게 일정 입력 요청 메일 발송"""
        interviewer_email = get_employee_email(request.interviewer_id)
        interviewer_info = get_employee_info(request.interviewer_id)
        
        # 🔧 수정: 실제 운영 중인 페이지 URL
        link = f"https://interview-scheduler-ajnetworks.streamlit.app/면접관_일정입력"
        
        subject = "📅 [면접 일정 조율] 면접 가능 일정 입력 요청"
        
        # 인사팀 제안 일시 테이블 생성
        preferred_schedule_html = ""
        if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
            preferred_schedule_html = """
            <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); padding: 25px; border-radius: 15px; border-left: 8px solid #ffc107; margin: 30px 0;">
                <h3 style="color: #856404; margin-top: 0; margin-bottom: 25px;">⭐ 인사팀 제안 일시</h3>
                <table style="width: 100%; border-collapse: collapse; border: 3px solid #ffc107; border-radius: 12px; overflow: hidden;">
                    <thead>
                        <tr style="background: linear-gradient(135deg, #ffc107 0%, #ffb300 100%); color: #212529;">
                            <th style="padding: 20px; text-align: center; font-weight: bold;">번호</th>
                            <th style="padding: 20px; text-align: center; font-weight: bold;">날짜</th>
                            <th style="padding: 20px; text-align: center; font-weight: bold;">시간</th>
                            <th style="padding: 20px; text-align: center; font-weight: bold;">비고</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            for i, datetime_slot in enumerate(request.preferred_datetime_slots, 1):
                bg_color = "#fffbf0" if i % 2 == 1 else "#fff8e1"
                
                if "면접관선택" in datetime_slot:
                    date_part = datetime_slot.split(' ')[0]
                    time_display = "09:00~17:00 중 선택"
                    note = "시간 선택 필요"
                    time_color = "#dc3545"
                else:
                    date_part, time_part = datetime_slot.split(' ')
                    time_display = time_part
                    note = "시간 고정"
                    time_color = "#28a745"
                
                preferred_schedule_html += f"""
                        <tr style="background-color: {bg_color};">
                            <td style="padding: 18px; text-align: center; font-weight: bold;">{i}</td>
                            <td style="padding: 18px; text-align: center; font-weight: bold;">{format_date_korean(date_part)}</td>
                            <td style="padding: 18px; text-align: center; font-weight: bold; color: {time_color};">{time_display}</td>
                            <td style="padding: 18px; text-align: center; font-style: italic;">{note}</td>
                        </tr>
                """
            
            preferred_schedule_html += """
                    </tbody>
                </table>
            </div>
            """
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto;">
            <!-- 헤더 -->
            <div style="background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%); color: white; padding: 40px; text-align: center; border-radius: 15px 15px 0 0;">
                <div style="font-size: 3rem; margin-bottom: 15px;">📅</div>
                <h1 style="margin: 0; font-size: 2.2rem; font-weight: 300;">면접 일정 입력 요청</h1>
                <p style="margin: 15px 0 0 0; font-size: 1.1rem; opacity: 0.9;">Interview Schedule Request</p>
            </div>
            
            <!-- 본문 -->
            <div style="padding: 50px; background-color: #f8f9fa; border-radius: 0 0 15px 15px;">
                <div style="background-color: white; padding: 40px; border-radius: 15px;">
                    <h2 style="color: #333; margin: 0 0 15px 0;">안녕하세요, <strong style="color: #0078d4;">{interviewer_info['name']}</strong>님</h2>
                    <p style="color: #666; margin: 8px 0 25px 0;">({interviewer_info['department']})</p>
                    <p style="font-size: 1.1rem; line-height: 1.8; color: #555;">새로운 면접 일정 조율 요청이 도착했습니다. 아래 정보를 확인하시고 가능한 면접 일정을 입력해주세요.</p>
                </div>
                
                <!-- 면접 정보 -->
                <div style="background-color: white; padding: 30px; border-radius: 15px; border-left: 8px solid #0078d4; margin: 30px 0;">
                    <h3 style="color: #0078d4; margin-top: 0;">📋 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 15px; font-weight: bold; color: #333; width: 150px;">💼 공고명</td>
                            <td style="padding: 15px; color: #555; font-size: 1.1rem; font-weight: bold;">{request.position_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 15px; font-weight: bold; color: #333;">👤 면접자</td>
                            <td style="padding: 15px; color: #555;">{request.candidate_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 15px; font-weight: bold; color: #333;">📧 이메일</td>
                            <td style="padding: 15px; color: #555;">{request.candidate_email}</td>
                        </tr>
                    </table>
                </div>
                
                {preferred_schedule_html}
                
                <!-- CTA 버튼 -->
                <div style="text-align: center; margin: 50px 0;">
                    <a href="{link}" 
                       style="background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%); color: white; padding: 20px 50px; text-decoration: none; border-radius: 12px; font-weight: bold; display: inline-block; font-size: 1.1rem;">
                        🗓️ 면접 가능 일정 입력하기
                    </a>
                </div>
                
                <!-- 안내사항 -->
                <div style="background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #28a745;">
                    <h4 style="margin-top: 0; color: #155724;">💡 안내사항</h4>
                    <ul style="color: #155724; line-height: 2;">
                        <li>인사팀에서 제안한 일시 중에서만 선택 가능합니다</li>
                        <li>가능한 면접 일정을 여러 개 선택해주세요</li>
                        <li>면접자가 일정을 선택하면 확정 알림을 받게 됩니다</li>
                    </ul>
                </div>
            </div>
        </div>
        """
        
        return self.send_email(
            to_emails=[interviewer_email],
            cc_emails=Config.HR_EMAILS,
            subject=subject,
            body=body
        )

    def send_candidate_invitation(self, request: InterviewRequest):
        """면접자에게 일정 선택 요청 메일 발송 (독립 앱 링크)"""
        interviewer_info = get_employee_info(request.interviewer_id)
        # 🔧 수정: 독립 앱 URL 사용
        candidate_link = f"https://candidate-app.streamlit.app/"
        
        # 가능한 일정 목록 HTML 테이블 생성
        slots_html = ""
        for i, slot in enumerate(request.available_slots, 1):
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            slots_html += f"""
            <tr style="background-color: {bg_color};">
                <td style="padding: 20px; text-align: center;">
                    <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 12px 24px; border-radius: 25px; font-weight: bold;">
                        옵션 {i}
                    </div>
                </td>
                <td style="padding: 20px; text-align: center; font-weight: bold;">{format_date_korean(slot.date)}</td>
                <td style="padding: 20px; text-align: center; font-weight: bold; color: #007bff;">{slot.time}</td>
                <td style="padding: 20px; text-align: center;">{slot.duration}분</td>
            </tr>
            """
        
        subject = "📅 [면접 일정 선택] 면접 일정을 선택해주세요"
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto;">
            <!-- 헤더 -->
            <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 40px; text-align: center; border-radius: 15px 15px 0 0;">
                <div style="font-size: 3rem; margin-bottom: 15px;">📅</div>
                <h1 style="margin: 0; font-size: 2.2rem; font-weight: 300;">면접 일정 선택</h1>
                <p style="margin: 15px 0 0 0; font-size: 1.1rem; opacity: 0.9;">Interview Schedule Selection</p>
            </div>
            
            <!-- 본문 -->
            <div style="padding: 50px; background-color: #f8f9fa; border-radius: 0 0 15px 15px;">
                <div style="background-color: white; padding: 40px; border-radius: 15px;">
                    <h2 style="color: #333; margin: 0 0 15px 0;">안녕하세요, <strong style="color: #28a745;">{request.candidate_name}</strong>님</h2>
                    <p style="font-size: 1.1rem; line-height: 1.8; color: #555;">면접관께서 제안하신 면접 일정 중에서 원하시는 시간을 선택해주세요.</p>
                </div>
                
                <!-- 면접 정보 -->
                <div style="background-color: white; padding: 30px; border-radius: 15px; border-left: 8px solid #28a745; margin: 30px 0;">
                    <h3 style="color: #28a745; margin-top: 0;">📋 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 15px; font-weight: bold; color: #333; width: 150px;">💼 포지션</td>
                            <td style="padding: 15px; color: #555; font-size: 1.1rem; font-weight: bold;">{request.position_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 15px; font-weight: bold; color: #333;">👨‍💼 면접관</td>
                            <td style="padding: 15px; color: #555;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                        </tr>
                    </table>
                </div>
                
                <!-- 제안된 면접 일정 -->
                <div style="background-color: white; padding: 30px; border-radius: 15px; margin: 30px 0;">
                    <h3 style="color: #28a745; margin-top: 0;">🗓️ 제안된 면접 일정</h3>
                    <table style="width: 100%; border-collapse: collapse; border: 3px solid #28a745; border-radius: 12px; overflow: hidden;">
                        <thead>
                            <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                                <th style="padding: 20px; text-align: center; font-weight: bold;">옵션</th>
                                <th style="padding: 20px; text-align: center; font-weight: bold;">날짜</th>
                                <th style="padding: 20px; text-align: center; font-weight: bold;">시간</th>
                                <th style="padding: 20px; text-align: center; font-weight: bold;">소요시간</th>
                            </tr>
                        </thead>
                        <tbody>
                            {slots_html}
                        </tbody>
                    </table>
                </div>
                
                <!-- CTA 버튼 -->
                <div style="text-align: center; margin: 50px 0;">
                    <a href="{candidate_link}" 
                       style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px 50px; text-decoration: none; border-radius: 12px; font-weight: bold; display: inline-block; font-size: 1.1rem;">
                        ✅ 면접 일정 선택하기
                    </a>
                </div>
                
                <!-- 참고사항 -->
                <div style="background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #17a2b8;">
                    <h4 style="margin-top: 0; color: #0c5460;">📝 참고사항</h4>
                    <ul style="color: #0c5460; line-height: 2;">
                        <li>제안된 일정 중 선택하시거나, 다른 일정이 필요한 경우 요청사항을 입력해주세요</li>
                        <li>일정 선택 후 자동으로 모든 관련자에게 확정 알림이 전송됩니다</li>
                        <li>면접 당일 10분 전까지 도착해주시기 바랍니다</li>
                    </ul>
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
        """🔧 개선된 면접 확정 알림 메일 발송 (캘린더 초대 포함)"""
        interviewer_email = get_employee_email(request.interviewer_id)
        interviewer_info = get_employee_info(request.interviewer_id)
        
        if request.status == Config.Status.CONFIRMED:
            subject = "✅ [면접 일정 확정] 면접 일정이 확정되었습니다"
            status_color = "#28a745"
            status_text = "확정 완료"
            status_icon = "🎉"
            header_gradient = "linear-gradient(135deg, #28a745 0%, #20c997 100%)"
            
        else:
            subject = "⏳ [면접 일정 조율] 추가 조율이 필요합니다"
            status_color = "#ffc107"
            status_text = "추가 조율 필요"
            status_icon = "⏳"
            header_gradient = "linear-gradient(135deg, #ffc107 0%, #ffb300 100%)"
        
        # 확정 일시 테이블
        confirmed_schedule_html = ""
        if request.selected_slot:
            confirmed_schedule_html = f"""
            <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #28a745; margin: 30px 0;">
                <h3 style="color: #155724; margin-top: 0;">{status_icon} 확정된 면접 일시</h3>
                <table style="width: 100%; border-collapse: collapse; border: 3px solid #28a745; border-radius: 12px; overflow: hidden;">
                    <thead>
                        <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                            <th style="padding: 25px; text-align: center; font-weight: bold;">날짜</th>
                            <th style="padding: 25px; text-align: center; font-weight: bold;">시간</th>
                            <th style="padding: 25px; text-align: center; font-weight: bold;">소요시간</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 30px; text-align: center; font-weight: bold; font-size: 1.3rem; color: #155724;">{format_date_korean(request.selected_slot.date)}</td>
                            <td style="padding: 30px; text-align: center; font-weight: bold; font-size: 1.4rem; color: #28a745;">{request.selected_slot.time}</td>
                            <td style="padding: 30px; text-align: center; font-weight: bold; font-size: 1.2rem;">{request.selected_slot.duration}분</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto;">
            <!-- 헤더 -->
            <div style="background: {header_gradient}; color: white; padding: 40px; text-align: center; border-radius: 15px 15px 0 0;">
                <div style="font-size: 3rem; margin-bottom: 15px;">{status_icon}</div>
                <h1 style="margin: 0; font-size: 2.2rem; font-weight: 300;">면접 일정 {status_text}</h1>
            </div>
            
            <!-- 본문 -->
            <div style="padding: 50px; background-color: #f8f9fa; border-radius: 0 0 15px 15px;">
                <!-- 면접 정보 -->
                <div style="background-color: white; padding: 30px; border-radius: 15px; border-left: 8px solid {status_color}; margin: 30px 0;">
                    <h3 style="color: {status_color}; margin-top: 0;">📋 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 15px; font-weight: bold; color: #333; width: 160px;">💼 포지션</td>
                            <td style="padding: 15px; color: #555; font-size: 1.1rem; font-weight: bold;">{request.position_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 15px; font-weight: bold; color: #333;">👨‍💼 면접관</td>
                            <td style="padding: 15px; color: #555;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                        </tr>
                        <tr>
                            <td style="padding: 15px; font-weight: bold; color: #333;">👤 면접자</td>
                            <td style="padding: 15px; color: #555;">{request.candidate_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 15px; font-weight: bold; color: #333;">📊 상태</td>
                            <td style="padding: 15px;"><span style="color: {status_color}; font-weight: bold; background: rgba(255,255,255,0.8); padding: 8px 16px; border-radius: 20px; border: 2px solid {status_color};">{status_text}</span></td>
                        </tr>
                    </table>
                </div>
                
                {confirmed_schedule_html}
        """
        
        if request.candidate_note:
            body += f"""
                <div style="background-color: white; padding: 30px; border-radius: 15px; border-left: 8px solid #17a2b8; margin: 30px 0;">
                    <h4 style="color: #17a2b8; margin-top: 0;">💬 면접자 요청사항</h4>
                    <div style="background: #f8f9fa; padding: 25px; border-radius: 12px; border: 2px solid #dee2e6;">
                        <p style="margin: 0; color: #495057; line-height: 1.8; white-space: pre-line;">{request.candidate_note}</p>
                    </div>
                </div>
            """
        
        if request.status == Config.Status.CONFIRMED:
            body += """
                <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #28a745;">
                    <h4 style="margin-top: 0; color: #155724;">🎉 면접 일정이 확정되었습니다!</h4>
                    <ul style="color: #155724; line-height: 2;">
                        <li>⏰ 면접 당일 10분 전까지 도착해주시기 바랍니다</li>
                        <li>🆔 신분증과 필요 서류를 지참해주세요</li>
                        <li>📞 일정 변경이 필요한 경우 최소 24시간 전에 인사팀에 연락해주세요</li>
                    </ul>
                </div>
            """
        else:
            body += """
                <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #ffc107;">
                    <h4 style="margin-top: 0; color: #856404;">⏳ 추가 일정 조율이 필요합니다</h4>
                    <p style="color: #856404; line-height: 1.8;">인사팀에서 면접자 요청사항을 검토한 후 재조율하여 안내드리겠습니다.</p>
                </div>
            """
        
        body += """
            </div>
        </div>
        """
        
        # 🔧 캘린더 초대장 첨부 (확정된 경우만)
        attachment_data = None
        attachment_name = None
        if request.status == Config.Status.CONFIRMED and request.selected_slot:
            try:
                ics_content = create_calendar_invite(request)
                if ics_content:
                    attachment_data = ics_content.encode('utf-8')
                    attachment_name = f"면접일정_{request.candidate_name}_{request.selected_slot.date}.ics"
            except Exception as e:
                logger.warning(f"캘린더 초대장 생성 실패: {e}")
        
        # 모든 관련자에게 발송
        all_recipients = [interviewer_email, request.candidate_email]
        
        return self.send_email(
            to_emails=all_recipients,
            cc_emails=Config.HR_EMAILS,
            subject=subject,
            body=body,
            attachment_data=attachment_data,
            attachment_name=attachment_name,
            attachment_mime_type="text/calendar"
        )


