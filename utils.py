from datetime import datetime, timedelta
from typing import List
import calendar
import pandas as pd
from config import Config
import os
from collections import defaultdict
from typing import Dict, List
from models import InterviewRequest
import re

def group_requests_by_interviewer_and_position(requests: List[InterviewRequest]) -> Dict[str, List[InterviewRequest]]:
    """
    면접관 + 포지션 조합으로 면접 요청 그룹핑
    
    Args:
        requests: 면접 요청 리스트
    
    Returns:
        {
            "면접관1,면접관2_IT혁신팀": [request1, request2, request3],
            "면접관1_데이터분석가": [request4],
        }
    """
    groups = defaultdict(list)
    
    for request in requests:
        # 면접관 ID 정규화 (정렬하여 일관성 유지)
        interviewer_ids = sorted([id.strip() for id in request.interviewer_id.split(',')])
        interviewer_key = ",".join(interviewer_ids)
        
        # 그룹 키 생성: "면접관ID들_포지션명"
        group_key = f"{interviewer_key}_{request.position_name}"
        groups[group_key].append(request)
    
    return groups


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
    """사번으로 직원 이메일 조회 (🔧 실제 이메일 주소 반환)"""
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

from collections import defaultdict
from typing import Dict, List
from models import InterviewRequest, InterviewSlot

def group_requests_by_slot(requests: List[InterviewRequest]) -> Dict[str, List[InterviewRequest]]:
    """
    슬롯별로 면접 요청 그룹핑
    
    Returns:
        {
            "2025-01-15_14:00_면접관1,면접관2": [request1, request2, ...],
            "2025-01-15_15:00_면접관1,면접관2": [request3, ...],
        }
    """
    slot_groups = defaultdict(list)
    
    for request in requests:
        # 면접관 ID 정규화 (쉼표 구분 → 정렬하여 일관성 유지)
        interviewer_ids = sorted([id.strip() for id in request.interviewer_id.split(',')])
        interviewer_key = ",".join(interviewer_ids)
        
        # 슬롯별 키 생성
        if request.available_slots:
            for slot in request.available_slots:
                slot_key = f"{slot.date}_{slot.time}_{interviewer_key}"
                slot_groups[slot_key].append(request)
    
    return slot_groups


def prepare_slot_email_data(slot_key: str, requests: List[InterviewRequest]) -> dict:
    """
    슬롯별 이메일 발송 데이터 준비
    
    Returns:
        {
            'date': '2025-01-15',
            'time': '14:00',
            'interviewer_ids': ['223286', '223287'],
            'position_name': 'IT혁신팀 데이터분석가',
            'candidates': [
                {'name': '홍길동', 'email': 'hong@example.com'},
                {'name': '김철수', 'email': 'kim@example.com'}
            ]
        }
    """
    # 슬롯 키 파싱
    parts = slot_key.split('_')
    date = parts[0]
    time = parts[1]
    interviewer_ids = parts[2].split(',')
    
    # 면접자 정보 수집 (중복 제거)
    candidates = []
    seen_emails = set()
    position_name = requests[0].position_name if requests else ""
    
    for request in requests:
        if request.candidate_email not in seen_emails:
            candidates.append({
                'name': request.candidate_name,
                'email': request.candidate_email
            })
            seen_emails.add(request.candidate_email)
    
    return {
        'date': date,
        'time': time,
        'interviewer_ids': interviewer_ids,
        'position_name': position_name,
        'candidates': candidates
    }

def create_calendar_invite(request) -> str:
    """🔧 개선된 캘린더 초대장 생성 (ICS 형식)"""
    try:
        from datetime import datetime
        import uuid
        
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
        
        # 면접관 정보 조회
        interviewer_info = get_employee_info(request.interviewer_id)
        interviewer_email = get_employee_email(request.interviewer_id)
        
        # UTC 시간으로 변환
        utc_start = interview_datetime.strftime('%Y%m%dT%H%M%S')
        utc_end = end_datetime.strftime('%Y%m%dT%H%M%S')
        
        # 고유 UID 생성
        event_uid = f"{request.id}-{uuid.uuid4().hex[:8]}@{Config.COMPANY_DOMAIN}"
        
        # ICS 형식으로 생성 (개선된 버전)
        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//AI Interview System//Interview Schedule//KR
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VTIMEZONE
TZID:Asia/Seoul
BEGIN:STANDARD
DTSTART:19701101T000000
TZOFFSETFROM:+0900
TZOFFSETTO:+0900
TZNAME:KST
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:{event_uid}
DTSTART;TZID=Asia/Seoul:{utc_start}
DTEND;TZID=Asia/Seoul:{utc_end}
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:면접 - {request.position_name}
DESCRIPTION:📋 면접 정보\\n\\n• 포지션: {request.position_name}\\n• 면접자: {request.candidate_name}\\n• 면접관: {interviewer_info['name']} ({interviewer_info['department']})\\n• 소요시간: {request.selected_slot.duration}분\\n\\n⏰ 면접 10분 전까지 도착해주세요.\\n📧 문의: hr@{Config.COMPANY_DOMAIN}
LOCATION:회사 면접실
ORGANIZER;CN={interviewer_info['name']}:mailto:{interviewer_email}
ATTENDEE;CN={request.candidate_name};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{request.candidate_email}
ATTENDEE;CN={interviewer_info['name']};ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED:mailto:{interviewer_email}
STATUS:CONFIRMED
TRANSP:OPAQUE
PRIORITY:5
CLASS:PUBLIC
BEGIN:VALARM
TRIGGER:-PT30M
ACTION:DISPLAY
DESCRIPTION:면접 30분 전 알림 - {request.position_name}
END:VALARM
BEGIN:VALARM
TRIGGER:-PT10M
ACTION:DISPLAY
DESCRIPTION:면접 10분 전 알림 - 준비해주세요!
END:VALARM
END:VEVENT
END:VCALENDAR"""
        
        return ics_content
        
    except Exception as e:
        print(f"캘린더 초대장 생성 실패: {e}")
        return None

def format_duration_korean(minutes: int) -> str:
    """소요시간을 한국어로 포맷"""
    if minutes < 60:
        return f"{minutes}분"
    else:
        hours = minutes // 60
        remaining_minutes = minutes % 60
        if remaining_minutes == 0:
            return f"{hours}시간"
        else:
            return f"{hours}시간 {remaining_minutes}분"
        
def normalize_text(text: str) -> str:
    """
    문자열을 비교하기 쉽게 정규화합니다.
    (공백 제거, 소문자 변환, 특수문자 제거)
    예: '홍 길 동 ' → '홍길동'
    """
    if not text:
        return ""
    text = str(text).strip().lower()
    # 한글 이름 등은 소문자 변환만 적용하고 특수문자 제거
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'[^a-z0-9가-힣@._-]', '', text)
    return text

def parse_proposed_slots(raw_slots: str):
    """
    구글 시트에 저장된 제안 일정 문자열을 파싱하여 구조화된 리스트로 변환합니다.
    예: "2025-10-20 14:00(30분), 2025-10-21 10:00(60분)"
        → [{'date': '2025-10-20', 'time': '14:00', 'duration': 30}, ...]
    """
    if not raw_slots:
        return []
    
    slots = []
    try:
        parts = re.split(r'[,;/\n]+', raw_slots)
        for part in parts:
            part = part.strip()
            if not part:
                continue

            match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*\(?(\d+)?', part)
            if match:
                date_str = match.group(1)
                time_str = match.group(2)
                duration = int(match.group(3)) if match.group(3) else 30
                slots.append({
                    "date": date_str,
                    "time": time_str,
                    "duration": duration
                })
    except Exception:
        pass

    return slots
        
def normalize_request_id(request_id: str) -> str:
    """요청 ID 정규화 - 항상 8자리만 반환"""
    if not request_id:
        return ""
    
    # "..." 제거
    clean_id = request_id.replace('...', '').strip()
    
    # 8자리만 추출
    return clean_id[:8] if len(clean_id) >= 8 else clean_id

def generate_request_id() -> str:
    """8자리 요청 ID 생성"""
    import uuid
    return str(uuid.uuid4()).replace('-', '')[:8]


def get_business_days_between(start_date: str, end_date: str) -> int:
    """두 날짜 사이의 영업일 수 계산"""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        business_days = 0
        current_date = start
        
        while current_date <= end:
            if current_date.weekday() < 5:  # 월-금
                business_days += 1
            current_date += timedelta(days=1)
        
        return business_days
    except:
        return 0

def is_business_hour(time_str: str) -> bool:
    """업무시간 여부 확인 (9:00-18:00)"""
    try:
        time_obj = datetime.strptime(time_str, '%H:%M').time()
        business_start = datetime.strptime('09:00', '%H:%M').time()
        business_end = datetime.strptime('18:00', '%H:%M').time()
        
        return business_start <= time_obj <= business_end
    except:
        return False
