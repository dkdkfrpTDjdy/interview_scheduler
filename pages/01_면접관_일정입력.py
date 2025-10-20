import streamlit as st
import pandas as pd  # ✅ 누락된 import 추가
import os

# 앱 구분 로직
def is_interviewer_app():
    """현재 앱이 면접관용인지 확인"""
    try:
        # URL이나 환경변수로 앱 구분
        if "candidate-app" in st.get_option("server.headless"):
            return False
        return True
    except:
        # 환경변수로 구분
        return os.getenv("APP_TYPE", "interviewer") == "interviewer"

# 페이지 접근 제어
if not is_interviewer_app():
    st.error("❌ 접근 권한이 없습니다.")
    st.info("면접관 전용 페이지입니다. 면접자용 앱을 이용해주세요.")
    st.stop()

from datetime import datetime
import sys

# 상위 디렉터리의 모듈들을 import하기 위해 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager
from email_service import EmailService
from models import InterviewSlot
from config import Config
from utils import format_date_korean, get_employee_info

# 페이지 설정
st.set_page_config(
    page_title="면접관 일정 입력 - AI 면접 시스템",
    page_icon="👨‍💼",
    layout="wide"
)

# 전역 객체 초기화
@st.cache_resource
def init_services():
    db = DatabaseManager()
    email_service = EmailService()
    return db, email_service

db, email_service = init_services()

def main():
    st.title("👨‍💼 면접관 일정 입력")
    st.caption("면접관 전용 페이지")
    
    # 🔧 수정: 사번 입력 방식으로 변경
    if 'authenticated_interviewer' not in st.session_state:
        show_login_form()
    else:
        show_interviewer_dashboard()

# 중복 일정 감지 (예시)
def find_overlapping_slots(all_requests):
    slot_counts = {}
    for req in all_requests:
        for slot in req.available_slots:
            key = f"{slot.date}_{slot.time}"
            slot_counts[key] = slot_counts.get(key, 0) + 1
    
    # 2명 이상 선택한 일정만 반환
    return [k for k, v in slot_counts.items() if v >= 2]

def show_login_form():
    """면접관 사번 입력 폼"""
    st.markdown("""
    <div style="background-color: #1A1A1A;
                color: white;
                padding: 10px;
                border-radius: 12px;
                text-align: center;
                margin: 15px 0;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);">
        <div style="font-size: 2rem; margin-bottom: 10px;">🔐</div>
        <h1 style="margin: 0 0 10px 0; font-size: 1.5rem; font-weight: 400;">면접관 인증</h1>
        <p style="font-size: 0.95rem; opacity: 0.9; margin: 0;">면접 요청을 확인하세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("interviewer_login"):
            
            employee_id = st.text_input(
                label="사번 입력",
                placeholder="예: 223286"
            )
            
            submitted = st.form_submit_button("🔍 면접 요청 확인", type="primary")
            
            if submitted:
                if not employee_id.strip():
                    st.error("사번을 입력해주세요.")
                else:
                    # ✅ 면접관 정보 확인 로직 개선
                    interviewer_info = get_employee_info(employee_id)
                    
                    # 정확한 매칭 또는 부분 매칭 확인
                    is_valid = (
                        interviewer_info['employee_id'] == employee_id 
                    )
                    
                    if is_valid:
                        # 해당 면접관의 대기 중인 요청 찾기
                        pending_requests = find_pending_requests(employee_id)
                        
                        if pending_requests:
                            st.session_state.authenticated_interviewer = employee_id
                            st.session_state.interviewer_info = interviewer_info
                            st.session_state.pending_requests = pending_requests
                            st.rerun()
                        else:
                            st.warning("현재 처리할 면접 요청이 없습니다.")
                    else:
                        st.error("등록되지 않은 사번입니다. 인사팀에 문의해주세요.")
    
    # 도움말
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="background-color: #f8f9fa; padding: 25px; border-radius: 12px; text-align: center; border: 1px solid #dee2e6;">
            <h4 style="color: #495057; margin-top: 0;">이용 안내</h4>
            <div style="text-align: left; margin: 15px 0;">
                <p style="margin: 8px 0; color: #6c757d;">• <strong>사번</strong>을 정확히 입력하세요</p>
                <p style="margin: 8px 0; color: #6c757d;">• 예정된 면접이 표시됩니다</p>
            </div>
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 15px;">
                <p style="margin: 0; color: #1565c0;"><strong>📞 기타 문의:</strong> <a href="mailto:hr@ajnet.co.kr">hr@ajnet.co.kr</a></p>
            </div>
        </div>
        """, unsafe_allow_html=True)

def find_pending_requests(employee_id: str):
    """면접관의 대기 중인 요청 찾기 (복수 면접관 지원)"""
    try:
        all_requests = db.get_all_requests()
        pending_requests = []
        
        for request in all_requests:
            # ✅ 복수 면접관 ID 처리
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            
            # 현재 로그인한 면접관 ID가 포함되어 있는지 확인
            if employee_id in interviewer_ids:
                if request.status == Config.Status.PENDING_INTERVIEWER:
                    pending_requests.append(request)
        
        return pending_requests
    except Exception as e:
        st.error(f"요청 조회 중 오류가 발생했습니다: {e}")
        return []

def show_interviewer_dashboard():
    """면접관 대시보드"""
    interviewer_info = st.session_state.interviewer_info
    pending_requests = st.session_state.pending_requests

    # 헤더
    # col1, _ = st.columns([3, 1])  # col2 제거

    # with col1:
    #     st.markdown(f"""
    #     <div style="margin: 20px 0;">
    #         <h2 style="color: #1A1A1A; margin: 0; display: flex; align-items: center;">
    #             <span style="margin-right: 10px;">👋</span> 안녕하세요, {interviewer_info['name']}님!
    #         </h2>
    #     </div>
    #     """, unsafe_allow_html=True)

    # 대기 중인 요청 표시
    if not pending_requests:
        st.markdown("""
        <div style="text-align: center; margin: 30px 0;">
            <h3 style="color: #1A1A1A; margin: 0 0 15px 0;">모든 면접 일정을 처리하였습니다</h3>
        </div>
        """, unsafe_allow_html=True)
        return

    st.subheader(f"📋 {interviewer_info['name']} ({interviewer_info['department']}) 님의 대기 중인 면접 요청 ({len(pending_requests)}건)")

    # 각 요청에 대해 처리
    for i, request in enumerate(pending_requests):
        with st.expander(f"📅 {request.position_name} - {request.candidate_name}", expanded=len(pending_requests) == 1):
            show_request_detail(request, i)

def show_request_detail(request, index):
    """개별 면접 요청 상세 정보 및 처리 - 시간 범위 입력"""
    
    # 면접 정보 표시
    st.markdown(f"""
    <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid #0078d4; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,120,212,0.1);">
        <table style="width: 100%; border-collapse: collapse; text-align: center;">
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #1A1A1A; width: 120px;">공고명</td>
                <td style="padding: 10px 0; color: #333;">{request.position_name}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #1A1A1A;">면접자</td>
                <td style="padding: 10px 0; color: #333;">{request.candidate_name}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #1A1A1A;">이메일</td>
                <td style="padding: 10px 0; color: #333;">{request.candidate_email}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #1A1A1A;">요청일</td>
                <td style="padding: 10px 0; color: #333;">{request.created_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

    st.write("**아래에서 면접 가능한 시간대를 입력해 주세요 (30분 단위로 자동 분할됩니다)**")
    
    # 폼과 일정 선택을 함께 처리
    with st.form(f"interviewer_schedule_{index}"):
        selected_time_ranges = []
        
        if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
            for i, datetime_slot in enumerate(request.preferred_datetime_slots):
                st.markdown(f"**📅 희망 날짜 {i+1}**")
                
                # 시간 범위 입력
                date_part = datetime_slot.split(' ')[0]
                
                col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 1])
                
                with col1:
                    is_selected = st.checkbox(
                        f"{format_date_korean(date_part)}",
                        key=f"date_check_{index}_{i}",
                        help="해당 날짜가 가능하면 선택해주세요"
                    )
                
                with col2:
                    start_time = st.selectbox(
                        "시작 시간",
                        options=["선택안함"] + Config.TIME_SLOTS,
                        key=f"start_time_{index}_{i}",
                        help="면접 가능 시작 시간"
                    )
                
                with col3:
                    end_time = st.selectbox(
                        "종료 시간",
                        options=["선택안함"] + Config.TIME_SLOTS,
                        key=f"end_time_{index}_{i}",
                        help="면접 가능 종료 시간"
                    )
                
                with col4:
                    if is_selected and start_time != "선택안함" and end_time != "선택안함":
                        # 슬롯 개수 계산
                        start_hour = int(start_time.split(':')[0])
                        end_hour = int(end_time.split(':')[0])
                        slot_count = (end_hour - start_hour) * 2
                        st.markdown(f"<div style='margin-top:32px;color:#4caf50;font-weight:bold;'>{slot_count}개 슬롯</div>", unsafe_allow_html=True)
                
                # 선택된 시간 범위 추가
                if is_selected and start_time != "선택안함" and end_time != "선택안함":
                    # 시간 유효성 검사
                    start_hour = int(start_time.split(':')[0])
                    end_hour = int(end_time.split(':')[0])
                    
                    if start_hour < end_hour:
                        from models import TimeRange
                        time_range = TimeRange(
                            date=date_part,
                            start_time=start_time,
                            end_time=end_time
                        )
                        selected_time_ranges.append(time_range)
        
        # 선택된 시간대 미리보기
        if selected_time_ranges:
            st.write("**선택된 시간대:**")
            
            # 30분 단위로 분할된 슬롯 생성
            all_generated_slots = []
            for time_range in selected_time_ranges:
                slots = time_range.generate_30min_slots()
                all_generated_slots.extend(slots)
            
            preview_data = []
            for i, slot in enumerate(all_generated_slots, 1):
                preview_data.append({
                    "번호": i,
                    "날짜": format_date_korean(slot.date),
                    "시간": slot.time,
                    "소요시간": "30분"
                })
            
            st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)
            st.info(f"💡 총 {len(all_generated_slots)}개의 30분 단위 면접 슬롯이 생성됩니다.")
        else:
            st.info("💡 위에서 가능한 시간대를 선택해주세요.")

        # 버튼
        col1, col2, col3 = st.columns([6, 1, 1])
        
        with col3:
            submitted = st.form_submit_button("일정 확정", use_container_width=True)

        # 폼 제출 처리
        if submitted:
            if not selected_time_ranges:
                st.error("최소 1개 이상의 시간대를 선택해주세요.")
            else:
                try:
                    # 30분 단위 슬롯 생성
                    all_slots = []
                    for time_range in selected_time_ranges:
                        slots = time_range.generate_30min_slots()
                        all_slots.extend(slots)
                    
                    # 요청 업데이트
                    request.available_slots = all_slots
                    request.status = Config.Status.PENDING_CANDIDATE
                    request.updated_at = datetime.now()
                    
                    db.save_interview_request(request)
                    db.update_google_sheet(request)
                    
                    # 면접자에게 이메일 발송
                    if email_service.send_candidate_invitation(request):
                        st.success(f"✅ {len(all_slots)}개의 30분 단위 면접 슬롯이 면접자에게 전송되었습니다!")
                        
                        # 세션 상태에서 처리된 요청 제거
                        if 'pending_requests' in st.session_state:
                            st.session_state.pending_requests = [
                                r for r in st.session_state.pending_requests 
                                if r.id != request.id
                            ]
                        
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("❌ 면접 일정은 저장되었지만 이메일 발송에 실패했습니다.")
                        
                except Exception as e:
                    st.error(f"❌ 처리 중 오류가 발생했습니다: {str(e)}")

if __name__ == "__main__":
    main()
