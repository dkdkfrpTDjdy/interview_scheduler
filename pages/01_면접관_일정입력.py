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
        <p style="font-size: 0.95rem; opacity: 0.9; margin: 0;">사번을 입력하여 본인의 면접 요청을 확인하세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("interviewer_login"):
            st.subheader("사번 입력")
            
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
            </div>
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 15px;">
                <p style="margin: 0; color: #1565c0;"><strong>📞 문의:</strong> <a href="mailto:hr@ajnet.co.kr">hr@ajnet.co.kr</a></p>
            </div>
        </div>
        """, unsafe_allow_html=True)

def find_pending_requests(employee_id: str):
    """면접관의 대기 중인 요청 찾기"""
    try:
        # 정확한 사번 매칭 또는 이름/부서로 검색
        all_requests = db.get_all_requests()
        pending_requests = []
        
        for request in all_requests:
            # 직접 매칭
            if request.interviewer_id == employee_id:
                if request.status == Config.Status.PENDING_INTERVIEWER:
                    pending_requests.append(request)
            else:
                # 이름이나 부서로 검색한 경우
                interviewer_info = get_employee_info(request.interviewer_id)
                if (employee_id.lower() in interviewer_info['name'].lower() or 
                    employee_id.lower() in interviewer_info['department'].lower()):
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
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 25px; border-radius: 12px; margin: 20px 0;">
            <h2 style="color: #1565c0; margin: 0; display: flex; align-items: center;">
                <span style="margin-right: 15px;">👋</span> 안녕하세요, {interviewer_info['name']}님!
            </h2>
            <p style="color: #1976d2; margin: 8px 0 0 0; font-size: 1rem;">({interviewer_info['department']})</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        if st.button("🚪 로그아웃", use_container_width=True):
            # 세션 상태 초기화
            for key in ['authenticated_interviewer', 'interviewer_info', 'pending_requests']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # 대기 중인 요청 표시
    if not pending_requests:
        st.markdown("""
        <div style="text-align: center; padding: 60px; background-color: #f8f9fa; border-radius: 15px; margin: 30px 0;">
            <div style="font-size: 4rem; margin-bottom: 20px; color: #6c757d;">📭</div>
            <h3 style="color: #6c757d; margin: 0 0 15px 0;">처리할 면접 요청이 없습니다</h3>
            <p style="color: #6c757d; font-size: 1.1rem;">새로운 면접 요청이 오면 여기에 표시됩니다.</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    st.subheader(f"📋 대기 중인 면접 요청 ({len(pending_requests)}건)")
    
    # 각 요청에 대해 처리
    for i, request in enumerate(pending_requests):
        with st.expander(f"📅 {request.position_name} - {request.candidate_name} ({request.created_at.strftime('%m/%d')})", expanded=len(pending_requests)==1):
            show_request_detail(request, i)

def show_request_detail(request, index):
    """개별 면접 요청 상세 정보 및 처리"""
    
    # ✅ 면접 정보 표시 (누락된 부분 추가)
    st.markdown(f"""
    <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid #0078d4; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,120,212,0.1);">
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #0078d4; width: 120px;">포지션</td>
                <td style="padding: 10px 0; color: #333; font-size: 1.1rem; font-weight: bold;">{request.position_name}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #0078d4;">면접자</td>
                <td style="padding: 10px 0; color: #333;">{request.candidate_name}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #0078d4;">이메일</td>
                <td style="padding: 10px 0; color: #333; font-size: 0.9rem;">{request.candidate_email}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #0078d4;">요청일</td>
                <td style="padding: 10px 0; color: #333;">{request.created_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    # ✅ 인사팀 제안 일시 표시 (Streamlit 테이블 사용)
    if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
        st.write("**⭐ 인사팀 제안 희망일시**")
        
        # DataFrame으로 변환
        slots_data = []
        for i, datetime_slot in enumerate(request.preferred_datetime_slots, 1):
            if "면접관선택" in datetime_slot:
                date_part = datetime_slot.split(' ')[0]
                time_display = "시간 선택 필요"
                status = "⚠️ 선택"
            else:
                date_part, time_part = datetime_slot.split(' ')
                time_display = time_part
                status = "✅ 고정"
            
            slots_data.append({
                "번호": i,
                "날짜": format_date_korean(date_part),
                "시간": time_display,
                "상태": status
            })
        
        # Streamlit 테이블로 표시
        st.dataframe(pd.DataFrame(slots_data), use_container_width=True, hide_index=True)
    
    # 🔧 수정: 일정 입력 폼 (폼 밖에서 상태 관리)
    st.write("**⏰ 가능한 면접 일정을 선택해주세요**")
    
    # 세션 상태로 선택 상태 관리
    if f'selected_slots_{index}' not in st.session_state:
        st.session_state[f'selected_slots_{index}'] = {}
    
    selected_slots = []
    
    if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
        for i, datetime_slot in enumerate(request.preferred_datetime_slots):
            st.markdown(f"### 📅 옵션 {i+1}")
            
            if "면접관선택" in datetime_slot:
                # 면접관이 시간을 직접 선택해야 하는 경우
                date_part = datetime_slot.split(' ')[0]
                
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    # 체크박스 상태를 세션에서 관리
                    checkbox_key = f"slot_{index}_{i}"
                    is_selected = st.checkbox(
                        f"📅 {format_date_korean(date_part)} (시간 선택 필요)",
                        key=checkbox_key,
                        help="이 날짜를 선택하고 시간을 지정해주세요"
                    )
                    
                    # 세션 상태 업데이트
                    st.session_state[f'selected_slots_{index}'][f'slot_{i}'] = is_selected
                
                with col2:
                    # 체크박스 상태에 따라 disabled 설정
                    selected_time = st.selectbox(
                        "⏰ 시간 선택",
                        options=["선택안함"] + Config.TIME_SLOTS,
                        key=f"time_select_{index}_{i}",
                        disabled=not is_selected,  # 실시간 반영
                        help="면접 시작 시간을 선택해주세요"
                    )
                
                with col3:
                    duration = st.selectbox(
                        "⏱️ 소요시간",
                        options=[30, 60, 90, 120],
                        index=1,
                        format_func=lambda x: f"{x}분",
                        key=f"duration_{index}_{i}",
                        disabled=not is_selected,  # 실시간 반영
                        help="예상 면접 소요 시간"
                    )
                
                # 선택된 슬롯 추가
                if is_selected and selected_time != "선택안함":
                    selected_slots.append(InterviewSlot(date_part, selected_time, duration))
                    
            else:
                # 시간이 고정된 경우
                date_part, time_part = datetime_slot.split(' ')
                
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    checkbox_key = f"slot_{index}_{i}"
                    is_selected = st.checkbox(
                        f"📅 {format_date_korean(date_part)} {time_part}",
                        key=checkbox_key,
                        help="이 일정이 가능하면 선택해주세요"
                    )
                    
                    # 세션 상태 업데이트
                    st.session_state[f'selected_slots_{index}'][f'slot_{i}'] = is_selected
                
                with col2:
                    st.markdown(f"**⏰ {time_part}** (고정)")
                
                with col3:
                    duration = st.selectbox(
                        "⏱️ 소요시간",
                        options=[30, 60, 90, 120],
                        index=1,
                        format_func=lambda x: f"{x}분",
                        key=f"duration_{index}_{i}",
                        disabled=not is_selected  # 실시간 반영
                    )
                
                # 선택된 슬롯 추가
                if is_selected:
                    selected_slots.append(InterviewSlot(date_part, time_part, duration))
    
    # 🔧 폼은 제출 버튼만 포함
    with st.form(f"interviewer_schedule_{index}"):
        # 선택된 일정 미리보기
        if selected_slots:
            st.write("**✅ 선택된 일정:**")
            
            # ✅ 선택된 일정을 표로 표시
            preview_data = []
            for i, slot in enumerate(selected_slots, 1):
                preview_data.append({
                    "번호": i,
                    "날짜": format_date_korean(slot.date),
                    "시간": slot.time,
                    "소요시간": f"{slot.duration}분"
                })
            
            st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)
        else:
            st.info("💡 위에서 가능한 일정을 선택해주세요.")
        
        # 제출 버튼
        submitted = st.form_submit_button(
            "📧 면접자에게 일정 전송", 
            use_container_width=True, 
            type="primary",
            disabled=len(selected_slots) == 0  # 선택된 슬롯이 없으면 비활성화
        )
        
        if submitted:
            if not selected_slots:
                st.error("❌ 최소 1개 이상의 면접 일정을 선택해주세요.")
            else:
                # 요청 업데이트
                request.available_slots = selected_slots
                request.status = Config.Status.PENDING_CANDIDATE
                request.updated_at = datetime.now()
                
                db.save_interview_request(request)
                db.update_google_sheet(request)
                
                # 면접자에게 이메일 발송
                if email_service.send_candidate_invitation(request):
                    st.success("✅ 면접 일정이 면접자에게 전송되었습니다!")
                    
                    # 세션 상태에서 처리된 요청 제거
                    st.session_state.pending_requests = [r for r in st.session_state.pending_requests if r.id != request.id]
                    
                    # 선택 상태 초기화
                    if f'selected_slots_{index}' in st.session_state:
                        del st.session_state[f'selected_slots_{index}']
                    
                    # 페이지 새로고침
                    st.rerun()
                else:
                    st.error("❌ 면접 일정은 저장되었지만 이메일 발송에 실패했습니다.")

if __name__ == "__main__":
    main()
