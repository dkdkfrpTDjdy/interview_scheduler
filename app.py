import streamlit as st
import pandas as pd
from datetime import datetime
from urllib.parse import parse_qs
from database import DatabaseManager
from email_service import EmailService
from models import InterviewRequest, InterviewSlot
from config import Config
from utils import get_next_weekdays, format_date_korean, validate_email

# 페이지 설정
st.set_page_config(
    page_title="AI 면접 일정 조율 시스템",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 전역 객체 초기화
@st.cache_resource
def init_services():
    db = DatabaseManager()
    email_service = EmailService()
    return db, email_service

db, email_service = init_services()

def main():
    st.title("📅 AI 면접 일정 조율 시스템")
    
    # URL 파라미터 확인 (새로운 API 사용)
    query_params = st.query_params
    role = query_params.get('role', None)
    request_id = query_params.get('id', None)
    
    if role == 'interviewer' and request_id:
        show_interviewer_page(request_id)
    elif role == 'candidate' and request_id:
        show_candidate_page(request_id)
    else:
        show_admin_page()

def show_admin_page():
    """인사팀 관리자 페이지"""
    st.header("🏢 인사팀 관리 대시보드")
    
    # Outlook 연결 상태 확인
    with st.sidebar:
        st.subheader("🔧 시스템 상태")
        
        # 이메일 서비스 연결 테스트
        if st.button("📧 Outlook 연결 테스트"):
            test_result = email_service._create_smtp_connection()
            if test_result:
                test_result.quit()
                st.success("✅ Outlook 서버 연결 성공")
            else:
                st.error("❌ Outlook 서버 연결 실패")
                st.info("설정을 확인해주세요:")
                st.write("- 이메일 주소")
                st.write("- 앱 비밀번호")
                st.write("- Exchange 서버 주소")
    
    tab1, tab2 = st.tabs(["새 면접 요청", "진행 현황"])
    
    with tab1:
        st.subheader("새로운 면접 일정 조율 요청")
        
        with st.form("new_interview_request"):
            col1, col2 = st.columns(2)
            
            with col1:
                interviewer_id = st.text_input(
                    "면접관 사번",
                    placeholder="예: EMP001",
                    help="면접관의 사번을 입력해주세요"
                )
            
            with col2:
                candidate_email = st.text_input(
                    "면접자 이메일",
                    placeholder="candidate@example.com",
                    help="면접자의 이메일 주소를 입력해주세요"
                )
            
            submitted = st.form_submit_button("📧 면접 일정 조율 시작", use_container_width=True)
            
            if submitted:
                if not interviewer_id.strip():
                    st.error("면접관 사번을 입력해주세요.")
                elif not candidate_email.strip():
                    st.error("면접자 이메일을 입력해주세요.")
                elif not validate_email(candidate_email):
                    st.error("올바른 이메일 형식을 입력해주세요.")
                else:
                    # 새 면접 요청 생성
                    request = InterviewRequest.create_new(interviewer_id, candidate_email)
                    db.save_interview_request(request)
                    
                    # 면접관에게 이메일 발송
                    if email_service.send_interviewer_invitation(request):
                        st.success(f"✅ 면접 요청이 생성되었습니다! (ID: {request.id[:8]}...)")
                        st.success(f"📧 면접관({interviewer_id})에게 일정 입력 요청 메일을 발송했습니다.")
                        st.info("면접관이 일정을 입력하면 자동으로 면접자에게 알림이 전송됩니다.")
                    else:
                        st.error("면접 요청은 생성되었지만 이메일 발송에 실패했습니다.")
    
    with tab2:
        st.subheader("면접 일정 조율 현황")
        
        requests = db.get_all_requests()
        
        if not requests:
            st.info("진행 중인 면접 일정 조율이 없습니다.")
        else:
            # 상태별 통계
            col1, col2, col3, col4 = st.columns(4)
            
            status_counts = {}
            for req in requests:
                status_counts[req.status] = status_counts.get(req.status, 0) + 1
            
            with col1:
                st.metric("전체", len(requests))
            with col2:
                st.metric("면접관 대기", status_counts.get(Config.Status.PENDING_INTERVIEWER, 0))
            with col3:
                st.metric("면접자 대기", status_counts.get(Config.Status.PENDING_CANDIDATE, 0))
            with col4:
                st.metric("확정 완료", status_counts.get(Config.Status.CONFIRMED, 0))
            
            # 상세 목록
            st.subheader("📋 상세 현황")
            
            data = []
            for req in requests:
                data.append({
                    "요청ID": req.id[:8] + "...",
                    "면접관": req.interviewer_id,
                    "면접자": req.candidate_email,
                    "상태": req.status,
                    "생성일시": req.created_at.strftime('%m/%d %H:%M'),
                    "확정일시": req.selected_slot.date + " " + req.selected_slot.time if req.selected_slot else "-"
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)

def show_interviewer_page(request_id: str):
    """면접관 일정 입력 페이지"""
    request = db.get_interview_request(request_id)
    
    if not request:
        st.error("❌ 유효하지 않은 요청입니다.")
        return
    
    if request.status != Config.Status.PENDING_INTERVIEWER:
        st.warning(f"⚠️ 이미 처리된 요청입니다. (현재 상태: {request.status})")
        return
    
    st.header("📅 면접 가능 일정 입력")
    st.info(f"면접자: **{request.candidate_email}**")
    
    st.subheader("가능한 면접 일정을 선택해주세요")
    
    with st.form("interviewer_schedule"):
        st.write("**📅 날짜 및 시간 선택**")
        
        # 날짜 선택
        available_dates = get_next_weekdays(10)
        
        selected_slots = []
        
        # 동적으로 일정 추가
        if 'slot_count' not in st.session_state:
            st.session_state.slot_count = 1
        
        for i in range(st.session_state.slot_count):
            st.write(f"**면접 일정 {i+1}**")
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                date = st.selectbox(
                    "날짜",
                    options=available_dates,
                    format_func=format_date_korean,
                    key=f"date_{i}"
                )
            
            with col2:
                time = st.selectbox(
                    "시간",
                    options=Config.TIME_SLOTS,
                    key=f"time_{i}"
                )
            
            with col3:
                duration = st.selectbox(
                    "소요시간",
                    options=[30, 60, 90],
                    index=1,
                    format_func=lambda x: f"{x}분",
                    key=f"duration_{i}"
                )
            
            if date and time:
                selected_slots.append(InterviewSlot(date, time, duration))
        
        # 일정 추가 버튼
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.form_submit_button("➕ 일정 추가"):
                st.session_state.slot_count += 1
                st.experimental_rerun()
        
        # 제출 버튼
        submitted = st.form_submit_button("📧 면접자에게 일정 전송", use_container_width=True)
        
        if submitted:
            if not selected_slots:
                st.error("최소 1개 이상의 면접 일정을 선택해주세요.")
            else:
                # 중복 제거
                unique_slots = []
                seen = set()
                for slot in selected_slots:
                    slot_key = (slot.date, slot.time)
                    if slot_key not in seen:
                        unique_slots.append(slot)
                        seen.add(slot_key)
                
                # 요청 업데이트
                request.available_slots = unique_slots
                request.status = Config.Status.PENDING_CANDIDATE
                request.updated_at = datetime.now()
                
                db.save_interview_request(request)
                
                # 면접자에게 이메일 발송
                if email_service.send_candidate_invitation(request):
                    st.success("✅ 면접 일정이 면접자에게 전송되었습니다!")
                    st.success("📧 면접자가 일정을 선택하면 자동으로 알림을 받게 됩니다.")
                    
                    # 선택된 일정 미리보기
                    st.subheader("📋 전송된 면접 일정")
                    for i, slot in enumerate(unique_slots, 1):
                        st.write(f"{i}. {format_date_korean(slot.date)} {slot.time} ({slot.duration}분)")
                else:
                    st.error("면접 일정은 저장되었지만 이메일 발송에 실패했습니다.")

def show_candidate_page(request_id: str):
    """면접자 일정 선택 페이지"""
    request = db.get_interview_request(request_id)
    
    if not request:
        st.error("❌ 유효하지 않은 요청입니다.")
        return
    
    if request.status == Config.Status.CONFIRMED:
        st.success("✅ 면접 일정이 이미 확정되었습니다!")
        st.info(f"**확정된 면접 일시:** {request.selected_slot}")
        return
    
    if request.status != Config.Status.PENDING_CANDIDATE:
        st.warning(f"⚠️ 현재 면접자 선택 단계가 아닙니다. (현재 상태: {request.status})")
        return
    
    st.header("📅 면접 일정 선택")
    st.info(f"면접관: **{request.interviewer_id}**")
    
    st.subheader("제안된 면접 일정 중 선택해주세요")
    
    with st.form("candidate_selection"):
        # 라디오 버튼으로 일정 선택
        slot_options = []
        for i, slot in enumerate(request.available_slots):
            slot_text = f"{format_date_korean(slot.date)} {slot.time} ({slot.duration}분)"
            slot_options.append(slot_text)
        
        slot_options.append("🔄 다른 일정으로 조율 필요")
        
        selected_option = st.radio(
            "원하는 면접 일정을 선택해주세요:",
            options=range(len(slot_options)),
            format_func=lambda x: slot_options[x]
        )
        
        # 기타 일정 조율이 필요한 경우
        candidate_note = ""
        if selected_option == len(slot_options) - 1:
            candidate_note = st.text_area(
                "희망하는 면접 일정이나 요청사항을 입력해주세요:",
                placeholder="예: 다음 주 화요일 오후 2시 이후 가능합니다.",
                height=100
            )
        
        submitted = st.form_submit_button("✅ 면접 일정 확정", use_container_width=True)
        
        if submitted:
            if selected_option < len(request.available_slots):
                # 정규 일정 선택
                selected_slot = request.available_slots[selected_option]
                request.selected_slot = selected_slot
                request.status = Config.Status.CONFIRMED
            else:
                # 기타 일정 조율
                if not candidate_note.strip():
                    st.error("다른 일정 조율이 필요한 경우 구체적인 요청사항을 입력해주세요.")
                    return
                request.status = Config.Status.PENDING_CONFIRMATION
            
            request.candidate_note = candidate_note
            request.updated_at = datetime.now()
            
            db.save_interview_request(request)
            
            # 확정 알림 발송
            if email_service.send_confirmation_notification(request):
                if request.status == Config.Status.CONFIRMED:
                    st.success("🎉 면접 일정이 확정되었습니다!")
                    st.success("📧 관련자 모두에게 확정 알림을 발송했습니다.")
                    
                    st.subheader("📋 확정된 면접 정보")
                    st.write(f"**면접 일시:** {format_date_korean(request.selected_slot.date)} {request.selected_slot.time}")
                    st.write(f"**소요 시간:** {request.selected_slot.duration}분")
                    st.write(f"**면접관:** {request.interviewer_id}")
                else:
                    st.success("📧 일정 조율 요청이 인사팀에 전달되었습니다!")
                    st.info("인사팀에서 검토 후 별도 연락드리겠습니다.")
            else:
                st.error("면접 일정은 저장되었지만 알림 발송에 실패했습니다.")

if __name__ == "__main__":
    main()
