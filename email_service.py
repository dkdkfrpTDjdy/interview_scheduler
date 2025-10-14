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
        self.last_send_time = {}  # 발송 간격 제어용

    def validate_and_correct_email(self, email: str) -> tuple[str, bool]:
        """이메일 주소 검증 및 오타 교정"""
        # 일반적인 오타 패턴
        common_typos = {
            'gamail.com': 'gmail.com',
            'gmial.com': 'gmail.com',
            'gmai.com': 'gmail.com',
            'gmail.co': 'gmail.com',
            'outlok.com': 'outlook.com',
            'hotmial.com': 'hotmail.com'
        }
        
        # 기본 이메일 형식 검증
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\$', email):
            return email, False
        
        local_part, domain = email.split('@')
        
        # 오타 교정
        if domain.lower() in common_typos:
            corrected_email = f"{local_part}@{common_typos[domain.lower()]}"
            logger.warning(f"이메일 오타 교정: {email} -> {corrected_email}")
            return corrected_email, True
        
        return email, False

    def _check_email_deliverability(self, email: str) -> bool:
        """이메일 전송 가능성 체크"""
        try:
            domain = email.split('@')[1]
            # MX 레코드 확인
            mx_records = socket.getaddrinfo(domain, None)
            return len(mx_records) > 0
        except:
            return False

    def _is_gmail_recipient(self, email: str) -> bool:
        """Gmail 수신자인지 확인 (오타 도메인 포함)"""
        gmail_domains = ['gmail.com', 'gamail.com', 'gmial.com', 'gmai.com', 'gmail.co']
        return any(domain in email.lower() for domain in gmail_domains)

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
        """SMTP 연결 생성 (Gmail/Outlook 자동 감지)"""
        try:
            logger.info(f"📧 SMTP 연결 시작 - User: {self.email_config.EMAIL_USER}")
            
            if "gmail.com" in self.email_config.EMAIL_USER:
                server = smtplib.SMTP("smtp.gmail.com", 587)
                logger.info("Gmail SMTP 서버 사용")
            elif "@outlook.com" in self.email_config.EMAIL_USER or "@hotmail.com" in self.email_config.EMAIL_USER:
                server = smtplib.SMTP("smtp-mail.outlook.com", 587)
                logger.info("Outlook SMTP 서버 사용")
            else:
                # 사용자 정의 SMTP 서버
                server = smtplib.SMTP(self.email_config.EXCHANGE_SERVER, self.email_config.EXCHANGE_PORT)
                logger.info(f"사용자 정의 SMTP 서버 사용: {self.email_config.EXCHANGE_SERVER}:{self.email_config.EXCHANGE_PORT}")
            
            server.starttls()
            server.login(self.email_config.EMAIL_USER, self.email_config.EMAIL_PASSWORD)
            logger.info("✅ SMTP 연결 및 로그인 성공")
            return server
        except Exception as e:
            logger.error(f"❌ SMTP 연결 실패: {e}")
            logger.error(f"  - Server: {self.email_config.EXCHANGE_SERVER}:{self.email_config.EXCHANGE_PORT}")
            logger.error(f"  - User: {self.email_config.EMAIL_USER}")
            return None

    def _generate_secure_message_id(self):
        """보안 강화된 Message-ID 생성"""
        # 실제 발송 도메인 사용
        sender_domain = self.email_config.EMAIL_USER.split('@')[1]
        unique_id = str(uuid.uuid4()).replace('-', '')
        timestamp = int(time.time())
        
        return f"<{timestamp}.{unique_id}@{sender_domain}>"

    def _generate_message_id(self):
        """고유한 Message-ID 생성 (호환성 유지)"""
        return self._generate_secure_message_id()

    def _check_send_rate_limit(self, recipient_email: str, min_interval: int = 60):
        """발송 간격 제어 (초 단위)"""
        current_time = time.time()
        
        if recipient_email in self.last_send_time:
            time_diff = current_time - self.last_send_time[recipient_email]
            if time_diff < min_interval:
                logger.warning(f"⚠️ 발송 간격 제한: {recipient_email} ({time_diff:.1f}초 전 발송)")
                return False
        
        self.last_send_time[recipient_email] = current_time
        return True

    def _create_optimized_mime_structure(self, text_body: str, html_body: str, attachment_data=None, attachment_name=None):
        """Gmail 최적화된 MIME 구조 생성"""
        
        if attachment_data:
            # 첨부파일이 있는 경우: mixed > alternative > (text + html)
            msg = MIMEMultipart('mixed')
            
            # 본문 파트 (alternative)
            body_part = MIMEMultipart('alternative')
            body_part.attach(MIMEText(text_body, 'plain', 'utf-8'))
            body_part.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            msg.attach(body_part)
            
            # 첨부파일 추가
            attachment = MIMEBase('application', 'octet-stream')
            attachment.set_payload(attachment_data)
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', f'attachment; filename="{attachment_name}"')
            msg.attach(attachment)
        else:
            # 첨부파일 없는 경우: alternative만 사용
            msg = MIMEMultipart('alternative')
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        return msg

    def _add_anti_spam_headers(self, msg: MIMEMultipart, recipient_email: str) -> MIMEMultipart:
        """강화된 스팸 방지 헤더"""
        
        # 기본 헤더
        msg['Message-ID'] = self._generate_secure_message_id()
        msg['Date'] = formatdate(localtime=True)
        
        # Gmail 특화 헤더
        if self._is_gmail_recipient(recipient_email):
            msg['X-Mailer'] = f"StreamIt-EmailSystem/1.0"
            msg['X-Priority'] = '3'
            msg['Importance'] = 'Normal'
            msg['X-Auto-Response-Suppress'] = 'OOF, DR, RN, NRN'
            msg['List-Unsubscribe'] = f"<mailto:{Config.HR_EMAILS[0] if Config.HR_EMAILS else self.email_config.EMAIL_USER}?subject=Unsubscribe>"
            msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
            
            # 발송자 신뢰성 향상
            msg['From'] = f"{getattr(self.email_config, 'FROM_NAME', 'StreamIt')} HR <{self.email_config.EMAIL_USER}>"
            msg['Reply-To'] = Config.HR_EMAILS[0] if Config.HR_EMAILS else self.email_config.EMAIL_USER
            msg['Return-Path'] = self.email_config.EMAIL_USER
            
            # 추가 신뢰성 헤더
            msg['X-Sender'] = self.email_config.EMAIL_USER
            msg['X-Original-Sender'] = self.email_config.EMAIL_USER
            
            logger.info("  - Gmail 스팸 방지 헤더 적용")
        else:
            msg['From'] = self.email_config.EMAIL_USER
            logger.info("  - 일반 헤더 적용")
                
        return msg

    def _strip_emojis(self, text: str) -> str:
        """Gmail용 이모지 제거"""
        emoji_pattern = re.compile("["
                                 u"\U0001F600-\U0001F64F"  # 감정
                                 u"\U0001F300-\U0001F5FF"  # 심볼
                                 u"\U0001F680-\U0001F6FF"  # 교통
                                 u"\U0001F1E0-\U0001F1FF"  # 국기
                                 "]+", flags=re.UNICODE)
        return emoji_pattern.sub('', text)

    def _optimize_subject_for_gmail(self, subject: str) -> str:
        """Gmail 최적화 제목"""
        # 이모지 제거
        clean_subject = self._strip_emojis(subject)
        
        # 스팸 단어 제거
        spam_words = ['무료', '급한', '지금', '클릭', '!!!']
        for word in spam_words:
            clean_subject = clean_subject.replace(word, '')
        
        # 회사명 추가
        company_name = getattr(Config, 'COMPANY_NAME', self.company_domain.upper())
        if company_name not in clean_subject:
            clean_subject = f"[{company_name}] {clean_subject}"
        
        return clean_subject.strip()

    def _create_gmail_safe_html(self, content_data: dict) -> str:
        """Gmail 안전 HTML 생성 (CSS 인라인, 단순 구조)"""
        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;font-family:Arial,sans-serif;background-color:#f8f9fa;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background-color:#ffffff;">
        <!-- 헤더 -->
        <tr>
            <td style="padding:30px;text-align:center;background-color:#007bff;color:#ffffff;">
                <h1 style="margin:0;font-size:24px;font-weight:normal;">{content_data.get('company_name', 'StreamIt')}</h1>
                <p style="margin:10px 0 0 0;font-size:14px;">{content_data.get('title', '이메일 알림')}</p>
            </td>
        </tr>
        
        <!-- 본문 -->
        <tr>
            <td style="padding:40px 30px;">
                <h2 style="color:#333333;margin:0 0 20px 0;font-size:20px;">
                    안녕하세요, {content_data.get('recipient_name', '고객')}님
                </h2>
                
                <p style="color:#555555;line-height:1.6;margin:0 0 25px 0;">
                    {content_data.get('main_message', '메시지 내용')}
                </p>
                
                <!-- 정보 테이블 -->
                <table width="100%" cellpadding="10" cellspacing="0" style="border:1px solid #dee2e6;margin:20px 0;">
                    <tr style="background-color:#f8f9fa;">
                        <td style="font-weight:bold;color:#333333;width:30%;">포지션</td>
                        <td style="color:#555555;">{content_data.get('position', '')}</td>
                    </tr>
                    <tr>
                        <td style="font-weight:bold;color:#333333;">면접관</td>
                        <td style="color:#555555;">{content_data.get('interviewer', '')}</td>
                    </tr>
                </table>
                
                <!-- CTA 버튼 -->
                <table width="100%" cellpadding="0" cellspacing="0" style="margin:30px 0;">
                    <tr>
                        <td style="text-align:center;">
                            <a href="{content_data.get('action_link', '#')}" 
                               style="display:inline-block;padding:15px 30px;background-color:#007bff;color:#ffffff;text-decoration:none;border-radius:5px;font-weight:bold;">
                                {content_data.get('button_text', '확인하기')}
                            </a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        
        <!-- 푸터 -->
        <tr>
            <td style="padding:20px 30px;background-color:#f8f9fa;text-align:center;border-top:1px solid #dee2e6;">
                <p style="margin:0;font-size:12px;color:#666666;">
                    본 메일은 {content_data.get('company_name', 'StreamIt')} 인사팀에서 발송되었습니다.<br>
                    <a href="mailto:{content_data.get('unsubscribe_email', '')}?subject=수신거부" style="color:#666666;">수신거부</a>
                </p>
            </td>
        </tr>
    </table>
</body>
</html>"""

    def send_email(self, to_emails: List[str], subject: str, body: str, 
                   cc_emails: Optional[List[str]] = None, 
                   bcc_emails: Optional[List[str]] = None,
                   is_html: bool = True,
                   attachment_data: Optional[bytes] = None,
                   attachment_name: Optional[str] = None,
                   attachment_mime_type: Optional[str] = None):
        """이메일 발송 (Gmail 최적화 적용)"""
        try:
            # 1. 이메일 주소 검증 및 교정
            validated_emails = []
            for email in (to_emails if isinstance(to_emails, list) else [to_emails]):
                corrected_email, was_corrected = self.validate_and_correct_email(email)
                if self._check_email_deliverability(corrected_email):
                    validated_emails.append(corrected_email)
                    if was_corrected:
                        logger.info(f"이메일 오타 교정하여 발송: {email} -> {corrected_email}")
                else:
                    logger.error(f"전송 불가능한 이메일: {email}")
            
            if not validated_emails:
                logger.error("전송 가능한 이메일이 없습니다.")
                return False

            # 발송 간격 체크
            primary_email = validated_emails[0]
            if not self._check_send_rate_limit(primary_email):
                return False

            logger.info(f"📧 이메일 발송 시작")
            logger.info(f"  - TO: {validated_emails}")
            logger.info(f"  - CC: {cc_emails}")
            logger.info(f"  - Subject: {subject}")
            
            # 2. Gmail 수신자 감지
            has_gmail = self._has_gmail_recipients(validated_emails, cc_emails, bcc_emails)
            logger.info(f"  - Gmail 수신자 포함: {has_gmail}")
            
            # 3. 컨텐츠 최적화
            if has_gmail and is_html:
                # Gmail용 단순 HTML로 변환
                html_body = self._create_gmail_safe_html({
                    'company_name': getattr(Config, 'COMPANY_NAME', self.company_domain.upper()),
                    'title': '면접 시스템 알림',
                    'recipient_name': '고객',
                    'main_message': self._strip_emojis(self._html_to_text(body)),
                    'position': '',
                    'interviewer': '',
                    'action_link': '#',
                    'button_text': '확인하기',
                    'unsubscribe_email': Config.HR_EMAILS[0] if Config.HR_EMAILS else self.email_config.EMAIL_USER
                })
                optimized_subject = self._optimize_subject_for_gmail(subject)
            else:
                html_body = body
                optimized_subject = subject
            
            # 4. MIME 구조 생성
            if is_html:
                text_body = self._html_to_text(html_body)
                msg = self._create_optimized_mime_structure(
                    text_body, html_body, 
                    attachment_data, 
                    attachment_name
                )
            else:
                msg = MIMEMultipart()
                text_part = MIMEText(body, 'plain', 'utf-8')
                msg.attach(text_part)
                
                # 첨부파일 추가
                if attachment_data and attachment_name:
                    attachment = MIMEBase('application', 'octet-stream')
                    attachment.set_payload(attachment_data)
                    encoders.encode_base64(attachment)
                    attachment.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{attachment_name}"'
                    )
                    msg.attach(attachment)
                    logger.info(f"  - 첨부파일: {attachment_name}")
            
            # 5. 헤더 설정
            msg = self._add_anti_spam_headers(msg, primary_email)
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
            
            # 6. SMTP 연결 및 발송
            server = self._create_smtp_connection()
            if server:
                text = msg.as_string()
                server.sendmail(self.email_config.EMAIL_USER, all_recipients, text)
                server.quit()
                
                logger.info(f"✅ 이메일 발송 성공: {validated_emails}")
                return True
            else:
                logger.error("❌ SMTP 서버 연결 실패")
                return False
                
        except Exception as e:
            logger.error(f"❌ 이메일 발송 실패: {e}")
            import traceback
            logger.error(f"  - Traceback: {traceback.format_exc()}")
            return False

    def _get_company_signature(self, is_gmail_optimized: bool = False) -> str:
        """회사 이메일 서명 (Gmail 최적화 버전 포함)"""
        if is_gmail_optimized:
            # Gmail용 간단하고 전문적인 서명
            return f"""
            <div style="margin-top: 30px; padding-top: 20px; border-top: 2px solid #dee2e6; font-size: 13px; color: #666; font-family: Arial, sans-serif;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 5px 0;">
                            <strong>{self.company_domain.upper()}</strong> 인사팀
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 0;">
                            이메일: <a href="mailto:{Config.HR_EMAILS[0] if Config.HR_EMAILS else self.email_config.EMAIL_USER}" style="color: #007bff;">{Config.HR_EMAILS[0] if Config.HR_EMAILS else self.email_config.EMAIL_USER}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 0;">
                            본 메일은 면접 일정 조율을 위해 자동 발송되었습니다.
                        </td>
                    </tr>
                </table>
                
                <p style="margin-top: 15px; font-size: 12px; color: #999;">
                    더 이상 이런 메일을 받고 싶지 않으시면 
                    <a href="mailto:{Config.HR_EMAILS[0] if Config.HR_EMAILS else self.email_config.EMAIL_USER}?subject=수신거부요청" style="color: #999;">여기를 클릭</a>하세요.
                </p>
            </div>
            """
        else:
            # 기존 화려한 서명
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
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', html_content)
        # 연속된 공백 정리
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _create_gmail_optimized_subject(self, original_subject: str) -> str:
        """Gmail 최적화된 제목 생성 (스팸 단어 제거)"""
        return self._optimize_subject_for_gmail(original_subject)

    def _create_professional_email_body(self, request, interviewer_info, candidate_link, is_gmail_optimized=False):
        """전문적이고 스팸 방지된 이메일 본문 생성"""
        
        # 가능한 일정 목록
        slots_html = ""
        for i, slot in enumerate(request.available_slots, 1):
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            slots_html += f"""
            <tr style="background-color: {bg_color};">
                <td style="padding: 15px; text-align: center; font-weight: bold;">옵션 {i}</td>
                <td style="padding: 15px; text-align: center;">{format_date_korean(slot.date)}</td>
                <td style="padding: 15px; text-align: center; color: #007bff;">{slot.time}</td>
                <td style="padding: 15px; text-align: center;">{slot.duration}분</td>
            </tr>
            """
        
        if is_gmail_optimized:
            # Gmail 최적화 버전 - 단순하고 전문적
            return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.company_domain.upper()} 면접 일정 안내</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8f9fa; font-family: Arial, 'Malgun Gothic', sans-serif;">
    <div style="max-width: 700px; margin: 0 auto; background-color: white;">
        
        <!-- 회사 헤더 -->
        <div style="background-color: #ffffff; padding: 30px; border-bottom: 3px solid #007bff; text-align: center;">
            <h1 style="color: #333; margin: 0; font-size: 24px;">{self.company_domain.upper()}</h1>
            <p style="color: #666; margin: 10px 0 0 0;">Human Resources Department</p>
        </div>
        
        <!-- 본문 -->
        <div style="padding: 40px;">
            <h2 style="color: #333; margin-top: 0;">면접 일정 안내</h2>
            
            <p style="color: #555; line-height: 1.6; margin-bottom: 25px;">
                안녕하세요, <strong>{request.candidate_name}</strong>님<br>
                {request.position_name} 포지션 지원에 감사드립니다.
            </p>
            
            <!-- 면접 정보 -->
            <div style="background-color: #f8f9fa; padding: 25px; border-radius: 8px; margin: 25px 0;">
                <h3 style="color: #007bff; margin-top: 0; margin-bottom: 20px;">면접 정보</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; font-weight: bold; color: #333; width: 120px;">포지션</td>
                        <td style="padding: 8px 0; color: #555;">{request.position_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; font-weight: bold; color: #333;">면접관</td>
                        <td style="padding: 8px 0; color: #555;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                    </tr>
                </table>
            </div>
            
            <!-- 제안 일정 -->
            <div style="margin: 30px 0;">
                <h3 style="color: #007bff; margin-bottom: 20px;">제안 면접 일정</h3>
                <table style="width: 100%; border-collapse: collapse; border: 1px solid #dee2e6;">
                    <thead>
                        <tr style="background-color: #007bff; color: white;">
                            <th style="padding: 15px; text-align: center;">구분</th>
                            <th style="padding: 15px; text-align: center;">날짜</th>
                            <th style="padding: 15px; text-align: center;">시간</th>
                            <th style="padding: 15px; text-align: center;">소요시간</th>
                        </tr>
                    </thead>
                    <tbody>
                        {slots_html}
                    </tbody>
                </table>
            </div>
            
            <!-- 버튼 -->
            <div style="text-align: center; margin: 40px 0;">
                <a href="{candidate_link}" 
                   style="display: inline-block; background-color: #007bff; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    일정 선택하기
                </a>
            </div>
            
            <!-- 안내사항 -->
            <div style="background-color: #e7f3ff; padding: 20px; border-radius: 5px; border-left: 4px solid #007bff;">
                <h4 style="color: #0056b3; margin-top: 0;">안내사항</h4>
                <ul style="color: #0056b3; line-height: 1.6; margin: 0; padding-left: 20px;">
                    <li>제안된 일정 중 가능한 시간을 선택해 주시기 바랍니다</li>
                    <li>별도 요청사항이 있으시면 함께 입력해 주세요</li>
                    <li>면접 당일 신분증을 지참해 주시기 바랍니다</li>
                </ul>
            </div>
        </div>
        
        <!-- 푸터 -->
        <div style="background-color: #f8f9fa; padding: 25px; text-align: center; border-top: 1px solid #dee2e6;">
            <p style="color: #666; margin: 0; font-size: 14px;">
                본 메일은 {self.company_domain.upper()} 인사팀에서 발송되었습니다.<br>
                문의사항: <a href="mailto:{Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@company.com'}" style="color: #007bff;">{Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@company.com'}</a>
            </p>
        </div>
    </div>
</body>
</html>"""
        else:
            # 기존 화려한 버전
            return f"""
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

    def send_interviewer_invitation(self, request: InterviewRequest):
        """면접관에게 일정 입력 요청 메일 발송"""
        try:
            interviewer_email = get_employee_email(request.interviewer_id)
            interviewer_info = get_employee_info(request.interviewer_id)
            
            # Gmail 수신자 체크
            is_gmail = self._is_gmail_recipient(interviewer_email)
            logger.info(f"📧 면접관 초대 메일 준비 - 면접관: {interviewer_email} (Gmail: {is_gmail})")
            
            link = f"https://interview-scheduler-ajnetworks.streamlit.app/면접관_일정입력"
            
            # Gmail인 경우 제목 최적화
            if is_gmail:
                subject = f"[{self.company_domain.upper()}] 면접 일정 입력 요청 - {request.position_name}"
            else:
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
            
            result = self.send_email(
                to_emails=[interviewer_email],
                cc_emails=Config.HR_EMAILS,
                subject=subject,
                body=body
            )
            
            logger.info(f"📧 면접관 초대 메일 발송 결과: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 면접관 초대 메일 발송 실패: {e}")
            return False

    def send_candidate_invitation(self, request: InterviewRequest):
        """면접자에게 일정 선택 요청 메일 발송 - Gmail 최적화"""
        try:
            interviewer_info = get_employee_info(request.interviewer_id)
            candidate_link = f"https://candidate-app.streamlit.app/"
            
            # Gmail 수신자 체크
            is_gmail = self._is_gmail_recipient(request.candidate_email)
            logger.info(f"📧 면접자 초대 메일 준비 - 면접자: {request.candidate_email} (Gmail: {is_gmail})")
            
            # Gmail인 경우 제목 최적화
            if is_gmail:
                subject = self._create_gmail_optimized_subject(f"면접 일정 안내 - {request.position_name}")
            else:
                subject = "📅 [면접 일정 선택] 면접 일정을 선택해주세요"
            
            # Gmail 최적화 여부에 따른 본문 생성
            body = self._create_professional_email_body(request, interviewer_info, candidate_link, is_gmail)
            
            logger.info(f"📧 면접자 초대 메일 발송 - 면접자: {request.candidate_email}, 인사팀: {Config.HR_EMAILS}")
            
            result = self.send_email(
                to_emails=[request.candidate_email],
                cc_emails=Config.HR_EMAILS,
                subject=subject,
                body=body,
                is_html=True
            )
            
            logger.info(f"📧 면접자 초대 메일 발송 결과: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 면접자 초대 메일 발송 실패: {e}")
            return False

    def send_confirmation_notification(self, request: InterviewRequest, sender_type="interviewer"):
        """면접 확정 알림 메일 발송 (Gmail 최적화 적용)"""
        try:
            interviewer_email = get_employee_email(request.interviewer_id)
            interviewer_info = get_employee_info(request.interviewer_id)
            
            # Gmail 수신자 체크
            has_gmail = self._has_gmail_recipients([interviewer_email, request.candidate_email])
            logger.info(f"📧 확정 알림 메일 준비 - 발송자 타입: {sender_type} (Gmail 최적화: {has_gmail})")
            
            if request.status == Config.Status.CONFIRMED:
                if has_gmail:
                    subject = f"[{self.company_domain.upper()}] 면접 일정 확정 - {request.position_name}"
                else:
                    subject = "✅ [면접 일정 확정] 면접 일정이 확정되었습니다"
                status_color = "#28a745"
                status_text = "확정 완료"
                status_icon = "🎉"
                header_gradient = "linear-gradient(135deg, #28a745 0%, #20c997 100%)"
            else:
                if has_gmail:
                    subject = f"[{self.company_domain.upper()}] 면접 일정 조율 필요 - {request.position_name}"
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
            
            # 발송자에 따른 수신자 구분
            if sender_type == "interviewer":
                primary_recipients = [request.candidate_email]
                cc_recipients = Config.HR_EMAILS
                logger.info(f"📧 면접관이 확정 - 면접자에게 발송: {request.candidate_email}")
            elif sender_type == "candidate":
                primary_recipients = [interviewer_email]
                cc_recipients = Config.HR_EMAILS
                self._send_candidate_confirmation_email(request)
                logger.info(f"📧 면접자가 선택 - 면접관에게 발송: {interviewer_email}")
            else:
                primary_recipients = [interviewer_email, request.candidate_email]
                cc_recipients = Config.HR_EMAILS
                logger.info(f"📧 기본 발송 - 모든 관련자")
            
            # 캘린더 초대장 첨부 (확정된 경우만)
            attachment_data = None
            attachment_name = None
            if request.status == Config.Status.CONFIRMED and request.selected_slot:
                try:
                    ics_content = create_calendar_invite(request)
                    if ics_content:
                        attachment_data = ics_content.encode('utf-8')
                        attachment_name = f"면접일정_{request.candidate_name}_{request.selected_slot.date}.ics"
                        logger.info(f"📅 캘린더 초대장 첨부: {attachment_name}")
                except Exception as e:
                    logger.warning(f"캘린더 초대장 생성 실패: {e}")
            
            result = self.send_email(
                to_emails=primary_recipients,
                cc_emails=cc_recipients,
                subject=subject,
                body=body,
                attachment_data=attachment_data,
                attachment_name=attachment_name,
                attachment_mime_type="text/calendar"
            )
            
            logger.info(f"📧 확정 알림 메일 발송 결과: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 확정 알림 메일 발송 실패: {e}")
            return False

    def _send_candidate_confirmation_email(self, request: InterviewRequest):
        """면접자용 확정 확인 메일"""
        try:
            is_gmail = self._is_gmail_recipient(request.candidate_email)
            
            if is_gmail:
                subject = f"[{self.company_domain.upper()}] 면접 일정 선택 완료 - {request.position_name}"
            else:
                subject = "✅ [면접 일정 선택 완료] 선택이 완료되었습니다"
            
            body = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 30px; text-align: center; border-radius: 15px 15px 0 0;">
                    <div style="font-size: 2.5rem; margin-bottom: 15px;">✅</div>
                    <h1 style="margin: 0; font-size: 1.8rem; font-weight: 300;">일정 선택이 완료되었습니다</h1>
                </div>
                
                <div style="padding: 40px; background-color: #f8f9fa; border-radius: 0 0 15px 15px;">
                    <p style="font-size: 1.1rem; line-height: 1.8; color: #555;">
                        안녕하세요, <strong>{request.candidate_name}</strong>님<br>
                        면접 일정 선택이 완료되었습니다. 면접관에게 확정 알림이 전송되었으며, 
                        최종 확정 후 다시 한 번 알림을 드리겠습니다.
                    </p>
                    
                    <div style="background-color: white; padding: 25px; border-radius: 12px; border-left: 5px solid #28a745; margin: 20px 0;">
                        <h4 style="color: #28a745; margin-top: 0;">📅 선택하신 일정</h4>
                        <p style="font-size: 1.2rem; font-weight: bold; color: #333; margin: 0;">
                            {format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)
                        </p>
                    </div>
                </div>
            </div>
            """
            
            result = self.send_email(
                to_emails=[request.candidate_email],
                subject=subject,
                body=body
            )
            
            logger.info(f"📧 면접자 확인 메일 발송 결과: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 면접자 확인 메일 발송 실패: {e}")
            return False

    def send_interviewer_notification_on_candidate_selection(self, request: InterviewRequest):
        """면접자가 일정을 선택했을 때 면접관에게만 발송하는 함수 (Gmail 최적화)"""
        try:
            interviewer_email = get_employee_email(request.interviewer_id)
            interviewer_info = get_employee_info(request.interviewer_id)
            
            # Gmail 수신자 체크
            is_gmail = self._is_gmail_recipient(interviewer_email)
            
            if is_gmail:
                subject = f"[{self.company_domain.upper()}] 면접 일정 확정 - {request.position_name}"
            else:
                subject = "📅 [면접 일정 확정] 면접자가 일정을 선택했습니다"
            
            logger.info(f"📧 면접자 선택 완료 알림 준비 - 면접관: {interviewer_email} (Gmail: {is_gmail})")
            
            body = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto;">
                <!-- 헤더 -->
                <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 40px; text-align: center; border-radius: 15px 15px 0 0;">
                    <div style="font-size: 3rem; margin-bottom: 15px;">🎉</div>
                    <h1 style="margin: 0; font-size: 2.2rem; font-weight: 300;">면접 일정이 확정되었습니다</h1>
                </div>
                
                <!-- 본문 -->
                <div style="padding: 50px; background-color: #f8f9fa; border-radius: 0 0 15px 15px;">
                    <div style="background-color: white; padding: 40px; border-radius: 15px;">
                        <h2 style="color: #333; margin: 0 0 15px 0;">안녕하세요, <strong style="color: #28a745;">{interviewer_info['name']}</strong>님</h2>
                        <p style="color: #666; margin: 8px 0 25px 0;">({interviewer_info['department']})</p>
                        <p style="font-size: 1.1rem; line-height: 1.8; color: #555;">면접자가 제안하신 일정 중 하나를 선택했습니다.</p>
                    </div>
                    
                    <!-- 확정된 면접 정보 -->
                    <div style="background-color: white; padding: 30px; border-radius: 15px; border-left: 8px solid #28a745; margin: 30px 0;">
                        <h3 style="color: #28a745; margin-top: 0;">📋 확정된 면접 정보</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 15px; font-weight: bold; color: #333; width: 160px;">💼 포지션</td>
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
                            <tr style="background-color: #f8f9fa;">
                                <td style="padding: 15px; font-weight: bold; color: #333;">📅 확정일시</td>
                                <td style="padding: 15px; color: #28a745; font-size: 1.2rem; font-weight: bold;">
                                    {format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)
                                </td>
                            </tr>
                        </table>
                    </div>
                    
                    <!-- 안내사항 -->
                    <div style="background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #28a745;">
                        <h4 style="margin-top: 0; color: #155724;">💡 안내사항</h4>
                        <ul style="color: #155724; line-height: 2;">
                            <li>면접 일정이 최종 확정되었습니다</li>
                            <li>면접자와 인사팀에게도 확정 알림이 전송되었습니다</li>
                            <li>일정 변경이 필요한 경우 인사팀에 연락해주세요</li>
                        </ul>
                    </div>
                </div>
            </div>
            """
            
            logger.info(f"📧 면접자 선택 완료 알림 - 면접관에게만 발송: {interviewer_email}")
            
            result = self.send_email(
                to_emails=[interviewer_email],
                cc_emails=Config.HR_EMAILS,
                subject=subject,
                body=body
            )
            
            logger.info(f"📧 면접자 선택 완료 알림 발송 결과: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 면접자 선택 완료 알림 발송 실패: {e}")
            return False

    def send_automatic_confirmation_email(self, request: InterviewRequest):
        """구글시트 L열 변경 감지 시 자동 확정 알림 발송"""
        try:
            logger.info(f"📧 자동 확정 알림 발송 시작 - 요청 ID: {request.id[:8]}...")
            
            # 1. 면접자에게 확정 알림
            candidate_success = self.send_confirmation_notification(request, sender_type="system")
            
            # 2. 면접관에게 확정 알림
            interviewer_success = self.send_interviewer_notification_on_candidate_selection(request)
            
            if candidate_success and interviewer_success:
                logger.info(f"✅ 자동 확정 알림 발송 성공: {request.id[:8]}...")
                return True
            else:
                logger.warning(f"⚠️ 일부 자동 확정 알림 발송 실패: {request.id[:8]}...")
                return False
                
        except Exception as e:
            logger.error(f"❌ 자동 확정 알림 발송 실패: {e}")
            return False

    def test_html_email(self):
        """HTML 이메일 테스트 함수"""
        try:
            test_subject = "🧪 HTML 이메일 테스트"
            test_body = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>테스트</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: white;">
        <h1 style="color: #28a745;">HTML 이메일 테스트</h1>
        <p style="color: #555; font-size: 16px;">이 메일이 <strong style="color: #007bff;">HTML로 제대로 표시</strong>되나요?</p>
        <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px; border-radius: 10px; text-align: center;">
            <h2 style="margin: 0;">✅ 성공!</h2>
        </div>
    </div>
</body>
</html>"""
            
            result = self.send_email(
                to_emails=[self.email_config.EMAIL_USER],
                subject=test_subject,
                body=test_body,
                is_html=True
            )
            
            logger.info(f"📧 HTML 테스트 메일 발송 결과: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ HTML 테스트 메일 발송 실패: {e}")
            return False
