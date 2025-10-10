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

# utils.py - validate_email 함수 수정
def validate_email(email: str) -> bool:
    """이메일 유효성 검사"""
    import re
    
    # 기존 정규식에 오타가 있었음 (마지막에 \\$ 대신 \$)
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\$'
    
    result = re.match(pattern, email) is not None
    
    # 디버깅을 위한 출력 (임시)
    print(f"🔍 이메일 검증: {email} -> {'✅ 유효' if result else '❌ 무효'}")
    
    return result

def load_employee_data():
    """조직도 엑셀 파일에서 직원 데이터 로드"""
    try:
        if not os.path.exists(Config.EMPLOYEE_DATA_PATH):
            print(f"조직도 파일을 찾을 수 없습니다: {Config.EMPLOYEE_DATA_PATH}")
            return []
        
        # 엑셀 파일 읽기
        df = pd.read_excel(Config.EMPLOYEE_DATA_PATH)
        
        # 필요한 컬럼: 사번, 이름, 부서, 이메일
        # 컬럼명은 실제 엑셀 파일에 맞게 조정 필요
        required_columns = ['사번', '이름', '부서', '이메일']
        
        # 영문 컬럼명으로도 시도
        if not all(col in df.columns for col in required_columns):
            required_columns = ['employee_id', 'name', 'department', 'email']
        
        if not all(col in df.columns for col in required_columns):
            print("필요한 컬럼을 찾을 수 없습니다. 컬럼명을 확인해주세요.")
            return []
        
        employees = []
        for _, row in df.iterrows():
            if pd.notna(row[required_columns[0]]):  # 사번이 있는 경우만
                employee = {
                    'employee_id': str(row[required_columns[0]]),
                    'name': str(row[required_columns[1]]),
                    'department': str(row[required_columns[2]]),
                    'email': str(row[required_columns[3]]) if pd.notna(row[required_columns[3]]) else f"{row[required_columns[0]]}@{Config.COMPANY_DOMAIN}"
                }
                employees.append(employee)
        
        return employees
        
    except Exception as e:
        print(f"조직도 데이터 로드 실패: {e}")
        return []

def get_employee_email(employee_id: str) -> str:
    """사번으로 직원 이메일 조회"""
    employees = load_employee_data()
    
    for emp in employees:
        if emp['employee_id'] == employee_id:
            return emp['email']
    
    # 조직도에서 찾지 못한 경우 기본 이메일 형식 사용
    return f"{employee_id.lower()}@{Config.COMPANY_DOMAIN}"

def get_employee_info(employee_id: str) -> dict:
    """사번으로 직원 정보 조회"""
    employees = load_employee_data()
    
    for emp in employees:
        if emp['employee_id'] == employee_id:
            return emp
    
    # 기본 정보 반환
    return {
        'employee_id': employee_id,
        'name': employee_id,
        'department': '미확인',
        'email': f"{employee_id.lower()}@{Config.COMPANY_DOMAIN}"
    }

