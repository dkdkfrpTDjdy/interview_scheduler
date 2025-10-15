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

    def validate_and_correct_email(self, email: str) -> Tuple[str, bool]:
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
        """Gmail 안전 HTML 생성"""
        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{content_data.get('title', '이메일 알림')}</title>
</head>
<body style="margin:0;padding:0;font-family:'Malgun Gothic',Arial,sans-serif;background-color:#f8f9fa;line-height:1.6;">
    <div style="max-width:600px;margin:0 auto;background-color:#ffffff;">
        <!-- 헤더 -->
        <div style="background-color:#007bff;color:#ffffff;padding:30px;text-align:center;">
            <h1 style="margin:0;font-size:24px;font-weight:300;">{content_data.get('company_name', 'AJ Networks')}</h1>
            <p style="margin:10px 0 0 0;font-size:14px;opacity:0.9;">{content_data.get('title', '면접 시스템 알림')}</p>
        </div>
        
        <!-- 본문 -->
        <div style="padding:40px 30px;">
            <h2 style="color:#333333;margin:0 0 20px 0;font-size:20px;">
                안녕하세요, {content_data.get('recipient_name', '고객')}님
            </h2>
            
            <p style="color:#555555;margin:0 0 25px 0;">
                {content_data.get('main_message', '메시지 내용')}
            </p>
            
            <!-- 정보 테이블 -->
            <table style="width:100%;border-collapse:collapse;border:1px solid #dee2e6;margin:20px 0;">
                <tr style="background-color:#f8f9fa;">
                    <td style="padding:12px;font-weight:bold;color:#333333;width:30%;border:1px solid #dee2e6;">포지션</td>
                    <td style="padding:12px;color:#555555;border:1px solid #dee2e6;">{content_data.get('position', '')}</td>
                </tr>
                <tr>
                    <td style="padding:12px;font-weight:bold;color:#333333;border:1px solid #dee2e6;">면접관</td>
                    <td style="padding:12px;color:#555555;border:1px solid #dee2e6;">{content_data.get('interviewer', '')}</td>
                </tr>
            </table>
            
            <!-- CTA 버튼 -->
            <div style="text-align:center;margin:30px 0;">
                <a href="{content_data.get('action_link', '#')}" 
                   style="display:inline-block;padding:15px 30px;background-color:#007bff;color:#ffffff;text-decoration:none;border-radius:5px;font-weight:bold;">
                    {content_data.get('button_text', '확인하기')}
                </a>
            </div>
            
            <!-- 추가 내용 -->
            <div style="background-color:#f8f9fa;padding:20px;border-radius:5px;margin:20px 0;">
                {content_data.get('additional_content', '')}
            </div>
        </div>
        
        <!-- 푸터 -->
        <div style="background-color:#f8f9fa;padding:20px 30px;text-align:center;border-top:1px solid #dee2e6;">
            <p style="margin:0;font-size:12px;color:#666666;">
                본 메일은 {content_data.get('company_name', 'AJ Networks')} 인사팀에서 발송되었습니다.<br>
                문의: <a href="mailto:{content_data.get('contact_email', 'hr@ajnet.co.kr')}" style="color:#007bff;">{content_data.get('contact_email', 'hr@ajnet.co.kr')}</a>
            </p>
        </div>
    </div>
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
            # 이메일 주소 검증 및 교정
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
    
            logger.info(f"📧 이메일 발송 시작")
            logger.info(f"  - TO: {validated_emails}")
            logger.info(f"  - CC: {cc_emails}")
            logger.info(f"  - Subject: {subject}")
            
            # Gmail 수신자 감지
            has_gmail = self._has_gmail_recipients(validated_emails, cc_emails, bcc_emails)
            logger.info(f"  - Gmail 수신자 포함: {has_gmail}")
            
            # 컨텐츠 최적화
            if has_gmail and is_html:
                optimized_subject = self._optimize_subject_for_gmail(subject)
                text_body = self._html_to_text(body)
                html_body = body
            else:
                optimized_subject = subject
                text_body = self._html_to_text(body) if is_html else body
                html_body = body if is_html else f"<pre>{body}</pre>"
            
            # MIME 구조 생성
            if is_html:
                msg = self._create_optimized_mime_structure(
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
                    attachment.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{attachment_name}"'
                    )
                    msg.attach(attachment)
                    logger.info(f"  - 첨부파일: {attachment_name}")
            
            # 헤더 설정
            primary_email = validated_emails[0]
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
            
            # SMTP 연결 및 발송
            server = self._create_smtp_connection()
            if server:
                try:
                    text = msg.as_string()
                    server.sendmail(self.email_config.EMAIL_USER, all_recipients, text)
                    
                    # 서버 연결 종료
                    try:
                        server.quit()
                    except:
                        pass
                    
                    logger.info(f"✅ 이메일 발송 성공: {', '.join(validated_emails)}")
                    return True
                    
                except Exception as smtp_error:
                    logger.error(f"❌ SMTP 발송 실패: {smtp_error}")
                    try:
                        server.quit()
                    except:
                        pass
                    return False
            else:
                logger.error("❌ SMTP 서버 연결 실패")
                return False
        
        except Exception as e:
            logger.error(f"❌ 이메일 발송 중 오류: {e}")
            return False

    def _html_to_text(self, html_content: str) -> str:
        """HTML을 텍스트로 변환"""
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', html_content)
        # 연속된 공백 정리
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _create_professional_email_body(self, request, interviewer_info, candidate_link, is_gmail_optimized=False):
        """전문적이고 스팸 방지된 이메일 본문 생성"""
        
        # 가능한 일정 목록
        slots_html = ""
        for i, slot in enumerate(request.available_slots, 1):
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            slots_html += f"""
            <tr style="background-color: {bg_color};">
                <td style="padding: 15px; text-align: center; font-weight: bold; border: 1px solid #dee2e6;">옵션 {i}</td>
                <td style="padding: 15px; text-align: center; border: 1px solid #dee2e6;">{format_date_korean(slot.date)}</td>
                <td style="padding: 15px; text-align: center; color: #007bff; border: 1px solid #dee2e6;">{slot.time}</td>
                <td style="padding: 15px; text-align: center; border: 1px solid #dee2e6;">{slot.duration}분</td>
            </tr>
            """
        
        if is_gmail_optimized:
            # Gmail 최적화 버전
            return self._create_gmail_safe_html({
                'company_name': 'AJ Networks',
                'title': '면접 일정 안내',
                'recipient_name': request.candidate_name,
                'main_message': f'{request.position_name} 포지션 지원에 감사드립니다. 면접관이 제안한 일정 중에서 원하시는 시간을 선택해주세요.',
                'position': request.position_name,
                'interviewer': f"{interviewer_info['name']} ({interviewer_info['department']})",
                'action_link': candidate_link,
                'button_text': '일정 선택하기',
                'additional_content': f"""
                <h4 style="color: #007bff; margin-bottom: 15px;">제안 면접 일정</h4>
                <table style="width: 100%; border-collapse: collapse; border: 1px solid #dee2e6;">
                    <thead>
                        <tr style="background-color: #007bff; color: white;">
                            <th style="padding: 12px; text-align: center; border: 1px solid #dee2e6;">구분</th>
                            <th style="padding: 12px; text-align: center; border: 1px solid #dee2e6;">날짜</th>
                            <th style="padding: 12px; text-align: center; border: 1px solid #dee2e6;">시간</th>
                            <th style="padding: 12px; text-align: center; border: 1px solid #dee2e6;">소요시간</th>
                        </tr>
                    </thead>
                    <tbody>
                        {slots_html}
                    </tbody>
                </table>
                <div style="margin-top: 20px; padding: 15px; background-color: #e7f3ff; border-radius: 5px; border-left: 4px solid #007bff;">
                    <h5 style="color: #0056b3; margin-top: 0;">안내사항</h5>
                    <ul style="color: #0056b3; margin: 0; padding-left: 20px;">
                        <li>제안된 일정 중 가능한 시간을 선택해 주시기 바랍니다</li>
                        <li>별도 요청사항이 있으시면 함께 입력해 주세요</li>
                        <li>면접 당일 신분증을 지참해 주시기 바랍니다</li>
                    </ul>
                </div>
                """,
                'contact_email': Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'
            })
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
            
            # Gmail용 최적화된 본문
            if is_gmail:
                body = self._create_gmail_safe_html({
                    'company_name': 'AJ Networks',
                    'title': '면접 일정 입력 요청',
                    'recipient_name': interviewer_info['name'],
                    'main_message': f'새로운 면접 일정 조율 요청이 도착했습니다. 아래 정보를 확인하시고 가능한 면접 일정을 입력해주세요.',
                    'position': request.position_name,
                    'interviewer': f"{interviewer_info['name']} ({interviewer_info['department']})",
                    'action_link': link,
                    'button_text': '면접 가능 일정 입력하기',
                    'additional_content': f"""
                    <h4 style="color: #007bff; margin-bottom: 15px;">면접 정보</h4>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #dee2e6;">
                        <tr>
                            <td style="padding: 12px; font-weight: bold; color: #333; border: 1px solid #dee2e6;">포지션</td>
                            <td style="padding: 12px; color: #555; border: 1px solid #dee2e6;">{request.position_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; color: #333; border: 1px solid #dee2e6;">면접자</td>
                            <td style="padding: 12px; color: #555; border: 1px solid #dee2e6;">{request.candidate_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px; font-weight: bold; color: #333; border: 1px solid #dee2e6;">이메일</td>
                            <td style="padding: 12px; color: #555; border: 1px solid #dee2e6;">{request.candidate_email}</td>
                        </tr>
                    </table>
                    """,
                    'contact_email': Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'
                })
            else:
                # 기존 화려한 버전
                body = f"""
                <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 800px; margin: 0 auto;">
                    <div style="background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%); color: white; padding: 40px; text-align: center; border-radius: 15px 15px 0 0;">
                        <div style="font-size: 3rem; margin-bottom: 15px;">📅</div>
                        <h1 style="margin: 0; font-size: 2.2rem; font-weight: 300;">면접 일정 입력 요청</h1>
                        <p style="margin: 15px 0 0 0; font-size: 1.1rem; opacity: 0.9;">Interview Schedule Request</p>
                    </div>
                    
                    <div style="padding: 50px; background-color: #f8f9fa; border-radius: 0 0 15px 15px;">
                        <div style="background-color: white; padding: 40px; border-radius: 15px;">
                            <h2 style="color: #333; margin: 0 0 15px 0;">안녕하세요, <strong style="color: #0078d4;">{interviewer_info['name']}</strong>님</h2>
                            <p style="color: #666; margin: 8px 0 25px 0;">({interviewer_info['department']})</p>
                            <p style="font-size: 1.1rem; line-height: 1.8; color: #555;">새로운 면접 일정 조율 요청이 도착했습니다. 아래 정보를 확인하시고 가능한 면접 일정을 입력해주세요.</p>
                        </div>
                        
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
                        
                        <div style="text-align: center; margin: 50px 0;">
                            <a href="{link}" 
                               style="background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%); color: white; padding: 20px 50px; text-decoration: none; border-radius: 12px; font-weight: bold; display: inline-block; font-size: 1.1rem;">
                                🗓️ 면접 가능 일정 입력하기
                            </a>
                        </div>
                        
                        <div style="background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #28a745;">
                            <h4 style="margin-top: 0; color: #155724;">💡 안내사항</h4>
                            <ul style="color: #155724; line-height: 2;">
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
        """면접자에게 일정 선택 요청 메일 발송"""
        try:
            interviewer_info = get_employee_info(request.interviewer_id)
            candidate_link = f"https://candidate-app.streamlit.app/"
            
            # Gmail 수신자 체크
            is_gmail = self._is_gmail_recipient(request.candidate_email)
            logger.info(f"📧 면접자 초대 메일 준비 - 면접자: {request.candidate_email} (Gmail: {is_gmail})")
            
            # Gmail인 경우 제목 최적화
            if is_gmail:
                subject = self._optimize_subject_for_gmail(f"면접 일정 안내 - {request.position_name}")
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
        """면접 확정 알림 메일 발송"""
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
            else:
                if has_gmail:
                    subject = f"[{self.company_domain.upper()}] 면접 일정 조율 필요 - {request.position_name}"
                else:
                    subject = "⏳ [면접 일정 조율] 추가 조율이 필요합니다"
                status_color = "#ffc107"
                status_text = "추가 조율 필요"
            
            # Gmail용 최적화된 본문
            if has_gmail:
                html_body = self._create_gmail_safe_html({
                    'company_name': 'AJ Networks',
                    'title': f'면접 일정 {status_text}',
                    'recipient_name': '고객',
                    'main_message': f'{request.position_name} 포지션 면접 일정이 {status_text} 상태입니다.',
                    'position': request.position_name,
                    'interviewer': f"{interviewer_info['name']} ({interviewer_info['department']})",
                    'action_link': '#',
                    'button_text': '확인완료',
                    'additional_content': f"""
                    <h4 style="color: #007bff; margin-bottom: 15px;">면접 정보</h4>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #dee2e6;">
                        <tr>
                            <td style="padding: 12px; font-weight: bold; color: #333; border: 1px solid #dee2e6;">포지션</td>
                            <td style="padding: 12px; color: #555; border: 1px solid #dee2e6;">{request.position_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; color: #333; border: 1px solid #dee2e6;">면접관</td>
                            <td style="padding: 12px; color: #555; border: 1px solid #dee2e6;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px; font-weight: bold; color: #333; border: 1px solid #dee2e6;">면접자</td>
                            <td style="padding: 12px; color: #555; border: 1px solid #dee2e6;">{request.candidate_name}</td>
                        </tr>
                        <tr style="background-color: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; color: #333; border: 1px solid #dee2e6;">상태</td>
                            <td style="padding: 12px; color: {status_color}; font-weight: bold; border: 1px solid #dee2e6;">{status_text}</td>
                        </tr>
                        {f'''<tr>
                            <td style="padding: 12px; font-weight: bold; color: #333; border: 1px solid #dee2e6;">확정일시</td>
                            <td style="padding: 12px; color: #28a745; font-weight: bold; border: 1px solid #dee2e6;">{format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)</td>
                        </tr>''' if request.selected_slot else ''}
                    </table>
                    {f'<div style="margin-top: 20px; padding: 15px; background-color: #d1ecf1; border-radius: 5px; border-left: 4px solid #17a2b8;"><h5 style="color: #0c5460; margin-top: 0;">면접자 요청사항</h5><p style="color: #0c5460; margin: 0; white-space: pre-line;">{request.candidate_note}</p></div>' if request.candidate_note else ''}
                    """,
                    'contact_email': Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'
                })
            else:
                # 기존 화려한 HTML 버전 (간소화)
                html_body = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <div style="background-color: {status_color}; color: white; padding: 30px; text-align: center;">
                        <h1 style="margin: 0;">면접 일정 {status_text}</h1>
                    </div>
                    
                    <div style="padding: 30px;">
                        <h3>면접 정보</h3>
                        <table style="width: 100%; border-collapse: collapse; border: 1px solid #dee2e6;">
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">포지션</td>
                                <td style="padding: 12px;">{request.position_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">면접관</td>
                                <td style="padding: 12px;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">면접자</td>
                                <td style="padding: 12px;">{request.candidate_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 12px; font-weight: bold;">상태</td>
                                <td style="padding: 12px; color: {status_color}; font-weight: bold;">{status_text}</td>
                            </tr>
                            {f'<tr><td style="padding: 12px; font-weight: bold;">확정일시</td><td style="padding: 12px; color: #28a745; font-weight: bold;">{format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)</td></tr>' if request.selected_slot else ''}
                        </table>
                        
                        {f'<div style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 5px;"><h4>면접자 요청사항</h4><p style="white-space: pre-line;">{request.candidate_note}</p></div>' if request.candidate_note else ''}
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
                body=html_body,
                attachment_data=attachment_data,
                attachment_name=attachment_name,
                attachment_mime_type="text/calendar",
                is_html=True
            )
            
            logger.info(f"📧 확정 알림 메일 발송 결과: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 확정 알림 메일 발송 실패: {e}")
            return False

    def send_interviewer_notification_on_candidate_selection(self, request: InterviewRequest):
        """면접자가 일정을 선택했을 때 면접관에게만 발송"""
        try:
            interviewer_email = get_employee_email(request.interviewer_id)
            interviewer_info = get_employee_info(request.interviewer_id)
            
            is_gmail = self._is_gmail_recipient(interviewer_email)
            
            if is_gmail:
                subject = f"[{self.company_domain.upper()}] 면접 일정 확정 - {request.position_name}"
                body = self._create_gmail_safe_html({
                    'company_name': 'AJ Networks',
                    'title': '면접 일정 확정',
                    'recipient_name': interviewer_info['name'],
                    'main_message': '면접자가 제안하신 일정 중 하나를 선택했습니다.',
                    'position': request.position_name,
                    'interviewer': f"{interviewer_info['name']} ({interviewer_info['department']})",
                    'action_link': '#',
                    'button_text': '확인완료',
                    'additional_content': f"""
                    <h4 style="color: #007bff;">확정된 면접 정보</h4>
                    <p><strong>확정일시:</strong> {format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)</p>
                    <p><strong>면접자:</strong> {request.candidate_name}</p>
                    """,
                    'contact_email': Config.HR_EMAILS[0] if Config.HR_EMAILS else 'hr@ajnet.co.kr'
                })
            else:
                subject = "📅 [면접 일정 확정] 면접자가 일정을 선택했습니다"
                body = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <div style="background-color: #28a745; color: white; padding: 30px; text-align: center;">
                        <h1 style="margin: 0;">면접 일정이 확정되었습니다</h1>
                    </div>
                    <div style="padding: 30px;">
                        <p>안녕하세요, {interviewer_info['name']}님</p>
                        <p>면접자가 제안하신 일정 중 하나를 선택했습니다.</p>
                        
                        <h3>확정된 면접 정보</h3>
                        <p><strong>포지션:</strong> {request.position_name}</p>
                        <p><strong>면접자:</strong> {request.candidate_name}</p>
                        <p><strong>확정일시:</strong> {format_date_korean(request.selected_slot.date)} {request.selected_slot.time} ({request.selected_slot.duration}분)</p>
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
            test_subject = "HTML 이메일 테스트"
            test_body = self._create_gmail_safe_html({
                'company_name': 'AJ Networks',
                'title': 'HTML 이메일 테스트',
                'recipient_name': '테스터',
                'main_message': '이 메일이 HTML로 제대로 표시되나요?',
                'position': '테스트 포지션',
                'interviewer': '테스트 면접관',
                'action_link': '#',
                'button_text': '테스트 성공',
                'additional_content': '<div style="background-color: #d4edda; padding: 20px; border-radius: 5px; text-align: center;"><h3 style="color: #155724; margin: 0;">✅ HTML 이메일 테스트 성공!</h3></div>',
                'contact_email': 'test@ajnet.co.kr'
            })
            
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
