import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate
import ssl
import time
import random
import uuid
import hashlib
import re
import socket
from typing import List, Optional, Tuple
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
        self.sent_emails_log = set()
        


    def _generate_email_hash(self, to_emails, subject: str, request_id: str = None) -> str:
        if not isinstance(to_emails, list):
            to_emails = [to_emails]
        content = f"{sorted(to_emails)}_{subject}_{request_id or ''}"
        return hashlib.md5(content.encode()).hexdigest()

    def validate_and_correct_email(self, email: str) -> Tuple[str, bool]:
        """이메일 주소 검증 및 오타 교정"""
        common_typos = {
            'gamail.com': 'gmail.com',
            'gmial.com': 'gmail.com',
            'gmai.com': 'gmail.com',
            'gmail.co': 'gmail.com',
            'outlok.com': 'outlook.com',
            'hotmial.com': 'hotmail.com'
        }
        
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return email, False
        
        local_part, domain = email.split('@')
        
        if domain.lower() in common_typos:
            corrected_email = f"{local_part}@{common_typos[domain.lower()]}"
            logger.warning(f"이메일 오타 교정: {email} -> {corrected_email}")
            return corrected_email, True
        
        return email, False

    def _check_email_deliverability(self, email: str) -> bool:
        """이메일 전송 가능성 체크"""
        try:
            domain = email.split('@')[1]
            mx_records = socket.getaddrinfo(domain, None)
            return len(mx_records) > 0
        except:
            return False

    def _is_gmail_recipient(self, email: str) -> bool:
        gmail_domains = ['gmail.com', 'gamail.com', 'gmial.com', 'gmai.com', 'gmail.co']
        return any(domain == email.lower().split('@')[-1] for domain in gmail_domains)

    def _has_gmail_recipients(self, to_emails: List[str], cc_emails: Optional[List[str]] = None, bcc_emails: Optional[List[str]] = None) -> bool:
        """수신자 중 Gmail 사용자가 있는지 확인"""
        all_emails = []
        
        if isinstance(to_emails, list):
            all_emails.extend(to_emails)
        else:
            all_emails.append(to_emails)
            
        if cc_emails:
            all_emails.extend(cc_emails)
        if bcc_emails:
            all_emails.extend(bcc_emails)
            
        return any(self._is_gmail_recipient(email) for email in all_emails)

    def _create_smtp_connection(self):
        """SMTP 연결 생성"""
        try:
            logger.info(f"📧 SMTP 연결 시작 - User: {self.email_config.EMAIL_USER}")
            
            if "gmail.com" in self.email_config.EMAIL_USER:
                server = smtplib.SMTP("smtp.gmail.com", 587)
                logger.info("Gmail SMTP 서버 사용")
            elif "@outlook.com" in self.email_config.EMAIL_USER or "@hotmail.com" in self.email_config.EMAIL_USER:
                server = smtplib.SMTP("smtp-mail.outlook.com", 587)
                logger.info("Outlook SMTP 서버 사용")
            else:
                server = smtplib.SMTP(self.email_config.EXCHANGE_SERVER, self.email_config.EXCHANGE_PORT)
                logger.info(f"사용자 정의 SMTP 서버 사용: {self.email_config.EXCHANGE_SERVER}:{self.email_config.EXCHANGE_PORT}")
            
            server.starttls()
            server.login(self.email_config.EMAIL_USER, self.email_config.EMAIL_PASSWORD)
            logger.info("SMTP 연결 및 로그인 성공")
            return server
        except Exception as e:
            logger.error(f"SMTP 연결 실패: {e}")
            return None

    def _generate_message_id(self):
        """Message-ID 생성"""
        sender_domain = self.email_config.EMAIL_USER.split('@')[1]
        unique_id = str(uuid.uuid4()).replace('-', '')
        timestamp = int(time.time())
        return f"<{timestamp}.{unique_id}@{sender_domain}>"

    def _create_mime_structure(self, text_body: str, html_body: str, attachment_data=None, attachment_name=None):
        """MIME 구조 생성"""
        if attachment_data:
            msg = MIMEMultipart('mixed')
            body_part = MIMEMultipart('alternative')
            body_part.attach(MIMEText(text_body, 'plain', 'utf-8'))
            body_part.attach(MIMEText(html_body, 'html', 'utf-8'))
            msg.attach(body_part)
            
            attachment = MIMEBase('application', 'octet-stream')
            attachment.set_payload(attachment_data)
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', f'attachment; filename="{attachment_name}"')
            msg.attach(attachment)
        else:
            msg = MIMEMultipart('alternative')
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        return msg

    def _add_headers(self, msg: MIMEMultipart, recipient_email: str) -> MIMEMultipart:
        """이메일 헤더 추가"""
        msg['Message-ID'] = self._generate_message_id()
        msg['Date'] = formatdate(localtime=True)
        
        if self._is_gmail_recipient(recipient_email):
            msg['X-Mailer'] = "StreamIt-EmailSystem/1.0"
            msg['X-Priority'] = '3'
            msg['From'] = f"AJ네트웍스 HR <{self.email_config.EMAIL_USER}>"
            msg['Reply-To'] = Config.HR_EMAILS[0] if Config.HR_EMAILS else self.email_config.EMAIL_USER
            logger.info("  - Gmail 헤더 적용")
        else:
            msg['From'] = self.email_config.EMAIL_USER
            logger.info("  - 일반 헤더 적용")
                
        return msg

    def _create_gmail_safe_html(self, content_data: dict) -> str:
        """Gmail 안전 HTML 생성 - AJ 로고 포함"""
        # AJ 로고 URL
        logo_url = "https://imgur.com/JxtMWx3.png"
        
        return f"""<!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>{content_data.get('title', '이메일 알림')}</title>
    </head>
    <body style="margin:0;padding:0;font-family: 'Apple SD Gothic Neo', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;background-color:#ffffff;">
        <div style="max-width:600px;margin:0 auto;background-color:#ffffff;">
            <!-- Header with AJ Logo -->
            <div style="background-color:#f9f9f9; color:#1A1A1A; padding:30px; text-align:center; border-bottom:2px solid #e7e7e7;">
                <img src="{logo_url}" 
                    alt="AJ네트웍스 로고" 
                    style="max-width:180px;height:auto;margin-bottom:15px;display:block;margin-left:auto;margin-right:auto;">
            </div>
            
            <!-- Body -->
            <div style="padding:30px;">
                <h2 style="color:#1A1A1A;margin:0 0 20px 0;font-size:18px;">
                    안녕하세요, <span style="color:#1A1A1A;">{content_data.get('recipient_name', '고객')}</span>님
                </h2>
                
                <p style="color:#737272;margin:0 0 25px 0;line-height:1.6;">
                    {content_data.get('main_message', '메시지 내용')}
                </p>
                
                <!-- 면접 정보 테이블 (외곽선 포함) -->
                <div style="border: 2px solid #e7e7e7; border-radius: 8px; overflow: hidden; margin: 20px 0;">
                    <table style="width:100%; border-collapse: collapse; background-color: #ffffff;">
                        <tr>
                            <td style="padding:14px; font-weight:bold; color:#1A1A1A; border:1px solid #e7e7e7; width:30%; text-align:center; font-size:14px;">
                                포지션
                            </td>
                            <td style="padding:14px; color:#737272; border:1px solid #e7e7e7; text-align:center; font-size:14px;">
                                {content_data.get('position', '')}
                            </td>
                        </tr>
                    </table>
                </div>
                
                <!-- 액션 버튼 -->
                <div style="text-align:center;margin:30px 0;">
                    <a href="{content_data.get('action_link', '#')}" 
                    style="display:inline-block;padding:18px 35px;background:linear-gradient(135deg, #EF3340 0%, #e0752e 100%);color:#ffffff;
                            text-decoration:none;border-radius:8px;font-family:'Malgun Gothic', 'Apple SD Gothic Neo', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                            font-weight:bold;font-size:16px;box-shadow:0 4px 15px rgba(239, 51, 64, 0.3);">
                    {content_data.get('button_text', '확인하기')}
                    </a>
                </div>
                
                <!-- 추가 컨텐츠 -->
                <div style="background-color:#f9f9f9;padding:20px;border-radius:10px;border-left:5px solid #EF3340;margin:25px 0; ">
                    {content_data.get('additional_content', '')}
                </div>
                
                <!-- 참고사항 -->
                <div style="background-color:#f9f9f9;padding:20px;border-radius:10px;border-left:5px solid #737272;margin:30px 0;">
                    <p style="margin:0 0 15px 0;font-weight:bold;color:#1A1A1A;font-size:16px;">📝 참고사항</p>
                    <ul style="margin:0;padding-left:20px;color:#737272;line-height:1.8;">
                        <li>제안된 일정 중 선택하시거나, 다른 일정이 필요한 경우 직접 입력해주세요</li>
                        <li>일정 선택 후 자동으로 확정 알림이 전송됩니다</li>
                        <li>궁금한 사항이 있으시면 인사팀으로 연락해주세요</li>
                        <li>면접 당일 10분 전까지 도착해주시기 바랍니다</li>
                    </ul>
                </div>
                
                <!-- 링크 안내 -->
                <div style="background-color:#f7ddd4;padding:20px;border-radius:10px;border-left:5px solid #e0752e;margin:30px 0;">
                    <p style="margin:0 0 10px 0;font-weight:bold;color:#1A1A1A;font-size:16px;">🔗 링크가 작동하지 않는 경우</p>
                    <p style="margin:0 0 15px 0;color:#737272;">아래 URL을 복사해서 브라우저에 직접 입력해주세요:</p>
                    <div style="background-color:white;padding:15px;border-radius:6px;font-family:'Courier New', monospace;word-break:break-all;margin:15px 0;border:1px solid #e7e7e7;color:#1A1A1A;font-size:14px;">
                        {content_data.get('action_link', '#')}
                    </div>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background-color:#f9f9f9;padding:20px;text-align:center;border-top:2px solid #e7e7e7;">
                <p style="margin:0;font-size:14px;color:#737272;">
                    본 메일은 <strong style="color:#EF3340;">{content_data.get('company_name', 'AJ네트웍스')}</strong> 인사팀에서 발송되었습니다.<br>
                    문의: <a href="mailto:{content_data.get('contact_email', 'hr@ajnet.co.kr')}" style="color:#EF3340;text-decoration:none;font-weight:bold;">{content_data.get('contact_email', 'hr@ajnet.co.kr')}</a>
                </p>
            </div>
        </div>
    </body>
    </html>"""

    def _html_to_text(self, html_content: str) -> str:
        """HTML을 텍스트로 변환"""
        text = re.sub(r'<[^>]+>', '', html_content)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def send_email(self, to_emails: List[str], subject: str, body: str, 
                   cc_emails: Optional[List[str]] = None, 
                   bcc_emails: Optional[List[str]] = None,
                   is_html: bool = True,
                   attachment_data: Optional[bytes] = None,
                   attachment_name: Optional[str] = None,
                   attachment_mime_type: Optional[str] = None,
                   request_id: str = None):
        """
        🔧 한도 체크 제거한 이메일 발송 (중복 방지 + 발송 한도 체크)
        
        문제점: 동일한 내용의 이메일이 중복 발송됨 + Gmail 한도 초과
        해결책: 해시 기반 중복 체크만 유지, 인위적 한도 체크 제거
        """
        try:
            # ✅ 중복 발송 체크만 유지 (이건 필요함)
            email_hash = self._generate_email_hash(to_emails, subject, request_id)
            if email_hash in self.sent_emails_log:
                logger.info(f"⚠️ 중복 이메일 발송 차단: {subject} -> {to_emails}")
                return True  # 이미 발송했으므로 성공으로 처리
            
            # 이메일 주소 검증
            validated_emails = []
            for email in (to_emails if isinstance(to_emails, list) else [to_emails]):
                corrected_email, was_corrected = self.validate_and_correct_email(email)
                if self._check_email_deliverability(corrected_email):
                    validated_emails.append(corrected_email)
                    if was_corrected:
                        logger.info(f"이메일 오타 교정: {email} -> {corrected_email}")
                else:
                    logger.error(f"전송 불가능한 이메일: {email}")
            
            if not validated_emails:
                logger.error("전송 가능한 이메일이 없습니다.")
                return False
    
            logger.info(f"📧 이메일 발송 시작 - TO: {validated_emails}")
            
            # Gmail 수신자 감지
            has_gmail = self._has_gmail_recipients(validated_emails, cc_emails, bcc_emails)
            
            optimized_subject = subject
    
            # 컨텐츠 최적화
            if has_gmail and is_html:
                text_body = self._html_to_text(body)
                html_body = body
            else:
                text_body = self._html_to_text(body) if is_html else body
                html_body = body if is_html else f"<pre>{body}</pre>"
            
            # MIME 구조 생성
            if is_html:
                msg = self._create_mime_structure(
                    text_body=text_body,
                    html_body=html_body,
                    attachment_data=attachment_data,
                    attachment_name=attachment_name
                )
            else:
                msg = MIMEMultipart()
                text_part = MIMEText(body, 'plain', 'utf-8')
                msg.attach(text_part)
                
                if attachment_data and attachment_name:
                    attachment = MIMEBase('application', 'octet-stream')
                    attachment.set_payload(attachment_data)
                    encoders.encode_base64(attachment)
                    attachment.add_header('Content-Disposition', f'attachment; filename="{attachment_name}"')
                    msg.attach(attachment)
            
            # 헤더 설정
            primary_email = validated_emails[0]
            msg = self._add_headers(msg, primary_email)
            msg['To'] = ', '.join(validated_emails)
            msg['Subject'] = optimized_subject
            
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
            if bcc_emails:
                msg['Bcc'] = ', '.join(bcc_emails)
            
            # 모든 수신자 목록 생성
            all_recipients = validated_emails.copy()
            if cc_emails:
                all_recipients.extend(cc_emails)
            if bcc_emails:
                all_recipients.extend(bcc_emails)
            
            # SMTP 연결 및 발송
            server = self._create_smtp_connection()
            if server:
                try:
                    text = msg.as_string()
                    server.sendmail(self.email_config.EMAIL_USER, all_recipients, text)
                    server.quit()
                    
                    # ✅ 발송 성공 시 중복 방지용 로그만 추가
                    self.sent_emails_log.add(email_hash)
                    
                    logger.info(f"✅ 이메일 발송 성공: {', '.join(validated_emails)} (총 {len(all_recipients)}명)")
                    return True
                    
                except Exception as smtp_error:
                    logger.error(f"SMTP 발송 실패: {smtp_error}")
                    
                    # ✅ Gmail 한도 초과 메시지만 로깅 (인위적 카운터 없음)
                    if "Daily user sending limit exceeded" in str(smtp_error):
                        logger.error("❌ Gmail 실제 일일 발송 한도 초과 - Gmail 측에서 차단됨")
                    
                    try:
                        server.quit()
                    except:
                        pass
                    return False
            else:
                logger.error("SMTP 서버 연결 실패")
                return False
        
        except Exception as e:
            logger.error(f"이메일 발송 실패: {e}")
            
            # ✅ Gmail 한도 초과 에러 처리 (로깅만)
            if "Daily user sending limit exceeded" in str(e):
                logger.error("❌ Gmail 일일 발송 한도 초과")
            
            return False

    def _create_professional_email_body(self, request, interviewer_info, candidate_link, is_gmail_optimized=False):
        """전문적인 이메일 본문 생성 - 통합 템플릿 사용"""
        slots_by_date = {}
        for slot in request.available_slots or []:
            slots_by_date.setdefault(slot.date, []).append(slot)
        # 면접 일정 테이블 HTML 생성
        slots_html = ""
        slot_number = 1
        
        for date, slots in sorted(slots_by_date.items()):
            for slot in slots:
                bg_color = "#ffffff" if slot_number % 2 == 0 else "#f9f9f9"
                slots_html += f"""
                <tr style="background-color:{bg_color};">
                    <td style="padding: 15px; border: 1px solid #e7e7e7; text-align:center; font-size:14px;">{slot_number}</td>
                    <td style="padding: 15px; border: 1px solid #e7e7e7; text-align:center; font-size:14px;">{format_date_korean(slot.date)}</td>
                    <td style="padding: 15px; border: 1px solid #e7e7e7; text-align:center; font-size:14px;">{slot.time}</td>
                    <td style="padding: 15px; border: 1px solid #e7e7e7; text-align:center; font-size:14px;">30분</td>
                </tr>
                """
                slot_number += 1
                
        # 무조건 통합 템플릿 사용
        return self._create_gmail_safe_html({
            'recipient_name': request.candidate_name,
            'main_message': f'{request.position_name} 포지션 지원에 감사드립니다.<br>아래 버튼을 클릭해 원하시는 일시를 선택해 주세요.',
            'position': request.position_name,
            'interviewer': f"{interviewer_info['name']} ({interviewer_info['department']})",
            'action_link': candidate_link,
            'button_text': '면접 일정 선택하기',
            'additional_content': f"""
            <h4 style="color: #EF3340; margin: 0 0 20px 0; font-size:16px;">🗓️ 선택 가능한 면접 시간</h4>
            
            <table style="width: 100%; border-collapse: collapse; border: 2px solid #EF3340; border-radius: 8px; overflow: hidden;">
                <thead>
                    <tr style="background: linear-gradient(135deg, #EF3340 0%, #e0752e 100%); color: white;">
                        <th style="padding: 15px; border: 1px solid #e7e7e7; font-weight: bold; font-size:14px;">번호</th>
                        <th style="padding: 15px; border: 1px solid #e7e7e7; font-weight: bold; font-size:14px;">날짜</th>
                        <th style="padding: 15px; border: 1px solid #e7e7e7; font-weight: bold; font-size:14px;">시간</th>
                        <th style="padding: 15px; border: 1px solid #e7e7e7; font-weight: bold; font-size:14px;">소요시간</th>
                    </tr>
                </thead>
                <tbody>
                    {slots_html}
                </tbody>
            </table>

            <div style="background-color:#fff3cd;padding:15px;border-radius:8px;margin-top:20px;border-left:5px solid #ffc107;">
                <p style="margin:0;color:#856404;font-weight:bold;">⚠️ 안내 사항</p>
                <p style="margin:5px 0 0 0;color:#856404;">
                    • 각 면접은 <strong>30분</strong>으로 진행됩니다<br>
                    • 다른 면접자가 먼저 선택한 시간은 자동으로 제외됩니다
                </p>
            </div>
            """,
            'contact_email': Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'
        })
    
    def _generate_interview_schedule_table(self, datetime_slots: List[str]) -> str:
        """
        면접 일정 HTML 테이블 생성 (번호/날짜/시간)
        
        Args:
            datetime_slots: ["2025-01-15 15:30~16:30", "2025-01-16 10:30~11:30"]
        
        Returns:
            str: HTML 테이블
        """
        rows_html = ""
        for i, datetime_slot in enumerate(datetime_slots, 1):
            try:
                parts = datetime_slot.split(' ')
                date_part = parts[0]
                time_range = parts[1] if len(parts) > 1 else "시간 미정"
                
                bg_color = "#ffffff" if i % 2 == 0 else "#f9f9f9"
                rows_html += f"""
                <tr style="background-color: {bg_color};">
                    <td style="padding: 12px; border: 1px solid #e7e7e7; text-align: center; width: 10%;">{i}</td>
                    <td style="padding: 12px; border: 1px solid #e7e7e7; text-align: center;">{format_date_korean(date_part)}</td>
                    <td style="padding: 12px; border: 1px solid #e7e7e7; text-align: center; font-weight: bold; color: #EF3340;">{time_range}</td>
                </tr>
                """
            except Exception as e:
                logger.error(f"일정 파싱 오류: {e}")
                continue
        
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; margin-bottom: 20px; border: 2px solid #e7e7e7; border-radius: 8px; overflow: hidden;">
            <thead>
                <tr style="background-color: #efeff1;">
                    <th style="padding: 14px; border: 1px solid #e7e7e7; font-weight: bold; width: 10%;">번호</th>
                    <th style="padding: 14px; border: 1px solid #e7e7e7; font-weight: bold;">날짜</th>
                    <th style="padding: 14px; border: 1px solid #e7e7e7; font-weight: bold;">시간</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        """

    def send_interviewer_invitation(self, requests: List[InterviewRequest]):
        """
        면접관에게 일정 입력 요청 메일 발송 (각 면접관에게 개별 발송)
        
        Args:
            requests: List[InterviewRequest] - 동일 그룹의 면접 요청 리스트
        
        Returns:
            bool: 전체 발송 성공 여부
        """
        try:
            # 단일 요청인 경우 리스트로 변환
            if not isinstance(requests, list):
                requests = [requests]
            
            if not requests:
                logger.warning("발송할 면접 요청이 없습니다.")
                return False
            
            # 첫 번째 요청에서 공통 정보 추출
            first_request = requests[0]
            position_name = first_request.position_name
            
            # 복수 면접관 ID 추출
            interviewer_ids = [id.strip() for id in first_request.interviewer_id.split(',')]
            
            logger.info(f"📧 면접관 초대 메일 준비 - 면접관 수: {len(interviewer_ids)}, 면접자 수: {len(requests)}")
            
            # 면접자 정보 수집 (중복 제거)
            candidates = []
            seen_emails = set()
            
            for request in requests:
                if request.candidate_email not in seen_emails:
                    candidates.append({
                        'name': request.candidate_name,
                        'email': request.candidate_email
                    })
                    seen_emails.add(request.candidate_email)
            
            # 면접 일정 테이블 생성 (번호/날짜/시간)
            schedule_html = self._generate_interview_schedule_table(first_request.preferred_datetime_slots)
            
            # 면접자 목록 테이블 생성 (번호/이름/이메일)
            candidates_html = self._generate_candidates_table(candidates)
            
            # 각 면접관에게 개별 발송
            success_count = 0
            
            for interviewer_id in interviewer_ids:
                try:
                    # 개별 면접관 정보 조회
                    interviewer_info = get_employee_info(interviewer_id)
                    interviewer_email = get_employee_email(interviewer_id)
                    
                    logger.info(f"📧 면접관 {interviewer_info['name']}({interviewer_id})에게 메일 발송 중...")
                    
                    # 제목 생성
                    candidate_count_text = f"{len(candidates)}명" if len(candidates) > 1 else candidates[0]['name']
                    subject = f"[인사팀] 면접 일정 입력 요청드립니다 - {position_name} ({candidate_count_text})"
                    
                    # 본문 생성 (개별 면접관 정보 사용)
                    if len(candidates) == 1:
                        intro_message = """
                        귀하께서 참여 예정이신 <strong style="color: #1A1A1A;">면접 일정 조율</strong>을 위해 협조를 부탁드립니다.<br>
                        아래 면접 일정 중 <strong style="color: #EF3340;">가능한 날짜를 선택</strong>해 주시면 감사하겠습니다.
                        """
                        candidate_section_title = "👤 면접자 정보"
                    else:
                        intro_message = f"""
                        귀하께서 참여 예정이신 <strong style="color: #1A1A1A;">{len(candidates)}명의 면접 일정 조율</strong>을 위해 협조를 부탁드립니다.<br>
                        아래 면접 일정 중 <strong style="color: #EF3340;">가능한 날짜를 선택</strong>해 주시면 감사하겠습니다.
                        """
                        candidate_section_title = f"👥 면접자 목록 ({len(candidates)}명)"
                    
                    link = "https://interview-scheduler-ajnetworks.streamlit.app/면접관_일정입력"
                    
                    body = f"""
                    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #ffffff; font-family: 'Apple SD Gothic Neo', Arial, sans-serif; color: #1A1A1A;">
                    <tr>
                        <td align="center">
                        <table width="640" cellpadding="0" cellspacing="0" style="background-color: #ffffff;">
                            <!-- Header -->
                            <tr>
                                <td align="center" style="background-color: #f5f5f5; color: #1A1A1A; padding: 24px;">
                                    <h2 style="margin: 10px 0 0; font-size: 20px;">면접 일정 입력 요청</h2>
                                </td>
                            </tr>

                            <!-- Body -->
                            <tr>
                                <td style="padding: 32px;">
                                    <p style="font-size: 15px; margin: 0 0 12px;">
                                        안녕하세요, <strong>{interviewer_info['name']} ({interviewer_info['employee_id']})</strong>님.
                                    </p>
                                    
                                    <p style="font-size: 15px; line-height: 1.6; margin: 0 0 24px;">
                                        인사팀입니다.<br>
                                        {intro_message}
                                    </p>

                                    <!-- Position Info Table -->
                                    <table width="100%" cellpadding="10" cellspacing="0" style="border-collapse: collapse; background-color: #ffffff; font-size: 14px; margin-bottom: 24px;">
                                        <tr>
                                            <td style="width: 30%; font-weight: bold; text-align: center; border: 1px solid #e7e7e7;">포지션</td>
                                            <td style="text-align: center; border: 1px solid #e7e7e7;">{position_name}</td>
                                        </tr>
                                    </table>


                                    <!-- Schedule Section -->
                                    <h3 style="color: #1A1A1A; margin: 24px 0 12px 0;">📅 인사팀이 지정한 면접 희망 일정</h3>
                                    <p style="font-size: 14px; color: #737272; margin: 0 0 15px 0;">
                                        아래 일정 중 <strong style="color: #EF3340;">가능한 날짜만 선택</strong>해주세요. 시간은 이미 지정되어 있습니다.
                                    </p>
                                    {schedule_html}

                                    <!-- Info Box -->
                                    <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 5px solid #ffc107; margin: 20px 0;">
                                        <p style="margin: 0; color: #856404; font-weight: bold;">💡 안내사항</p>
                                        <p style="margin: 5px 0 0 0; color: #856404; font-size: 14px;">
                                            • 시간은 자동으로 <strong>30분 단위</strong>로 분할됩니다<br>
                                            • 정해진 일자 참석이 어려우실 시 인사팀으로 문의 부탁드립니다
                                        </p>
                                    </div>

                                    <!-- Button -->
                                    <div style="text-align: center; margin: 36px 0;">
                                        <a href="{link}" 
                                            style="display: inline-block; padding: 18px 36px; background-color: #EF3340; color: #ffffff; text-decoration: none;
                                                font-weight: bold; border-radius: 6px; font-size: 15px;">
                                            👉 가능한 날짜 선택하기
                                        </a>
                                    </div>

                                    <p style="font-size: 14px; color: #737272; line-height: 1.6; margin: 0 0 10px;">
                                        ※ 링크가 열리지 않을 경우, 아래 주소를 복사하여 브라우저 주소창에 붙여 넣어주세요.
                                    </p>
                                    <div style="background-color:#f9f9f9;padding:12px;border-radius:6px;font-family:'Courier New',monospace;
                                                word-break:break-all;margin:10px 0;border:1px solid #e7e7e7;color:#1A1A1A;font-size:13px;">
                                        {link}
                                    </div>

                                    <!-- Contact -->
                                    <div style="background-color: #f5f5f5; font-size: 12px; color: #737272; text-align: center; padding: 24px; border-radius: 6px; margin-top: 40px;">
                                        본 메일은 <strong style="color:#EF3340;">AJ네트웍스 인사팀</strong>에서 발송되었습니다.<br>
                                        문의사항이 있으신 경우 인사팀으로 연락 부탁드립니다.<br>
                                        📧 <a href="mailto:{Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'}" 
                                            style="color: #e0752e; text-decoration: none;">{Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'}</a>
                                    </div>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td align="center" style="background-color: #ffffff; padding: 10px; font-size: 12px; color: #737272;">
                                    © 2025 AJ네트웍스. All rights reserved.
                                </td>
                            </tr>
                        </table>
                        </td>
                    </tr>
                    </table>
                    """
                    
                    # 개별 이메일 발송
                    result = self.send_email(
                        to_emails=[interviewer_email],
                        cc_emails=Config.HR_EMAILS,
                        subject=subject,
                        body=body
                    )
                    
                    if result:
                        success_count += 1
                        logger.info(f"면접관 {interviewer_info['name']}({interviewer_id}) 메일 발송 성공")
                    else:
                        logger.error(f"면접관 {interviewer_info['name']}({interviewer_id}) 메일 발송 실패")
                    
                    # API 부하 방지
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"면접관 {interviewer_id} 메일 발송 중 오류: {e}")
                    continue
            
            # 최종 결과
            total_interviewers = len(interviewer_ids)
            logger.info(f"📧 면접관 초대 메일 발송 완료: {success_count}/{total_interviewers}명 성공")
            
            # 1명이라도 성공하면 True 반환
            return success_count > 0
            
        except Exception as e:
            logger.error(f"면접관 초대 메일 발송 실패: {e}")
            return False

    def _generate_candidates_table(self, candidates: List[dict]) -> str:
        """
        면접자 정보 HTML 테이블 생성
        
        Args:
            candidates: [{'name': '홍길동', 'email': 'hong@example.com'}, ...]
        
        Returns:
            str: HTML 테이블
        """
        rows_html = ""
        for i, candidate in enumerate(candidates, 1):
            bg_color = "#ffffff" if i % 2 == 0 else "#f9f9f9"
            rows_html += f"""
            <tr style="background-color: {bg_color};">
                <td style="padding: 10px; border: 1px solid #e7e7e7; text-align: center; width: 10%;">{i}</td>
                <td style="padding: 10px; border: 1px solid #e7e7e7; width: 30%;">{candidate['name']}</td>
                <td style="padding: 10px; border: 1px solid #e7e7e7;">{candidate['email']}</td>
            </tr>
            """
        
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; margin-bottom: 20px;">
            <thead>
                <tr style="background-color: #efeff1;">
                    <th style="padding: 12px; border: 1px solid #e7e7e7; font-weight: bold; width: 10%;">번호</th>
                    <th style="padding: 12px; border: 1px solid #e7e7e7; font-weight: bold; width: 30%;">이름</th>
                    <th style="padding: 12px; border: 1px solid #e7e7e7; font-weight: bold;">이메일</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        """

    # HR 알림 메일 발송 함수 추가

    def send_hr_notification_on_interviewer_completion(self, group_key: str, position_name: str, candidate_count: int):
        """
        ✅ 모든 면접관이 일정 등록 완료했을 때만 HR에게 알림 메일 발송
        group_key 기준으로 판단 (공고명만으로 판단하지 않음)
        """
        try:
            from database import DatabaseManager
            db = DatabaseManager()
    
            completion_status = db.check_all_interviewers_completed(group_key)  # ✅ 변경
    
            if not completion_status['all_completed']:
                remaining_count = len(completion_status['pending_interviewers'])
                logger.info(f"⏳ {position_name}({group_key}) - 아직 {remaining_count}명의 면접관 대기 중")
                return False
    
            logger.info(f"🎉 {position_name}({group_key}) - 모든 면접관 완료! HR 알림 발송")
    
            subject = f"{position_name} 면접관 일정 등록 완료 - 면접자 메일 발송 필요"
            app_link = "https://interview-scheduler-ajnetworks.streamlit.app/"
            
            body = f"""
            <div style="font-family: 'Apple SD Gothic Neo', Arial, sans-serif; max-width: 640px; margin: 0 auto; background-color: #ffffff;">
                
                <div style="background-color: #EF3340; color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 22px;">면접관 일정 등록 완료</h1>
                </div>
    
                
                <div style="padding: 30px;">
                    <p style="font-size: 16px; line-height: 1.6;">
                        <strong>{position_name}</strong> 공고에 대한 면접관들의 일정이 모두 선택되었습니다.
                    </p>
                    
                    <div style="background-color: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0; color: #1A1A1A;">
                            <strong>면접자 수:</strong> {candidate_count}명
                        </p>
                    </div>
                    
                    <p style="font-size: 15px; color: #737272; line-height: 1.6;">
                        면접 조율 앱에서 확인하시고 면접자들에게 <strong style="color: #EF3340;">늦지 않게 메일을 발송</strong>해 주세요.
                    </p>
    
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a style="display: inline-block; padding: 18px 35px; background-color: #EF3340; color: #ffffff;
                                text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;" href="{app_link}">
                            📅 면접 조율 앱 열기
                        </a>
                    </div>
                    
                    <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 5px solid #ffc107; margin: 20px 0;">
                        <p style="margin: 0; color: #856404; font-weight: bold;">⚠️ 안내사항</p>
                        <p style="margin: 5px 0 0 0; color: #856404; font-size: 14px;">
                            • "면접자 메일 발송" 탭에서 일괄 발송 가능합니다<br>
                        </p>
                    </div>
                </div>
    
                
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; font-size: 12px; color: #737272;">
                    본 메일은 AI 면접 일정 조율 시스템에서 자동 발송되었습니다.
                </div>
            </div>
            """
            
            return self.send_email(
                to_emails=Config.HR_EMAILS,
                subject=subject,
                body=body,
                is_html=True,
                request_id=f"hr_notification_{group_key}"
            )
    
        except Exception as e:
            logger.error(f"HR 알림 메일 발송 실패: {e}")
            return False

    def send_candidate_invitation(self, requests):
        """
        🔧 개선된 면접자 초대 메일 발송 (복수 면접자 지원)
        
        Args:
            requests: InterviewRequest 또는 List[InterviewRequest]
        
        Returns:
            dict: {'success_count': int, 'fail_count': int, 'total': int}
        """
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            
            # 단일 요청인 경우 리스트로 변환
            if not isinstance(requests, list):
                requests = [requests]
            
            success_count = 0
            fail_count = 0
            
            for request in requests:
                try:
                    # ✅ 개선된 타임슬롯 찾기 로직
                    overlapping_slots = []
                    
                    # 1차: 기존 find_overlapping_time_slots 시도
                    try:
                        overlapping_slots = db.find_overlapping_time_slots(request)
                        logger.info(f"🔍 find_overlapping_time_slots 결과: {len(overlapping_slots)}개")
                    except Exception as e:
                        logger.warning(f"find_overlapping_time_slots 실패: {e}")
                    
                    # 2차: available_slots 직접 사용 (백업)
                    if not overlapping_slots and request.available_slots:
                        overlapping_slots = request.available_slots
                        logger.info(f"🔄 available_slots 직접 사용: {len(overlapping_slots)}개")
                    
                    # 3차: 구글시트에서 직접 파싱 (최후의 수단)
                    if not overlapping_slots:
                        try:
                            sheet_slots = self._parse_slots_from_sheet(request.id, db)
                            if sheet_slots:
                                overlapping_slots = sheet_slots
                                logger.info(f"📋 구글시트에서 직접 파싱: {len(overlapping_slots)}개")
                        except Exception as parse_error:
                            logger.warning(f"구글시트 파싱 실패: {parse_error}")
                    
                    # 최종 확인
                    if not overlapping_slots:
                        logger.warning(f"❌ 모든 방법으로도 타임슬롯을 찾을 수 없음: {request.candidate_name}")
                        fail_count += 1
                        continue
                    
                    # 면접관 정보 처리
                    interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
                    interviewer_names = []
                    
                    for interviewer_id in interviewer_ids:
                        info = get_employee_info(interviewer_id)
                        interviewer_names.append(info.get('name', interviewer_id))
                    
                    interviewer_display = ", ".join(interviewer_names)
                    candidate_link = f"https://candidate-app.streamlit.app/"
                    
                    logger.info(f"📧 면접자 초대 메일 준비 - {request.candidate_name} ({len(overlapping_slots)}개 타임슬롯)")
                    
                    # 면접 일정 테이블 HTML 생성
                    slots_by_date = {}
                    for slot in overlapping_slots:
                        if slot.date not in slots_by_date:
                            slots_by_date[slot.date] = []
                        slots_by_date[slot.date].append(slot)
                    
                    slots_html = ""
                    slot_number = 1
                    for date, slots in sorted(slots_by_date.items()):
                        for slot in slots:
                            bg_color = "#ffffff" if slot_number % 2 == 0 else "white"
                            slots_html += f"""
                            
                                {slot_number}
                                {format_date_korean(slot.date)}
                                {slot.time}
                                30분
                            
                            """
                            slot_number += 1
                    
                    subject = f"[AJ네트웍스] 면접 일정을 선택해주세요 - {request.position_name}"
                    body = self._create_gmail_safe_html({
                        'company_name': 'AJ네트웍스',
                        'recipient_name': request.candidate_name,
                        'main_message': f'{request.position_name} 포지션 지원에 감사드립니다.<br>면접관들이 가능한 시간 중에서 원하시는 <strong style="color:#EF3340;">시간</strong>을 선택해주세요.',
                        'position': request.position_name,
                        'interviewer': interviewer_display,
                        'action_link': candidate_link,
                        'button_text': '면접 일정 선택하기',
                        'additional_content': f"""
                        <h4 style="color: #EF3340; margin: 0 0 20px 0; font-size:16px;">🗓️ 선택 가능한 면접 시간</h4>
                        
                                {slots_html}
                            <table style="width: 100%; border-collapse: collapse; border: 2px solid #EF3340; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background: linear-gradient(135deg, #EF3340 0%, #e0752e 100%); color: white;">
                                    <th style="padding: 15px; border: 1px solid #e7e7e7; font-weight: bold; font-size:14px;">번호</th>
                                    <th style="padding: 15px; border: 1px solid #e7e7e7; font-weight: bold; font-size:14px;">날짜</th>
                                    <th style="padding: 15px; border: 1px solid #e7e7e7; font-weight: bold; font-size:14px;">시간</th>
                                    <th style="padding: 15px; border: 1px solid #e7e7e7; font-weight: bold; font-size:14px;">소요시간</th>
                                </tr>
                            </thead>
                            <tbody></tbody>
                        </table>
                        <div style="background-color:#fff3cd;padding:15px;border-radius:8px;margin-top:20px;border-left:5px solid #ffc107;">
                            <p style="margin:0;color:#856404;font-weight:bold;">⚠️ 안내 사항</p>
                            <p style="margin:5px 0 0 0;color:#856404;">• 각 면접은 <strong>30분</strong>으로 진행됩니다<br>• 다른 면접자가 먼저 선택한 시간은 자동으로 제외됩니다</p>
                        </div>
                        """,
                        'contact_email': Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'
                    })
                    
                    # 개별 면접자에게 이메일 발송
                    result = self.send_email(
                        to_emails=[request.candidate_email],
                        subject=subject,
                        body=body,
                        is_html=True,
                        request_id=f"candidate_{request.id}"
                    )
                    
                    if result:
                        success_count += 1
                        logger.info(f"✅ 면접자 {request.candidate_name} 메일 발송 성공")
                    else:
                        fail_count += 1
                        logger.error(f"❌ 면접자 {request.candidate_name} 메일 발송 실패")
                    
                    # API 부하 방지
                    time.sleep(0.5)
                    
                except Exception as e:
                    fail_count += 1
                    logger.error(f"❌ 면접자 {request.candidate_name} 메일 발송 중 오류: {e}")
                    continue
            
            total = len(requests)
            logger.info(f"📧 면접자 초대 메일 발송 완료: {success_count}/{total}명 성공, {fail_count}명 실패")
            
            return {
                'success_count': success_count,
                'fail_count': fail_count,
                'total': total
            }
            
        except Exception as e:
            logger.error(f"❌ 면접자 초대 메일 발송 실패: {e}")
            return {
                'success_count': 0,
                'fail_count': len(requests) if isinstance(requests, list) else 1,
                'total': len(requests) if isinstance(requests, list) else 1
            }
    
    def _parse_slots_from_sheet(self, request_id: str, db) -> list:
        """구글시트에서 직접 면접관확정일시 파싱"""
        try:
            if not db.sheet:
                return []
            
            records = db.sheet.get_all_records()
            
            for record in records:
                if record.get('요청ID', '').strip() == request_id:
                    proposed_str = record.get('면접관확정일시', '')
                    if proposed_str:
                        from models import InterviewSlot
                        import re
                        
                        slots = []
                        slot_parts = [s.strip() for s in proposed_str.split('|')]
                        
                        for part in slot_parts:
                            match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+(\d+)분$', part)
                            if match:
                                slot = InterviewSlot(
                                    date=match.group(1),
                                    time=match.group(2),
                                    duration=int(match.group(3))
                                )
                                slots.append(slot)
                        
                        return slots
            
            return []
            
        except Exception as e:
            logger.error(f"구글시트 슬롯 파싱 실패: {e}")
            return []


        
    def send_automatic_confirmation_on_sheet_update(self, request: InterviewRequest):
        """구글 시트 L열 업데이트 시 자동 확정 이메일 발송"""
        try:
            interviewer_email = get_employee_email(request.interviewer_id)

            subject = f"[{self.company_domain.upper()}] {request.position_name} 면접 확정 안내"

            confirmed_datetime = f"{format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)"

            body = f"""
            <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', Arial, sans-serif; max-width: 640px; margin: 0 auto; background-color: #F9F9F9; color: #1A1A1A;">
                <!-- Header -->
                <div style="background-color: #FF0033; color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 24px;">면접 확정 안내</h1>
                </div>

                <!-- Body -->
                <div style="padding: 30px; background-color: white;">
                    <p style="font-size: 16px;">안녕하세요, <strong>{request.candidate_name}</strong>님</p>
                    <p style="font-size: 15px; line-height: 1.6;">
                        지원하신 <strong>{request.position_name}</strong> 포지션의 면접 일정이 아래와 같이 <strong style="color: #FF0033;">확정</strong>되었습니다.
                    </p>

                    <div style="margin-top: 25px;">
                        <h3 style="color: #FF0033;">📅 확정된 면접 일정</h3>
                        <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px;">
                            <tr style="background-color: #F5F5F5;">
                                <td style="padding: 10px; border: 1px solid #D9D9D9; font-weight: bold; width: 30%;">포지션</td>
                                <td style="padding: 10px; border: 1px solid #D9D9D9;">{request.position_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 10px; border: 1px solid #D9D9D9; font-weight: bold;">면접일시</td>
                                <td style="padding: 10px; border: 1px solid #D9D9D9;">{confirmed_datetime}</td>
                            </tr>
                        </table>
                    </div>

                    <div style="text-align: center; margin: 40px 0 20px;">
                        <span style="display: inline-block; background: #FF0033; color: white; padding: 12px 24px; border-radius: 5px; font-weight: bold;">
                            면접 일정이 확정되었습니다
                        </span>
                    </div>

                    <p style="font-size: 13px; color: #4D4D4D; text-align: center; margin-top: 30px;">
                        본 메일은 AJ네트웍스 인사팀에서 발송되었습니다. 문의: 
                        <a href="mailto:{Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'}" style="color: #FF6600;">
                            {Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'}
                        </a>
                    </p>
                </div>

                <!-- Footer -->
                <div style="background-color: #E6E6E6; padding: 10px; text-align: center; font-size: 12px; color: #4D4D4D; border-radius: 0 0 8px 8px;">
                    © 2025 AJ네트웍스. All rights reserved.
                </div>
            </div>
            """

            # 수신자: 면접자, HR 팀
            recipients = [request.candidate_email] + Config.HR_EMAILS

            return self.send_email(
                to_emails=recipients,
                subject=subject,
                body=body,
                is_html=True
            )
        except Exception as e:
            logger.error(f"자동 확정 이메일 발송 실패: {e}")
            return False


    def send_confirmation_notification(self, request: InterviewRequest, sender_type="interviewer"):
        """면접 확정 알림 메일 발송"""
        try:
            interviewer_email = get_employee_email(request.interviewer_id)
            interviewer_info = get_employee_info(request.interviewer_id)
            
            has_gmail = self._has_gmail_recipients([interviewer_email, request.candidate_email])
            
            if request.status == Config.Status.CONFIRMED:
                subject = "면접 일정 확정" if has_gmail else "면접 일정이 확정되었습니다"
                status_color = "#28a745"
                status_text = "확정 완료"
            else:
                subject = "면접 일정 조율 필요" if has_gmail else "추가 조율이 필요합니다"
                status_color = "#ffc107"
                status_text = "추가 조율 필요"
            
            if has_gmail:
                html_body = self._create_gmail_safe_html({
                    'company_name': 'AJ네트웍스',
                    'title': f'면접 일정 {status_text}',
                    'recipient_name': '고객',
                    'main_message': f'{request.position_name} 포지션 면접 일정이 {status_text} 상태입니다.',
                    'position': request.position_name,
                    'interviewer': f"{interviewer_info['name']} ({interviewer_info['department']})",
                    'action_link': '#',
                    'button_text': '확인완료',
                    'additional_content': f"""
                    <p><strong>면접자:</strong> {request.candidate_name}</p>
                    <p><strong>상태:</strong> <span style="color: {status_color};">{status_text}</span></p>
                    {f'<p><strong>확정일시:</strong> {format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)</p>' if request.selected_slot else ''}
                    """,
                    'contact_email': Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'
                })
            else:
                html_body = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <div style="background-color: {status_color}; color: white; padding: 30px; text-align: center;">
                        <h1 style="margin: 0;">면접 일정 {status_text}</h1>
                    </div>
                    
                    <div style="padding: 30px;">
                        <h3>면접 정보</h3>
                        <p><strong>포지션:</strong> {request.position_name}</p>
                        <p><strong>면접관:</strong> {interviewer_info['name']} ({interviewer_info['department']})</p>
                        <p><strong>면접자:</strong> {request.candidate_name}</p>
                        <p><strong>상태:</strong> <span style="color: {status_color};">{status_text}</span></p>
                        {f'<p><strong>확정일시:</strong> {format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)</p>' if request.selected_slot else ''}
                    </div>
                </div>
                """
            
            # 발송자에 따른 수신자 구분
            if sender_type == "interviewer":
                primary_recipients = [request.candidate_email]
                cc_recipients = Config.HR_EMAILS
            elif sender_type == "candidate":
                primary_recipients = [interviewer_email]
                cc_recipients = Config.HR_EMAILS
            else:
                primary_recipients = [interviewer_email, request.candidate_email]
                cc_recipients = Config.HR_EMAILS
            
            # 캘린더 초대장 첨부
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
            
            result = self.send_email(
                to_emails=primary_recipients,
                cc_emails=cc_recipients,
                subject=subject,
                body=html_body,
                attachment_data=attachment_data,
                attachment_name=attachment_name,
                is_html=True
            )
            
            logger.info(f"📧 확정 알림 메일 발송 결과: {result}")
            return result
            
        except Exception as e:
            logger.error(f"확정 알림 메일 발송 실패: {e}")
            return False

    def send_interviewer_notification_on_candidate_selection(self, request: InterviewRequest):
        """면접자가 일정을 선택했을 때 면접관에게만 발송"""
        try:
            interviewer_email = get_employee_email(request.interviewer_id)
            interviewer_info = get_employee_info(request.interviewer_id)

            subject = f"[{self.company_domain.upper()}] 면접 일정 확정 - {request.position_name}"

            selected_datetime = f"{format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)"

            body = f"""
            <div style="font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', Arial, sans-serif; max-width: 640px; margin: 0 auto; background-color: #F9F9F9; color: #1A1A1A;">
                <!-- Header -->
                <div style="background-color: #FF0033; color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 22px;">면접 일정이 확정되었습니다</h1>
                </div>

                <!-- Body -->
                <div style="padding: 30px; background-color: white;">
                    <p style="font-size: 16px;">안녕하세요, <strong>{interviewer_info['name']}</strong>님</p>
                    <p style="font-size: 15px; line-height: 1.6;">
                        면접자가 제안하신 일정 중 하나를 선택했습니다.<br>
                        아래 확정된 면접 일정을 확인해 주세요.
                    </p>

                    <h3 style="margin-top: 30px; color: #FF0033;">📝 확정된 면접 정보</h3>
                    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                        <tr style="background-color: #F5F5F5;">
                            <td style="padding: 10px; font-weight: bold; width: 30%;">포지션</td>
                            <td style="padding: 10px;">{request.position_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 10px; font-weight: bold;">면접자</td>
                            <td style="padding: 10px;">{request.candidate_name}</td>
                        </tr>
                        <tr style="background-color: #F5F5F5;">
                            <td style="padding: 10px; font-weight: bold;">확정일시</td>
                            <td style="padding: 10px;">{selected_datetime}</td>
                        </tr>
                    </table>

                    <p style="font-size: 13px; color: #4D4D4D; text-align: center; margin-top: 30px;">
                        본 메일은 AJ네트웍스 인사팀에서 발송되었습니다. 문의: 
                        <a href="mailto:{Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'}" style="color: #FF6600;">
                            {Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'}
                        </a>
                    </p>
                </div>

                <!-- Footer -->
                <div style="background-color: #E6E6E6; padding: 10px; text-align: center; border-radius: 0 0 8px 8px; font-size: 12px; color: #4D4D4D;">
                    © 2025 AJ네트웍스. All rights reserved.
                </div>
            </div>
            """

            result = self.send_email(
                to_emails=[interviewer_email],
                cc_emails=Config.HR_EMAILS,
                subject=subject,
                body=body,
                is_html=True
            )

            return result

        except Exception as e:
            logger.error(f"면접자 선택 완료 알림 발송 실패: {e}")
            return False

    def send_automatic_confirmation_email(self, request: InterviewRequest):
        """자동 확정 알림 발송"""
        try:
            logger.info(f"📧 자동 확정 알림 발송 시작")
            
            candidate_success = self.send_confirmation_notification(request, sender_type="system")
            interviewer_success = self.send_interviewer_notification_on_candidate_selection(request)
            
            return candidate_success and interviewer_success
                
        except Exception as e:
            logger.error(f"자동 확정 알림 발송 실패: {e}")
            return False

    def test_html_email(self):
        """HTML 이메일 테스트"""
        try:
            test_body = self._create_gmail_safe_html({
                'company_name': 'AJ네트웍스',
                'title': 'HTML 이메일 테스트',
                'recipient_name': '테스터',
                'main_message': '이 메일이 HTML로 제대로 표시되나요?',
                'position': '테스트 포지션',
                'interviewer': '테스트 면접관',
                'action_link': '#',
                'button_text': '테스트 성공',
                'additional_content': '<p style="color: #28a745;">HTML 이메일 테스트 성공!</p>',
                'contact_email': 'test@ajnet.co.kr'
            })
            
            return self.send_email(
                to_emails=[self.email_config.EMAIL_USER],
                subject="HTML 이메일 테스트",
                body=test_body,
                is_html=True
            )
            
        except Exception as e:
            logger.error(f"HTML 테스트 메일 발송 실패: {e}")
            return False




















