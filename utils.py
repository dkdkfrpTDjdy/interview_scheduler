from datetime import datetime, timedelta
from typing import List
import calendar
import pandas as pd
from config import Config
import os

def get_next_weekdays(days: int = 14) -> List[str]:
    """향후 N일간의 평일 날짜 반환"""
    weekdays = []
    current_date = datetime.now().date()
    
    while len(weekdays) < days:
        current_date += timedelta(days=1)
        if current_date.weekday() < 5:  # 월-금 (0-4)
            weekdays.append(current_date.strftime('%Y-%m-%d'))
    
    return weekdays

def format_date_korean(date_str: str) -> str:
    """날짜를 한국어 형식으로 변환"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        weekday_names = ['월', '화', '수', '목', '금', '토', '일']
        weekday = weekday_names[date_obj.weekday()]
        return f"{date_obj.month}월 {date_obj.day}일 ({weekday})"
    except:
        return date_str

def validate_email(email: str) -> bool:
    """이메일 유효성 검사"""
    if not email:
        return False
    
    email = email.strip()
    
    # 기본 검사
    if '@' not in email or '.' not in email:
        return False
    
    parts = email.split('@')
    if len(parts) != 2:
        return False
    
    local, domain = parts
    
    # 로컬과 도메인이 비어있지 않은지 확인
    if not local or not domain:
        return False
    
    # 도메인에 점이 있는지 확인
    if '.' not in domain:
        return False
    
    # 도메인이 점으로 시작하거나 끝나지 않는지 확인
    if domain.startswith('.') or domain.endswith('.'):
        return False
    
    return True

def load_employee_data():
    """조직도 엑셀 파일에서 직원 데이터 로드"""
    try:
        if not os.path.exists(Config.EMPLOYEE_DATA_PATH):
            print(f"조직도 파일을 찾을 수 없습니다: {Config.EMPLOYEE_DATA_PATH}")
            return []
        
        # 엑셀 파일 읽기
        df = pd.read_excel(Config.EMPLOYEE_DATA_PATH)
        
        # 필요한 컬럼: 사번, 이름, 부서, 이메일
        # 한글 컬럼명 우선 시도
        required_columns = ['사번', '이름', '부서', '이메일']
        
        # 영문 컬럼명으로도 시도
        if not all(col in df.columns for col in required_columns):
            required_columns = ['employee_id', 'name', 'department', 'email']
        
        if not all(col in df.columns for col in required_columns):
            print(f"필요한 컬럼을 찾을 수 없습니다. 현재 컬럼: {list(df.columns)}")
            print("필요한 컬럼: ['사번', '이름', '부서', '이메일'] 또는 ['employee_id', 'name', 'department', 'email']")
            return []
        
        employees = []
        for _, row in df.iterrows():
            if pd.notna(row[required_columns[0]]):  # 사번이 있는 경우만
                employee = {
                    'employee_id': str(row[required_columns[0]]).strip(),
                    'name': str(row[required_columns[1]]).strip(),
                    'department': str(row[required_columns[2]]).strip(),
                    'email': str(row[required_columns[3]]).strip() if pd.notna(row[required_columns[3]]) else f"{str(row[required_columns[0]]).strip().lower()}@{Config.COMPANY_DOMAIN}"
                }
                employees.append(employee)
        
        print(f"조직도 데이터 로드 성공: {len(employees)}명")
        return employees
        
    except Exception as e:
        print(f"조직도 데이터 로드 실패: {e}")
        return []

def get_employee_email(employee_id: str) -> str:
    """사번으로 직원 이메일 조회 (실제 이메일 주소 반환)"""
    employees = load_employee_data()
    
    for emp in employees:
        if emp['employee_id'] == employee_id:
            return emp['email']
    
    # 조직도에서 찾지 못한 경우 기본 이메일 형식 사용
    print(f"Warning: 사번 {employee_id}에 대한 이메일을 조직도에서 찾을 수 없습니다. 기본 형식을 사용합니다.")
    return f"{employee_id.lower()}@{Config.COMPANY_DOMAIN}"

def get_employee_info(employee_id: str) -> dict:
    """사번으로 직원 정보 조회"""
    employees = load_employee_data()
    
    for emp in employees:
        if emp['employee_id'] == employee_id:
            return emp
    
    # 기본 정보 반환
    print(f"Warning: 사번 {employee_id}에 대한 정보를 조직도에서 찾을 수 없습니다.")
    return {
        'employee_id': employee_id,
        'name': employee_id,
        'department': '미확인',
        'email': f"{employee_id.lower()}@{Config.COMPANY_DOMAIN}"
    }

def get_employees_by_department(department: str) -> List[dict]:
    """부서별 직원 목록 조회"""
    employees = load_employee_data()
    return [emp for emp in employees if department.lower() in emp['department'].lower()]

def search_employee(keyword: str) -> List[dict]:
    """키워드로 직원 검색 (이름, 사번, 부서)"""
    employees = load_employee_data()
    keyword = keyword.lower()
    
    results = []
    for emp in employees:
        if (keyword in emp['name'].lower() or 
            keyword in emp['employee_id'].lower() or 
            keyword in emp['department'].lower()):
            results.append(emp)
    
    return results

def create_calendar_invite(request) -> str:
    """캘린더 초대장 생성 (ICS 형식)"""
    try:
        from datetime import datetime
        
        if not request.selected_slot:
            return None
        
        # 면접 날짜와 시간 파싱
        interview_date = datetime.strptime(request.selected_slot.date, '%Y-%m-%d')
        time_parts = request.selected_slot.time.split(':')
        interview_datetime = interview_date.replace(
            hour=int(time_parts[0]), 
            minute=int(time_parts[1])
        )
        
        # 종료 시간 계산
        end_datetime = interview_datetime + timedelta(minutes=request.selected_slot.duration)
        
        # ICS 형식으로 생성
        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//AI Interview System//Interview Schedule//KR
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{request.id}@{Config.COMPANY_DOMAIN}
DTSTART:{interview_datetime.strftime('%Y%m%dT%H%M%S')}
DTEND:{end_datetime.strftime('%Y%m%dT%H%M%S')}
SUMMARY:면접 - {request.position_name}
DESCRIPTION:면접자: {request.candidate_name}\\n포지션: {request.position_name}\\n면접관: {request.interviewer_id}\\n\\n※ 면접 10분 전까지 도착해주세요.
LOCATION:회사 면접실
ORGANIZER:mailto:{get_employee_email(request.interviewer_id)}
ATTENDEE:mailto:{request.candidate_email}
STATUS:CONFIRMED
TRANSP:OPAQUE
BEGIN:VALARM
TRIGGER:-PT30M
ACTION:DISPLAY
DESCRIPTION:면접 30분 전 알림
END:VALARM
END:VEVENT
END:VCALENDAR"""
        
        return ics_content
        
    except Exception as e:
        print(f"캘린더 초대장 생성 실패: {e}")
        return None
