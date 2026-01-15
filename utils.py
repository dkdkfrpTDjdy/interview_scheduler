from datetime import datetime, timedelta
from typing import List, Dict, Set, Any, Optional
import calendar
import pandas as pd
from config import Config
import os
from collections import defaultdict
from models import InterviewRequest
import re
import uuid

# -----------------------------
# 1) 공통 정규화 유틸
# -----------------------------
def normalize_employee_id(emp_id: Any) -> str:
    """
    사번을 어떤 형태로 들어와도 안정적으로 문자열 ID로 변환
    - 223286.0 / 223286 / '223286 ' / '223-286' 등 방어
    """
    if emp_id is None or (isinstance(emp_id, float) and pd.isna(emp_id)):
        return ""

    s = str(emp_id).strip()

    # 엑셀에서 숫자형으로 읽혀 "223286.0" 되는 케이스 제거
    # (뒤에 .0만 제거 / 소수점이 실제로 있는 값은 거의 없으니 이 방식이 안전)
    if re.match(r"^\d+\.0$", s):
        s = s[:-2]

    # 만약 사번에 문자가 섞일 가능성이 있으면 아래를 완화해야 함.
    s = re.sub(r"\D", "", s)

    return s


def pick_first_existing_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """
    df에 실제로 존재하는 컬럼명 중 첫 번째를 반환 (대소문자/공백 변형도 대응)
    """
    if df is None or df.empty:
        return None

    # 원본 컬럼명 매핑 (strip 한 버전)
    col_map = {str(c).strip(): c for c in df.columns}

    # 1) 완전 일치(공백제거/strip)
    for cand in candidates:
        cand_stripped = str(cand).strip()
        if cand_stripped in col_map:
            return col_map[cand_stripped]

    # 2) 느슨한 매칭: 공백 제거 후 비교
    normalized_cols = {re.sub(r"\s+", "", str(c)): c for c in df.columns}
    for cand in candidates:
        key = re.sub(r"\s+", "", str(cand))
        if key in normalized_cols:
            return normalized_cols[key]

    return None



def group_requests_by_interviewer_and_position(requests: List[InterviewRequest]) -> Dict[str, List[InterviewRequest]]:
    """
    🔧 개선된 그룹핑: 면접관 + 포지션 조합으로 면접 요청 그룹핑
    
    문제점: 기존 코드는 동일한 면접자가 여러 그룹에 포함되어 중복 발송
    해결책: 면접관 ID와 공고명을 정확히 조합하여 유일한 그룹 생성
    
    Args:
        requests: 면접 요청 리스트
    
    Returns:
        {
            "223286,223287_IT혁신팀": [request1, request2, request3],
            "223286_데이터분석가": [request4],
        }
    """
    groups = defaultdict(list)
    
    for request in requests:
        # ✅ 면접관 ID 정규화 및 정렬 (일관성 보장)
        interviewer_ids = sorted([id.strip() for id in request.interviewer_id.split(',')])
        interviewer_key = ",".join(interviewer_ids)
        
        # ✅ 그룹 키 생성: "면접관ID들_공고명"
        # 공고명도 정규화하여 공백 문제 방지
        position_normalized = request.position_name.strip().replace(" ", "")
        group_key = f"{interviewer_key}_{position_normalized}"
        
        groups[group_key].append(request)
    
    # ✅ 로그 출력으로 그룹핑 결과 확인
    print(f"📊 그룹핑 결과: 총 {len(groups)}개 그룹 생성")
    for group_key, group_requests in groups.items():
        print(f"  - {group_key}: {len(group_requests)}명 면접자")
    
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

# -----------------------------
# 2) 조직도 로드 (자동 컬럼 매핑 + 사번 정규화)
# -----------------------------
def load_employee_data() -> List[Dict[str, str]]:
    """
    조직도 엑셀 파일에서 직원 데이터 로드 (직책/직급/직위 등 자동 매핑 + 사번 .0 방어)
    필수: 사번, 성명(이름)만 있으면 최소 동작
    """
    try:
        path = Config.EMPLOYEE_DATA_PATH
        if not os.path.exists(path):
            print(f"조직도 파일을 찾을 수 없습니다: {path}")
            return []

        ext = os.path.splitext(path)[-1].lower()

        # ✅ dtype 강제는 '사번' 컬럼명이 정확히 있을 때만 먹혀서
        #    여기선 전체를 문자열로 읽고, 우리가 normalize로 처리하는 편이 더 안전함.
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(path, dtype=str)  # 전체 str로
        elif ext == ".csv":
            df = pd.read_csv(path, dtype=str)
        else:
            print(f"지원하지 않는 파일 형식: {ext}")
            return []

        if df is None or df.empty:
            print("조직도 파일이 비어있습니다.")
            return []

        # ✅ 컬럼 자동 탐지
        col_emp_id = pick_first_existing_column(df, ["사번", "사원번호", "직원번호", "EMP_ID", "employee_id", "ID"])
        col_name   = pick_first_existing_column(df, ["성명", "이름", "Name", "name"])
        col_div    = pick_first_existing_column(df, ["부문", "Division", "division"])
        col_hq     = pick_first_existing_column(df, ["본부", "Headquarters", "headquarters"])
        col_dept   = pick_first_existing_column(df, ["부서", "Department", "dept", "department", "팀", "Team"])
        col_pos    = pick_first_existing_column(df, ["직책", "직급", "직위", "Position", "position", "Title", "title"])
        col_email  = pick_first_existing_column(df, ["이메일", "메일", "Email", "email", "E-mail", "e-mail"])

        if not col_emp_id or not col_name:
            print(f"⚠️ 조직도 컬럼 탐지 실패: 사번/이름 컬럼이 필요합니다.")
            print(f"현재 컬럼: {list(df.columns)}")
            return []

        employees: List[Dict[str, str]] = []

        for _, row in df.iterrows():
            raw_id = row.get(col_emp_id, "")
            employee_id = normalize_employee_id(raw_id)
            if not employee_id:
                continue

            name = str(row.get(col_name, "") or "").strip()

            division = str(row.get(col_div, "") or "").strip() if col_div else ""
            headquarters = str(row.get(col_hq, "") or "").strip() if col_hq else ""
            department = str(row.get(col_dept, "") or "").strip() if col_dept else ""
            position = str(row.get(col_pos, "") or "").strip() if col_pos else ""

            email = ""
            if col_email:
                email = str(row.get(col_email, "") or "").strip()

            # 이메일이 없으면 기본 포맷 생성 (사번@도메인)
            if not email:
                email = f"{employee_id.lower()}@{Config.COMPANY_DOMAIN}"

            employees.append({
                "employee_id": employee_id,
                "name": name,
                "division": division,
                "headquarters": headquarters,
                "department": department,
                "position": position,
                "email": email,
            })

        print(f"조직도 데이터 로드 성공: {len(employees)}명")
        return employees

    except Exception as e:
        print(f"조직도 데이터 로드 실패: {e}")
        return []


# -----------------------------
# 3) 조회 함수들도 사번 정규화 통일
# -----------------------------
def get_employee_info(employee_id: str) -> dict:
    employees = load_employee_data()
    norm_id = normalize_employee_id(employee_id)

    for emp in employees:
        if normalize_employee_id(emp.get("employee_id")) == norm_id:
            return emp

    print(f"Warning: 사번 {employee_id}에 대한 정보를 조직도에서 찾을 수 없습니다.")
    return {
        "employee_id": norm_id or str(employee_id),
        "name": norm_id or str(employee_id),
        "division": "미확인",
        "headquarters": "미확인",
        "department": "미확인",
        "position": "",
        "email": f"{(norm_id or str(employee_id)).lower()}@{Config.COMPANY_DOMAIN}",
    }


def get_employee_email(employee_id: str) -> str:
    info = get_employee_info(employee_id)
    return info.get("email") or f"{normalize_employee_id(employee_id).lower()}@{Config.COMPANY_DOMAIN}"


def format_employee_greeting(employee_id: str) -> str:
    """
    "홍길동 팀장님" / "홍길동님"
    """
    try:
        info = get_employee_info(employee_id)
        name = (info.get("name") or f"사원{normalize_employee_id(employee_id)}").strip()
        position = (info.get("position") or "").strip()

        if position:
            return f"{name} {position}님"
        return f"{name}님"
    except Exception as e:
        print(f"직원 인사말 포맷팅 실패: {e}")
        return f"사원{normalize_employee_id(employee_id)}님"

def get_employee_info_with_position(employee_id: str) -> dict:
    """
    ✅ 직책 정보 포함한 사원 정보 조회 (별칭 함수)
    기존 get_employee_info와 동일하지만 명시적으로 직책 정보를 원할 때 사용
    """
    return get_employee_info(employee_id)


# ✅ 여러 면접관 처리용 함수 추가
def format_multiple_interviewers_greeting(interviewer_ids: str) -> str:
    """
    복수 면접관 인사말 포맷팅
    
    Args:
        interviewer_ids: "208081,216825" 형태의 쉼표 구분 면접관 ID
        
    Returns:
        str: "강미영 팀장, 강민석 팀장" 형태
    """
    try:
        ids = [id.strip() for id in interviewer_ids.split(',')]
        greetings = []
        
        for interviewer_id in ids:
            greeting = format_employee_greeting(interviewer_id)
            # "님"을 제거하고 직책만 남김 (복수일 때는 님 제거)
            if greeting.endswith('님'):
                greeting = greeting[:-1]  # "홍길동님" → "홍길동"
            greetings.append(greeting)
        
        return ", ".join(greetings)
        
    except Exception as e:
        print(f"복수 면접관 인사말 포맷팅 실패: {e}")
        return "면접관"

def get_employee_department_info(employee_id: str) -> str:
    """
    ✅ 직원 부서 정보 상세 조회
    
    Returns:
        str: "영업지원본부 지원3팀" 형태
    """
    try:
        employee_info = get_employee_info(employee_id)
        
        parts = []
        if employee_info.get('division'):
            parts.append(employee_info['division'])
        if employee_info.get('headquarters'):
            parts.append(employee_info['headquarters'])
        if employee_info.get('department'):
            parts.append(employee_info['department'])
        
        return " ".join(parts) if parts else "미확인"
        
    except Exception as e:
        print(f"부서 정보 조회 실패: {e}")
        return "미확인"

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
        primary_interviewer_id = str(request.interviewer_id).split(",")[0].strip()
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

import re

# ✅ 개선된 코드
def parse_proposed_slots(raw_slots: str) -> List[dict]:
    """
    제안 일정 파싱 (다양한 형식 지원)
    
    지원 형식:
    - "2025-01-15 14:00(30분)"
    - "2025-01-15 14:00~14:30"
    - "2025-01-15 14:00"
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not raw_slots:
        return []
    
    slots = []
    try:
        # 구분자로 분할
        parts = re.split(r'[|,;/\n\r]+', str(raw_slots))
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 패턴 1: "2025-01-15 14:00(30분)"
            match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*\(?(\d+)\s*분\)?$', part)
            if match:
                date_str, time_str, duration_str = match.groups()
                slots.append({
                    "date": date_str,
                    "time": time_str,
                    "duration": int(duration_str)
                })
                logger.debug(f"✅ 패턴1 매칭: {part}")
                continue
            
            # 패턴 2: "2025-01-15 14:00~14:30"
            match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})~(\d{2}:\d{2})', part)
            if match:
                date_str, start_time, end_time = match.groups()
                
                # 시간 차이 계산
                try:
                    from datetime import datetime
                    start = datetime.strptime(start_time, '%H:%M')
                    end = datetime.strptime(end_time, '%H:%M')
                    duration = int((end - start).total_seconds() / 60)
                except:
                    duration = 30
                
                slots.append({
                    "date": date_str,
                    "time": start_time,
                    "duration": duration
                })
                logger.debug(f"✅ 패턴2 매칭: {part}")
                continue
            
            # 패턴 3: "2025-01-15 14:00" (괄호 없음)
            match = re.match(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})', part)
            if match:
                date_str, time_str = match.groups()
                slots.append({
                    "date": date_str,
                    "time": time_str,
                    "duration": 30  # 기본값
                })
                logger.debug(f"✅ 패턴3 매칭: {part}")
                continue
            
            # 매칭 실패
            logger.warning(f"⚠️ 파싱 실패: {part}")
                
    except Exception as e:
        logger.error(f"❌ 제안 일정 파싱 오류: {e}")
    
    logger.info(f"📅 최종 파싱 결과: {len(slots)}개 슬롯")
    return slots

        
def normalize_request_id(request_id: str) -> str:
    """
    🔧 통일된 ID 정규화
    
    규칙:
    1. 공백 제거
    2. 대문자 변환
    3. 특수문자 제거
    4. 원본 길이 유지 (8자리 자르기 제거)
    
    예시:
    - "TL2AUIKZ" → "TL2AUIKZ"
    - "tl2auikz" → "TL2AUIKZ"
    - "TL2A UIKZ" → "TL2AUIKZ"
    - "TL2AUIKZ..." → "TL2AUIKZ"
    """
    if not request_id:
        return ""
    
    # 공백 및 특수문자 제거, 대문자 변환
    clean_id = re.sub(r'[^A-Z0-9]', '', str(request_id).strip().upper())
    
    # ✅ 원본 ID 그대로 반환 (8자리 제한 제거)
    return clean_id

def generate_request_id() -> str:
    """
    8자리 요청 ID 생성 (대문자+숫자만 사용)
    
    예시: "TL2AUIKZ", "9JO1ZIPS"
    """
    import string
    import random
    
    # ✅ 대문자 + 숫자만 사용 (소문자 제외)
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=8))

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





