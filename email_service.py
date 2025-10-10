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
                   is_html: bool = True):
        """이메일 발송"""
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
        return f"""
        <br><br>
        <div style="border-top: 2px solid #e9ecef; padding-top: 20px; margin-top: 30px; font-size: 13px; color: #6c757d; background-color: #f8f9fa; padding: 20px; border-radius: 8px;">
            <div style="text-align: center;">
                <p style="margin: 0; font-weight: bold; color: #495057; font-size: 14px;">🏢 AI 면접 일정 조율 시스템</p>
                <p style="margin: 5px 0; color: #6c757d;">본 메일은 자동 발송된 메일입니다.</p>
                <p style="margin: 5px 0; color: #6c757d;">문의사항이 있으시면 인사팀(<a href="mailto:hr@{self.company_domain}" style="color: #007bff;">hr@{self.company_domain}</a>)으로 연락해주세요.</p>
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #dee2e6;">
                    <p style="margin: 0; font-size: 12px; color: #adb5bd;">© 2024 {self.company_domain.upper()} - All rights reserved</p>
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
        """면접관에게 일정 입력 요청 메일 발송 (실제 이메일 주소 사용)"""
        # 실제 면접관 이메일 주소 조회
        interviewer_email = get_employee_email(request.interviewer_id)
        interviewer_info = get_employee_info(request.interviewer_id)
        
        link = f"{Config.APP_URL}?role=interviewer&id={request.id}"
        
        subject = "📅 [면접 일정 조율] 면접 가능 일정 입력 요청"
        
        # 인사팀 제안 일시 테이블 생성 (날짜 + 시간 정보)
        preferred_schedule_html = ""
        if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
            preferred_schedule_html = """
            <div style="background-color: #fff3cd; padding: 20px; border-radius: 10px; border-left: 5px solid #ffc107; margin: 25px 0; box-shadow: 0 2px 10px rgba(255,193,7,0.2);">
                <h4 style="color: #856404; margin-top: 0; margin-bottom: 20px; display: flex; align-items: center;">
                    <span style="margin-right: 10px;">⭐</span> 인사팀 제안 희망일시
                </h4>
                <table style="width: 100%; border-collapse: collapse; border: 2px solid #ffc107; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <thead>
                        <tr style="background: linear-gradient(135deg, #ffc107 0%, #ffca28 100%); color: #212529;">
                            <th style="padding: 15px; text-align: center; font-weight: bold; font-size: 14px;">번호</th>
                            <th style="padding: 15px; text-align: center; font-weight: bold; font-size: 14px;">날짜</th>
                            <th style="padding: 15px; text-align: center; font-weight: bold; font-size: 14px;">시간</th>
                            <th style="padding: 15px; text-align: center; font-weight: bold; font-size: 14px;">비고</th>
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
                        <tr style="background-color: {bg_color}; border-bottom: 1px solid #f0c14b;">
                            <td style="padding: 15px; text-align: center; font-weight: bold; font-size: 16px; color: #856404;">{i}</td>
                            <td style="padding: 15px; text-align: center; font-weight: bold; color: #495057;">{format_date_korean(date_part)}</td>
                            <td style="padding: 15px; text-align: center; font-weight: bold; color: {time_color}; font-size: 15px;">{time_display}</td>
                            <td style="padding: 15px; text-align: center; font-size: 12px; color: #6c757d; font-style: italic;">{note}</td>
                        </tr>
                """
            
            preferred_schedule_html += """
                    </tbody>
                </table>
                <div style="margin-top: 15px; padding: 15px; background-color: #fff8e1; border-radius: 6px; border: 1px solid #f0c14b;">
                    <p style="margin: 0; font-size: 14px; color: #856404; text-align: center;">
                        <strong>📌 안내:</strong> 위 일시 중에서만 선택 가능하며, "시간 선택 필요" 항목은 면접관님이 직접 시간을 지정해주세요.
                    </p>
                </div>
            </div>
            """
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 700px; margin: 0 auto; background-color: #ffffff;">
            <!-- 헤더 -->
            <div style="background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%); color: white; padding: 30px; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0; font-size: 28px; font-weight: 300;">📅 면접 일정 입력 요청</h1>
                <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Interview Schedule Request</p>
            </div>
            
            <!-- 본문 -->
            <div style="padding: 40px; background-color: #f8f9fa; border-radius: 0 0 12px 12px;">
                <div style="background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.07);">
                    <p style="font-size: 18px; margin-bottom: 10px; color: #333;">안녕하세요, <strong style="color: #0078d4;">{interviewer_info['name']}</strong>님</p>
                    <p style="font-size: 16px; color: #666; margin-bottom: 25px;">({interviewer_info['department']})</p>
                    <p style="font-size: 16px; line-height: 1.6; color: #555;">새로운 면접 일정 조율 요청이 도착했습니다. 아래 정보를 확인하시고 가능한 면접 일정을 입력해주세요.</p>
                </div>
                
                <!-- 면접 정보 테이블 -->
                <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid #0078d4; margin: 25px 0; box-shadow: 0 2px 10px rgba(0,120,212,0.1);">
                    <h3 style="color: #0078d4; margin-top: 0; margin-bottom: 20px; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">📋</span> 면접 정보
                    </h3>
                    <table style="width: 100%; border-collapse: collapse; border: 2px solid #0078d4; border-radius: 8px; overflow: hidden;">
                        <tbody>
                            <tr style="background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%); color: white;">
                                <td style="padding: 15px; font-weight: bold; width: 130px;">구분</td>
                                <td style="padding: 15px; font-weight: bold;">내용</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">포지션</td>
                                <td style="padding: 15px; color: #555; font-size: 16px;">{request.position_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">면접자</td>
                                <td style="padding: 15px; color: #555; font-size: 16px;">{request.candidate_name}</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">이메일</td>
                                <td style="padding: 15px; color: #555; font-size: 14px;">{request.candidate_email}</td>
                            </tr>
                            <tr>
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">요청 일시</td>
                                <td style="padding: 15px; color: #555;">{request.created_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">요청 ID</td>
                                <td style="padding: 15px; color: #666; font-family: monospace; font-size: 14px;">{request.id[:8]}...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                {preferred_schedule_html}
                
                <!-- CTA 버튼 -->
                <div style="text-align: center; margin: 40px 0;">
                    <a href="{link}" 
                       style="background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%); color: white; padding: 18px 40px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; font-size: 16px; box-shadow: 0 4px 15px rgba(0,120,212,0.3); transition: all 0.3s ease;">
                        🗓️ 면접 가능 일정 입력하기
                    </a>
                </div>
                
                <!-- 안내사항 -->
                <div style="background-color: #e8f5e8; padding: 25px; border-radius: 10px; border-left: 5px solid #28a745; margin: 25px 0;">
                    <h4 style="margin-top: 0; color: #155724; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">💡</span> 안내사항
                    </h4>
                    <ul style="margin: 15px 0; padding-left: 20px; color: #155724; line-height: 1.8;">
                        <li>인사팀에서 제안한 일시 중에서만 선택 가능합니다</li>
                        <li>가능한 면접 일정을 여러 개 선택해주세요 (면접자 선택권 확대)</li>
                        <li>일정 입력 후 자동으로 면접자에게 알림이 전송됩니다</li>
                        <li>면접자가 일정을 선택하면 확정 알림을 받게 됩니다</li>
                    </ul>
                </div>
                
                <!-- 링크 접속 안내 -->
                <div style="background-color: #d1ecf1; padding: 25px; border-radius: 10px; border-left: 5px solid #17a2b8; margin: 25px 0;">
                    <h4 style="margin-top: 0; color: #0c5460; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">🔗</span> 링크 접속이 안 되는 경우
                    </h4>
                    <p style="margin: 10px 0; color: #0c5460;">아래 URL을 브라우저에 직접 복사해서 붙여넣으세요:</p>
                    <div style="background-color: #fff; padding: 15px; border-radius: 6px; font-family: monospace; word-break: break-all; margin: 15px 0; border: 1px solid #bee5eb; font-size: 13px;">
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
        # 🔧 수정: 동일한 앱 내에서 role=candidate 파라미터 사용
        candidate_link = f"{Config.APP_URL}?role=candidate&id={request.id}"
        
        # 가능한 일정 목록 HTML 테이블 생성 (날짜 + 시간 정보)
        slots_html = ""
        for i, slot in enumerate(request.available_slots, 1):
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            slots_html += f"""
            <tr style="background-color: {bg_color}; border-bottom: 1px solid #dee2e6;">
                <td style="padding: 15px; text-align: center; font-weight: bold; color: #28a745; font-size: 16px;">옵션 {i}</td>
                <td style="padding: 15px; text-align: center; font-weight: bold;">{format_date_korean(slot.date)}</td>
                <td style="padding: 15px; text-align: center; font-weight: bold; color: #007bff; font-size: 16px;">{slot.time}</td>
                <td style="padding: 15px; text-align: center; color: #666;">{slot.duration}분</td>
            </tr>
            """
        
        subject = "📅 [면접 일정 선택] 면접 일정을 선택해주세요"
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 700px; margin: 0 auto; background-color: #ffffff;">
            <!-- 헤더 -->
            <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 30px; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0; font-size: 28px; font-weight: 300;">📅 면접 일정 선택</h1>
                <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Interview Schedule Selection</p>
            </div>
            
            <!-- 본문 -->
            <div style="padding: 40px; background-color: #f8f9fa; border-radius: 0 0 12px 12px;">
                <div style="background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.07);">
                    <p style="font-size: 18px; margin-bottom: 10px; color: #333;">안녕하세요, <strong style="color: #28a745;">{request.candidate_name}</strong>님</p>
                    <p style="font-size: 16px; line-height: 1.6; color: #555; margin-bottom: 25px;">면접관께서 제안하신 면접 일정 중에서 원하시는 시간을 선택해주세요. 아래 정보를 확인하시고 편리한 일정을 선택하시면 됩니다.</p>
                </div>
                
                <!-- 면접 정보 테이블 -->
                <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid #28a745; margin: 25px 0; box-shadow: 0 2px 10px rgba(40,167,69,0.1);">
                    <h3 style="color: #28a745; margin-top: 0; margin-bottom: 20px; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">📋</span> 면접 정보
                    </h3>
                    <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden;">
                        <tbody>
                            <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                                <td style="padding: 15px; font-weight: bold; width: 130px;">구분</td>
                                <td style="padding: 15px; font-weight: bold;">내용</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">포지션</td>
                                <td style="padding: 15px; color: #555; font-size: 16px;">{request.position_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">면접관</td>
                                <td style="padding: 15px; color: #555; font-size: 16px;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">요청 ID</td>
                                <td style="padding: 15px; color: #666; font-family: monospace; font-size: 14px;">{request.id[:8]}...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <!-- 제안된 면접 일정 테이블 -->
                <div style="background-color: white; padding: 25px; border-radius: 10px; margin: 25px 0; box-shadow: 0 4px 6px rgba(0,0,0,0.07);">
                    <h3 style="color: #28a745; margin-top: 0; margin-bottom: 20px; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">🗓️</span> 제안된 면접 일정
                    </h3>
                    <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <thead>
                            <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                                <th style="padding: 15px; text-align: center; font-weight: bold; font-size: 14px;">옵션</th>
                                <th style="padding: 15px; text-align: center; font-weight: bold; font-size: 14px;">날짜</th>
                                <th style="padding: 15px; text-align: center; font-weight: bold; font-size: 14px;">시간</th>
                                <th style="padding: 15px; text-align: center; font-weight: bold; font-size: 14px;">소요시간</th>
                            </tr>
                        </thead>
                        <tbody>
                            {slots_html}
                        </tbody>
                    </table>
                </div>
                
                <!-- CTA 버튼 -->
                <div style="text-align: center; margin: 40px 0;">
                    <a href="{candidate_link}" 
                       style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 18px 40px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; font-size: 16px; box-shadow: 0 4px 15px rgba(40,167,69,0.3); transition: all 0.3s ease;">
                        ✅ 면접 일정 선택하기
                    </a>
                </div>
                
                <!-- 참고사항 -->
                <div style="background-color: #d1ecf1; padding: 25px; border-radius: 10px; border-left: 5px solid #17a2b8;">
                    <h4 style="margin-top: 0; color: #0c5460; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">📝</span> 참고사항
                    </h4>
                    <ul style="margin: 15px 0; padding-left: 20px; color: #0c5460; line-height: 1.8;">
                        <li>제안된 일정 중 선택하시거나, 다른 일정이 필요한 경우 요청사항을 입력해주세요</li>
                        <li>일정 선택 후 자동으로 모든 관련자에게 확정 알림이 전송됩니다</li>
                        <li>궁금한 사항이 있으시면 인사팀으로 연락해주세요</li>
                        <li>면접 당일 <strong>10분 전까지 도착</strong>해주시기 바랍니다</li>
                    </ul>
                </div>
                
                <!-- 링크 안내 -->
                <div style="background-color: #fff3cd; padding: 25px; border-radius: 10px; border-left: 5px solid #ffc107; margin: 25px 0;">
                    <h4 style="margin-top: 0; color: #856404; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">🔗</span> 링크가 작동하지 않는 경우
                    </h4>
                    <p style="margin: 10px 0; color: #856404;">아래 URL을 복사해서 브라우저에 직접 입력해주세요:</p>
                    <div style="background-color: #fff; padding: 15px; border-radius: 6px; font-family: monospace; word-break: break-all; margin: 15px 0; border: 1px solid #f0c14b; font-size: 13px;">
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
            header_gradient = "linear-gradient(135deg, #28a745 0%, #20c997 100%)"
            
        else:
            subject = "⏳ [면접 일정 조율] 추가 조율이 필요합니다"
            status_color = "#ffc107"
            status_text = "추가 조율 필요"
            status_icon = "⏳"
            header_gradient = "linear-gradient(135deg, #ffc107 0%, #ffca28 100%)"
        
        # 확정 일시 테이블 (날짜 + 시간 정보)
        confirmed_schedule_html = ""
        if request.selected_slot:
            confirmed_schedule_html = f"""
            <div style="background-color: #d4edda; padding: 25px; border-radius: 10px; border-left: 5px solid #28a745; margin: 25px 0; box-shadow: 0 2px 10px rgba(40,167,69,0.2);">
                <h3 style="color: #155724; margin-top: 0; margin-bottom: 20px; display: flex; align-items: center;">
                    <span style="margin-right: 10px;">{status_icon}</span> 확정된 면접 일시
                </h3>
                <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <thead>
                        <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                            <th style="padding: 15px; text-align: center; font-size: 16px; font-weight: bold;">날짜</th>
                            <th style="padding: 15px; text-align: center; font-size: 16px; font-weight: bold;">시간</th>
                            <th style="padding: 15px; text-align: center; font-size: 16px; font-weight: bold;">소요시간</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 20px; text-align: center; font-weight: bold; font-size: 18px; color: #155724;">{format_date_korean(request.selected_slot.date)}</td>
                            <td style="padding: 20px; text-align: center; font-weight: bold; font-size: 18px; color: #28a745;">{request.selected_slot.time}</td>
                            <td style="padding: 20px; text-align: center; font-weight: bold; font-size: 18px; color: #495057;">{request.selected_slot.duration}분</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
        
        body = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 700px; margin: 0 auto; background-color: #ffffff;">
            <!-- 헤더 -->
            <div style="background: {header_gradient}; color: white; padding: 30px; text-align: center; border-radius: 12px 12px 0 0;">
                <h1 style="margin: 0; font-size: 28px; font-weight: 300;">{status_icon} 면접 일정 {status_text}</h1>
                <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Interview Schedule Confirmation</p>
            </div>
            
            <!-- 본문 -->
            <div style="padding: 40px; background-color: #f8f9fa; border-radius: 0 0 12px 12px;">
                <!-- 면접 정보 테이블 -->
                <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid {status_color}; margin: 25px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h3 style="color: {status_color}; margin-top: 0; margin-bottom: 20px; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">📋</span> 면접 정보
                    </h3>
                    <table style="width: 100%; border-collapse: collapse; border: 2px solid {status_color}; border-radius: 8px; overflow: hidden;">
                        <tbody>
                            <tr style="background: {header_gradient}; color: white;">
                                <td style="padding: 15px; font-weight: bold; width: 140px;">구분</td>
                                <td style="padding: 15px; font-weight: bold;">내용</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">포지션</td>
                                <td style="padding: 15px; color: #555; font-size: 16px;">{request.position_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">면접관</td>
                                <td style="padding: 15px; color: #555; font-size: 16px;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">면접관 이메일</td>
                                <td style="padding: 15px; color: #555; font-size: 14px;">{interviewer_email}</td>
                            </tr>
                            <tr>
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">면접자</td>
                                <td style="padding: 15px; color: #555; font-size: 16px;">{request.candidate_name}</td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">면접자 이메일</td>
                                <td style="padding: 15px; color: #555; font-size: 14px;">{request.candidate_email}</td>
                            </tr>
                            <tr>
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">상태</td>
                                <td style="padding: 15px;"><span style="color: {status_color}; font-weight: bold; font-size: 16px;">{status_text}</span></td>
                            </tr>
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">처리 일시</td>
                                <td style="padding: 15px; color: #555;">{request.updated_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
                            </tr>
                            <tr>
                                <td style="padding: 15px; font-weight: bold; color: #333; border-right: 1px solid #dee2e6;">요청 ID</td>
                                <td style="padding: 15px; color: #666; font-family: monospace; font-size: 14px;">{request.id[:8]}...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                {confirmed_schedule_html}
        """
        
        if request.candidate_note:
            body += f"""
                <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid #17a2b8; margin: 25px 0; box-shadow: 0 2px 10px rgba(23,162,184,0.1);">
                    <h4 style="color: #17a2b8; margin-top: 0; margin-bottom: 15px; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">💬</span> 면접자 요청사항
                    </h4>
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; border: 1px solid #dee2e6;">
                        <p style="margin: 0; color: #495057; line-height: 1.8; font-size: 15px; white-space: pre-line;">{request.candidate_note}</p>
                    </div>
                </div>
            """
        
        if request.status == Config.Status.CONFIRMED:
            body += """
                <div style="background-color: #d4edda; padding: 25px; border-radius: 10px; border-left: 5px solid #28a745;">
                    <h4 style="margin-top: 0; color: #155724; font-size: 18px; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">🎉</span> 면접 일정이 확정되었습니다!
                    </h4>
                    <ul style="margin: 15px 0; padding-left: 20px; color: #155724; line-height: 1.8;">
                        <li><strong>면접 당일 10분 전까지 도착</strong>해주시기 바랍니다</li>
                        <li>면접 준비에 차질이 없도록 미리 준비해주세요</li>
                        <li>일정 변경이 필요한 경우 <strong>최소 24시간 전</strong>에 인사팀에 연락해주세요</li>
                        <li>신분증과 필요 서류를 지참해주세요</li>
                    </ul>
                </div>
            """
        else:
            body += """
                <div style="background-color: #fff3cd; padding: 25px; border-radius: 10px; border-left: 5px solid #ffc107;">
                    <h4 style="margin-top: 0; color: #856404; font-size: 18px; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">⏳</span> 추가 일정 조율이 필요합니다
                    </h4>
                    <p style="margin: 15px 0 0 0; color: #856404; line-height: 1.6;">인사팀에서 면접자 요청사항을 검토한 후 재조율하여 안내드리겠습니다. 잠시만 기다려주세요.</p>
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

