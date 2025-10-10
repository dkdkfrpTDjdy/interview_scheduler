import os
from datetime import datetime, timedelta
import pytz

class Config:
    # 데이터베이스 설정
    DATABASE_PATH = "interview_scheduler.db"
    
    # 시간대 설정
    TIMEZONE = pytz.timezone('Asia/Seoul')
    
    # Outlook 이메일 설정
    class EmailConfig:
        # Exchange Server 설정 (회사 Exchange 서버용)
        EXCHANGE_SERVER = os.getenv("EXCHANGE_SERVER", "outlook.office365.com")
        EXCHANGE_PORT = int(os.getenv("EXCHANGE_PORT", "587"))
        
        # Outlook.com 설정 (개인 Outlook 계정용)
        OUTLOOK_SMTP_SERVER = "smtp-mail.outlook.com"
        OUTLOOK_SMTP_PORT = 587
        
        # 인증 정보
        EMAIL_USER = os.getenv("OUTLOOK_EMAIL")  # 회사 이메일 주소
        EMAIL_PASSWORD = os.getenv("OUTLOOK_PASSWORD")  # 앱 비밀번호 또는 계정 비밀번호
        
        # OAuth 설정 (선택사항 - 더 보안이 강화된 방법)
        CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
        CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
        TENANT_ID = os.getenv("OUTLOOK_TENANT_ID")
    
    # 회사 도메인 설정
    COMPANY_DOMAIN = os.getenv("COMPANY_DOMAIN", "yourcompany.com")
    
    # 앱 URL
    APP_URL = os.getenv("APP_URL", "https://your-app.streamlit.app")
    
    # 면접 시간 슬롯
    TIME_SLOTS = [
        "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
        "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
        "16:00", "16:30", "17:00", "17:30"
    ]
    
    # 상태 관리
    class Status:
        PENDING_INTERVIEWER = "면접관_일정대기"
        PENDING_CANDIDATE = "면접자_선택대기" 
        PENDING_CONFIRMATION = "확정대기"
        CONFIRMED = "확정완료"
        CANCELLED = "취소됨"
    
    # 인사팀 이메일 주소들
    HR_EMAILS = [
        "hr@ajnet.co.kr",
        "recruitment@ajnet.co.kr"
    ]