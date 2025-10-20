import streamlit as st
import pandas as pd
from datetime import datetime, date
from database import DatabaseManager
from email_service import EmailService
from models import InterviewRequest, InterviewSlot
from config import Config
from utils import get_next_weekdays, format_date_korean, validate_email, load_employee_data, get_employee_email
from sync_manager import SyncManager

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
    try:
        db = DatabaseManager()
        email_service = EmailService()
        
        # ✅ SyncManager 임시 제거 (선택적 로드)
        sync_manager = None
        try:
            from sync_manager import SyncManager
            sync_manager = SyncManager(db, email_service)
            sync_manager.start_monitoring()
        except ImportError:
            st.warning("⚠️ 자동 모니터링 모듈을 찾을 수 없습니다. 수동 모드로 실행됩니다.")
        except Exception as e:
            st.warning(f"⚠️ 자동 모니터링 시작 실패: {e}")
        
        return db, email_service, sync_manager
        
    except Exception as e:
        st.error(f"❌ 서비스 초기화 실패: {e}")
        st.stop()

@st.cache_data
def load_organization_data():
    """조직도 데이터 로드"""
    return load_employee_data()

# ✅ 세션 상태 초기화
def init_session_state():
    """세션 상태 초기화"""
    if "form_reset_counter" not in st.session_state:
        st.session_state.form_reset_counter = 0
    if "selected_interviewers" not in st.session_state:
        st.session_state.selected_interviewers = []
    if "selected_candidates" not in st.session_state:
        st.session_state.selected_candidates = []
    if "selected_slots" not in st.session_state:
        st.session_state.selected_slots = []
    if "submission_done" not in st.session_state:
        st.session_state.submission_done = False

# ✅ 면접 요청 탭만 초기화하는 함수 (개선 버전)
def reset_interview_request_tab():
    """면접 요청 탭만 완전 초기화 (다른 탭 상태는 유지)"""
    
    # ✅ 1단계: 카운터 증가로 모든 위젯 key 무효화
    st.session_state.form_reset_counter += 1
    
    # ✅ 2단계: 면접 요청 관련 세션 상태 정리
    keys_to_clean = [
        # 폼 내부 위젯 key들
        "interviewer_id_input",
        "interviewer_select", 
        "candidate_name_input",
        "position_name_input",
        "candidate_email_input",
        "date_selector",
        "time_selector",
        
        # 비즈니스 로직 상태들
        "basic_info",
        "selected_interviewers",
        "selected_candidates",
        "selected_slots", 
        "last_request_id",
        "submission_done"
    ]
    
    for key in keys_to_clean:
        st.session_state.pop(key, None)
    
    # 다시 초기화
    st.session_state.selected_interviewers = []
    st.session_state.selected_candidates = []
    st.session_state.selected_slots = []
    st.session_state.submission_done = False

def render_interviewer_selection(key_suffix, org_data):
    """면접관 선택 섹션 렌더링 (최대 3명)"""
    st.markdown("**👨‍💼 면접관 선택 (최대 3명)**")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if not org_data:  # 조직도 데이터가 없는 경우
            new_interviewer_id = st.text_input(
                "면접관 사번",
                placeholder="예: 223286",
                help="면접관의 사번을 입력해주세요",
                key=f"new_interviewer_id_{key_suffix}"
            )
        else:  # 조직도 데이터가 있는 경우
            interviewer_options = [f"{emp['employee_id']} - {emp['name']} ({emp['department']})" 
                                 for emp in org_data]
            selected_interviewer = st.selectbox(
                "면접관 선택",
                options=["선택해주세요"] + interviewer_options,
                help="면접관을 선택해주세요 (최대 3명)",
                key=f"new_interviewer_select_{key_suffix}"
            )
            new_interviewer_id = selected_interviewer.split(' - ')[0] if selected_interviewer != "선택해주세요" else ""
    
    with col2:
        st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
        add_interviewer_clicked = st.button(
            "➕ 면접관 추가",
            disabled=(not new_interviewer_id.strip() or len(st.session_state.selected_interviewers) >= 3),
            key=f"add_interviewer_{key_suffix}"
        )
    
    # 면접관 추가 로직
    if add_interviewer_clicked and new_interviewer_id.strip():
        if new_interviewer_id not in st.session_state.selected_interviewers:
            if len(st.session_state.selected_interviewers) < 3:
                st.session_state.selected_interviewers.append(new_interviewer_id)
                st.success(f"✅ 면접관 {new_interviewer_id}이(가) 추가되었습니다.")
                st.rerun()
            else:
                st.warning("⚠️ 최대 3명까지만 선택 가능합니다.")
        else:
            st.warning("⚠️ 이미 선택된 면접관입니다.")
    
    # 선택된 면접관 목록 표시
    if st.session_state.selected_interviewers:
        st.markdown("**선택된 면접관:**")
        for i, interviewer_id in enumerate(st.session_state.selected_interviewers):
            col1, col2 = st.columns([4, 1])
            with col1:
                # 조직도에서 이름 찾기
                interviewer_name = "알 수 없음"
                if org_data:
                    for emp in org_data:
                        if emp['employee_id'] == interviewer_id:
                            interviewer_name = f"{emp['name']} ({emp['department']})"
                            break
                st.text(f"{i+1}. {interviewer_id} - {interviewer_name}")
            with col2:
                if st.button("❌", key=f"remove_interviewer_{i}_{key_suffix}"):
                    st.session_state.selected_interviewers.pop(i)
                    st.rerun()

def render_candidate_selection(key_suffix):
    """면접자 선택 섹션 렌더링 (n명)"""
    st.markdown("**👤 면접자 선택**")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        new_candidate_name = st.text_input(
            "면접자 이름",
            placeholder="정면접",
            key=f"new_candidate_name_{key_suffix}"
        )
    
    with col2:
        new_candidate_email = st.text_input(
            "면접자 이메일",
            placeholder="candidate@example.com",
            key=f"new_candidate_email_{key_suffix}"
        )
    
    with col3:
        st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
        add_candidate_clicked = st.button(
            "➕ 면접자 추가",
            disabled=(not new_candidate_name.strip() or not new_candidate_email.strip()),
            key=f"add_candidate_{key_suffix}"
        )
    
    # 면접자 추가 로직
    if add_candidate_clicked:
        if new_candidate_name.strip() and new_candidate_email.strip():
            if validate_email(new_candidate_email):
                candidate_info = {
                    'name': new_candidate_name.strip(),
                    'email': new_candidate_email.strip()
                }
                
                # 중복 확인 (이메일 기준)
                existing_emails = [c['email'] for c in st.session_state.selected_candidates]
                if new_candidate_email not in existing_emails:
                    st.session_state.selected_candidates.append(candidate_info)
                    st.success(f"✅ 면접자 {new_candidate_name}이(가) 추가되었습니다.")
                    st.rerun()
                else:
                    st.warning("⚠️ 이미 등록된 이메일입니다.")
            else:
                st.error("❌ 올바른 이메일 형식을 입력해주세요.")
    
    # 선택된 면접자 목록 표시
    if st.session_state.selected_candidates:
        st.markdown("**선택된 면접자:**")
        for i, candidate in enumerate(st.session_state.selected_candidates):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.text(f"{i+1}. {candidate['name']} ({candidate['email']})")
            with col2:
                if st.button("❌", key=f"remove_candidate_{i}_{key_suffix}"):
                    st.session_state.selected_candidates.pop(i)
                    st.rerun()

def main():
    st.title("📅 AI 면접 일정 조율 시스템")

    # ✅ 세션 상태 초기화
    init_session_state()
    
    # ✅ 서비스 초기화
    db, email_service, sync_manager = init_services()
    
    # 조직도 데이터 로드
    org_data = load_organization_data()
        
    # ✅ 탭 생성 (기본 방식 사용)
    tab1, tab2 = st.tabs(["새 면접 요청", "진행 현황"])
    
    with tab1:
        # ✅ 동적 key suffix 생성
        key_suffix = st.session_state.form_reset_counter
        
        # ✅ 기본 정보 입력 폼
        with st.form("new_interview_request"):
            st.markdown("**📋 기본 정보**")
            
            position_name = st.text_input(
                "공고명",
                placeholder="IT혁신팀 데이터분석가",
                key=f"position_name_input_{key_suffix}"
            )
            
            # ✅ 폼 제출 버튼
            basic_info_submitted = st.form_submit_button("💾 기본 정보 저장", use_container_width=True)
            
            # 기본 정보 검증 및 세션 저장
            if basic_info_submitted:
                if not position_name.strip():
                    st.error("공고명을 입력해주세요.")
                else:
                    # 세션에 기본 정보 저장
                    st.session_state.basic_info = {
                        'position_name': position_name
                    }
                    st.success("✅ 기본 정보가 저장되었습니다. 아래에서 면접관과 면접자를 선택해 주세요.")
        
        # ✅ 면접관 및 면접자 선택 섹션 (폼 밖)
        if 'basic_info' in st.session_state:
            st.markdown("---")
            
            # 면접관 선택 섹션
            render_interviewer_selection(key_suffix, org_data)
            
            st.markdown("---")
            
            # 면접자 선택 섹션
            render_candidate_selection(key_suffix)
            
            st.markdown("---")
            
            # ✅ 면접 희망일시 선택 섹션
            st.markdown("**📅 면접 희망일시 선택 (최대 5개)**")
            
            available_dates = get_next_weekdays(20)
            
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                selected_date = st.selectbox(
                    "날짜 선택",
                    options=["선택안함"] + available_dates,
                    format_func=lambda x: format_date_korean(x) if x != "선택안함" else x,
                    key=f"date_selector_{key_suffix}"
                )
            
            with col2:
                time_options = ["선택안함", "면접관 선택"] + Config.TIME_SLOTS
                selected_time = st.selectbox(
                    "시간 선택",
                    options=time_options,
                    key=f"time_selector_{key_suffix}",
                    help="면접관 선택을 선택하면 면접관이 시간을 직접 선택합니다"
                )

            with col3:
                st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
                add_clicked = st.button(
                    "➕ 일정 추가",
                    disabled=(selected_date == "선택안함" or selected_time == "선택안함"),
                    key=f"add_slot_btn_{key_suffix}"
                )
            
            # 선택 추가 버튼
            if add_clicked:
                if selected_date != "선택안함" and selected_time != "선택안함":
                    time_value = "면접관 선택" if selected_time == "면접관 선택" else selected_time
                    datetime_slot = f"{selected_date} {time_value}"
                    
                    if datetime_slot not in st.session_state.selected_slots:
                        if len(st.session_state.selected_slots) < 5:
                            st.session_state.selected_slots.append(datetime_slot)
                            st.rerun()
                        else:
                            st.warning("⚠️ 최대 5개까지 선택 가능합니다.")
                    else:
                        st.warning("⚠️ 이미 선택된 일정입니다.")
            
            # ✅ 선택된 일정을 테이블로 실시간 표시
            if st.session_state.selected_slots:
                st.markdown("**📋 선택된 희망일시**")
                
                table_data = []
                for i, slot in enumerate(st.session_state.selected_slots, 1):
                    if "면접관 선택" in slot:
                        date_part = slot.split(' ')[0]
                        time_display = "면접관이 선택함"
                    else:
                        date_part, time_part = slot.split(' ')
                        time_display = time_part
                    
                    table_data.append({
                        "번호": i,
                        "날짜": format_date_korean(date_part),
                        "시간": time_display
                    })
                
                df = pd.DataFrame(table_data)
                for col in df.columns:
                    df[col] = df[col].astype(str)
                
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                if len(st.session_state.selected_slots) > 0:
                    col1, col2 = st.columns([10, 1])
                    with col2:
                        if st.button("일정 초기화", key="delete_all"):
                            st.session_state.selected_slots = []
                            st.success("✅ 모든 일정이 삭제되었습니다.")
                            st.rerun()
            
            # ✅ 최종 제출 섹션
            st.markdown("---")
            
            if st.session_state.submission_done:
                st.success(f"✅ 면접 요청이 생성되었습니다!")
                
                if st.button("새로운 면접 요청", type="primary", use_container_width=True):
                    reset_interview_request_tab()
                    st.rerun()
                    
            else:
                if st.button("면접 일정 조율 시작", type="primary", use_container_width=True):
                    # 유효성 검사
                    if not st.session_state.selected_interviewers:
                        st.error("최소 1명의 면접관을 선택해주세요.")
                    elif not st.session_state.selected_candidates:
                        st.error("최소 1명의 면접자를 선택해주세요.")
                    elif not st.session_state.selected_slots:
                        st.error("1개 이상의 면접 희망일시를 선택해주세요.")
                    else:
                        # ✅ 다중 면접자에 대해 각각 면접 요청 생성
                        success_count = 0
                        total_requests = len(st.session_state.selected_candidates)
                        
                        for candidate in st.session_state.selected_candidates:
                            try:
                                # 각 면접자별로 면접 요청 생성
                                request = InterviewRequest.create_new(
                                    interviewer_id=",".join(st.session_state.selected_interviewers),  # 복수 면접관 지원
                                    candidate_email=candidate['email'],
                                    candidate_name=candidate['name'],
                                    position_name=st.session_state.basic_info['position_name'],
                                    preferred_datetime_slots=st.session_state.selected_slots.copy()
                                )
                                
                                db.save_interview_request(request)
                                
                                if email_service.send_interviewer_invitation(request):
                                    success_count += 1
                                
                            except Exception as e:
                                st.error(f"❌ {candidate['name']} 면접 요청 생성 실패: {e}")
                        
                        if success_count > 0:
                            st.session_state.submission_done = True
                            st.success(f"✅ {success_count}/{total_requests}개의 면접 요청이 생성되었습니다!")
                            st.rerun()
                        else:
                            st.error("❌ 모든 면접 요청 생성에 실패했습니다.")
        else:
            st.info("👆 먼저 위에서 기본 정보를 입력하고 저장해주세요.")
    
    with tab2:
        st.subheader("📊 진행 현황")
        
        try:
            # 구글 시트에서 데이터 가져오기
            if db.sheet:
                sheet_data = db.sheet.get_all_records()
                
                if not sheet_data:
                    st.info("구글 시트에 데이터가 없습니다.")
                else:
                    # 상태별 통계 계산
                    status_counts = {
                        "일정재조율요청": 0,
                        "면접관_일정대기": 0,
                        "면접자_선택대기": 0,
                        "확정완료": 0
                    }
                    
                    for row in sheet_data:
                        status = str(row.get('상태', '')).strip()
                        if status in status_counts:
                            status_counts[status] += 1
                    
                    # 통계 표시
                    col1, col2, col3, col4 = st.columns(4)
                    
                    total_count = len(sheet_data)
                    interviewer_waiting = status_counts["면접관_일정대기"]
                    candidate_waiting = status_counts["면접자_선택대기"]
                    confirmed = status_counts["확정완료"]
                    
                    with col1:
                        st.metric("전체", total_count)
                    with col2:
                        st.metric("면접관 대기", interviewer_waiting)
                    with col3:
                        st.metric("면접자 대기", candidate_waiting)
                    with col4:
                        st.metric("확정 완료", confirmed)
                    
                    # 상세 목록 표시
                    st.subheader("📋 상세 현황")
                    
                    # DataFrame으로 변환하여 표시
                    df = pd.DataFrame(sheet_data)
                    
                    # 필요한 컬럼만 선택
                    display_columns = []
                    if '요청ID' in df.columns:
                        display_columns.append('요청ID')
                    if '포지션' in df.columns:
                        display_columns.append('포지션')
                    if '면접관' in df.columns:
                        display_columns.append('면접관')
                    if '면접자명' in df.columns:
                        display_columns.append('면접자명')
                    if '면접자이메일' in df.columns:
                        display_columns.append('면접자이메일')
                    if '상태' in df.columns:
                        display_columns.append('상태')
                    if '생성일시' in df.columns:
                        display_columns.append('생성일시')
                    if '확정일시' in df.columns:
                        display_columns.append('확정일시')
                    
                    if display_columns:
                        display_df = df[display_columns].copy()
                        
                        # 모든 컬럼을 문자열로 변환
                        for col in display_df.columns:
                            display_df[col] = display_df[col].astype(str)
                        
                        # 상태별 색상 구분을 위한 스타일링
                        def highlight_status(val):
                            if val == "확정완료":
                                return 'background-color: #d4edda; color: #155724'
                            elif val == "면접관_일정대기":
                                return 'background-color: #fff3cd; color: #856404'
                            elif val == "면접자_선택대기":
                                return 'background-color: #cce7ff; color: #004085'
                            elif val == "일정재조율요청":
                                return 'background-color: #f8d7da; color: #721c24'
                            return ''
                        
                        if '상태' in display_df.columns:
                            styled_df = display_df.style.applymap(highlight_status, subset=['상태'])
                            st.dataframe(styled_df, use_container_width=True)
                        else:
                            st.dataframe(display_df, use_container_width=True)
                    else:
                        st.dataframe(df, use_container_width=True)
                    
                    # ✅ 관리 기능 - 간단한 방식으로 수정
                    st.subheader("🔧 관리 기능")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("🔄 데이터 새로고침", use_container_width=True):
                            st.cache_resource.clear()  # 캐시 클리어
                            st.rerun()
                    
                    with col2:
                        if Config.GOOGLE_SHEET_ID:
                            st.link_button(
                                "📋 구글 시트 열기",
                                Config.GOOGLE_SHEET_URL,
                                use_container_width=True
                            )
                        else:
                            st.button("📋 구글 시트 열기", disabled=True, use_container_width=True)
                            st.error("구글 시트 ID가 설정되지 않았습니다.")
                    
                    with col3:
                        if st.button("📊 전체 동기화", use_container_width=True):
                            try:
                                requests = db.get_all_requests()
                                success_count = 0
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                
                                for i, req in enumerate(requests):
                                    status_text.text(f"동기화 중... {i+1}/{len(requests)}")
                                    if db.update_google_sheet(req):
                                        success_count += 1
                                    progress_bar.progress((i + 1) / len(requests))
                                
                                progress_bar.empty()
                                status_text.empty()
                                st.success(f"✅ 구글 시트 동기화 완료 ({success_count}/{len(requests)})")
                            except Exception as e:
                                st.error(f"❌ 구글 시트 동기화 실패: {e}")
                    
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
            st.info("구글 시트 연결을 확인해주세요.")

if __name__ == "__main__":
    main()