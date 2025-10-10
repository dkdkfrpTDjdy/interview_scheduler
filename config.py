import os
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    # 데이터베이스 설정
    DATABASE_PATH = "interview_scheduler.db"
    
    # 시간대 설정
    TIMEZONE = pytz.timezone('Asia/Seoul')
    
    # Outlook 이메일 설정
    class EmailConfig:
        EXCHANGE_SERVER = os.getenv("EXCHANGE_SERVER", "smtp.gmail.com")
        EXCHANGE_PORT = int(os.getenv("EXCHANGE_PORT", "587"))
        OUTLOOK_SMTP_SERVER = "smtp-mail.outlook.com"
        OUTLOOK_SMTP_PORT = 587
        
        EMAIL_USER = os.getenv("OUTLOOK_EMAIL")
        EMAIL_PASSWORD = os.getenv("OUTLOOK_PASSWORD")
        
        CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
        CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
        TENANT_ID = os.getenv("OUTLOOK_TENANT_ID")
    
    # 회사 도메인 설정
    COMPANY_DOMAIN = os.getenv("COMPANY_DOMAIN", "ajnet.co.kr")
    
    # 앱 URL (메인 앱과 면접자 전용 앱 분리)
    APP_URL = os.getenv("APP_URL", "https://interview-scheduler-ajnet.streamlit.app")
    # 🔧 새로 추가: 면접자 전용 독립 앱 URL
    CANDIDATE_APP_URL = os.getenv("CANDIDATE_APP_URL", "https://interview-candidate-ajnet.streamlit.app")
    
    # 면접 시간 슬롯 (오전 9시 ~ 오후 5시, 30분 단위)
    TIME_SLOTS = [
        "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
        "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", 
        "15:00", "15:30", "16:00", "16:30", "17:00"
    ]
    
    # 상태 관리
    class Status:
        PENDING_INTERVIEWER = "면접관_일정대기"
        PENDING_CANDIDATE = "면접자_선택대기" 
        PENDING_CONFIRMATION = "재조율_대기"
        CONFIRMED = "확정완료"
        CANCELLED = "취소됨"
    
    # 인사팀 이메일 주소 (고정)
    HR_EMAILS = [
        "hr@ajnet.co.kr"
    ]
    
    # 구글 시트 설정
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    GOOGLE_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/edit" if os.getenv("GOOGLE_SHEET_ID") else ""
    GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "service-account.json")
    
    # 조직도 엑셀 파일 경로
    EMPLOYEE_DATA_PATH = os.getenv("EMPLOYEE_DATA_PATH", "employee_data.xlsx")
    
    # 🔧 새로 추가: 이메일 템플릿 설정
    class EmailTemplates:
        # 이메일 공통 스타일
        COMMON_STYLE = """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
            body { font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            .btn-primary { background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); }
            .btn-success { background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%); }
            .btn-warning { background: linear-gradient(135deg, #ffc107 0%, #e0a800 100%); }
        </style>
        """
