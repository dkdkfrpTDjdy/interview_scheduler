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

# ✅ 면접 요청 탭만 초기화하는 함수 (개선 버전)
def reset_interview_request_tab():
    """면접 요청 탭만 완전 초기화 (다른 탭 상태는 유지)"""
    
    # ✅ 1단계: 카운터 증가로 모든 위젯 key 무효화
    if "form_reset_counter" not in st.session_state:
        st.session_state.form_reset_counter = 0
    st.session_state.form_reset_counter += 1
    
    # ✅ 2단계: 면접 요청 관련 세션 상태 정리
    keys_to_clean = [
        # 폼 내부 위젯 key들 (동적 key 사용 시 필요없지만 혹시 모를 잔여 제거)
        "interviewer_id_input",
        "interviewer_select", 
        "candidate_name_input",
        "position_name_input",
        "candidate_email_input",
        "date_selector",
        "time_selector",
        
        # 비즈니스 로직 상태들
        "basic_info",
        "selected_slots", 
        "last_request_id",
        "submission_done"
    ]
    
    for key in keys_to_clean:
        st.session_state.pop(key, None)  # None으로 기본값 설정하여 KeyError 방지

def main():
    st.title("📅 AI 면접 일정 조율 시스템")

    # ✅ 서비스 초기화 추가 (누락된 부분)
    db, email_service, sync_manager = init_services()

    # ✅ 폼 리셋 카운터 초기화
    if "form_reset_counter" not in st.session_state:
        st.session_state.form_reset_counter = 0
    
    # 조직도 데이터 로드
    org_data = load_organization_data()
        
    tab1, tab2= st.tabs(["새 면접 요청", "진행 현황"])
    
    with tab1:

        # ✅ 동적 key suffix 생성
        key_suffix = st.session_state.form_reset_counter        
        
        # ✅ 면접 희망일시 선택 상태 관리 (초기화 보장)
        if 'selected_slots' not in st.session_state:
            st.session_state.selected_slots = []
        if 'submission_done' not in st.session_state:
            st.session_state.submission_done = False
        
        # ✅ 폼 구조 개선: 기본 정보만 폼 안에, 일정 선택은 폼 밖으로
        with st.form("new_interview_request"):
            col1, col2 = st.columns(2)
            
            with col1:
                # ✅ 면접관 선택 로직 수정
                if not org_data:  # 조직도 데이터가 없는 경우
                    interviewer_id = st.text_input(
                        "면접관 사번",
                        placeholder="예: 223286",
                        help="면접관의 사번을 입력해주세요",
                        key=f"interviewer_id_input_{key_suffix}"  # ✅ 동적 key
                    )
                else:  # 조직도 데이터가 있는 경우
                    interviewer_options = [f"{emp['employee_id']} - {emp['name']} ({emp['department']})" 
                                         for emp in org_data]
                    selected_interviewer = st.selectbox(
                        "면접관 선택",
                        options=["선택해주세요"] + interviewer_options,
                        help="면접관을 직접 선택하거나 사번을 입력해 주세요",
                        key=f"interviewer_select_{key_suffix}"
                    )
                    interviewer_id = selected_interviewer.split(' - ')[0] if selected_interviewer != "선택해주세요" else ""

                candidate_name = st.text_input(
                    "면접자 이름",
                    placeholder="정면접",
                    key=f"candidate_name_input_{key_suffix}"  # ✅ 동적 key
                )
            
            with col2:
                position_name = st.text_input(
                    "공고명",
                    placeholder="IT혁신팀 데이터분석가",
                    key=f"position_name_input_{key_suffix}"  # ✅ 동적 key
                )
                
                candidate_email = st.text_input(
                    "면접자 이메일",
                    placeholder="candidate@example.com",
                    key=f"candidate_email_input_{key_suffix}"  # ✅ 동적 key
                )
            
            # ✅ 폼 제출 버튼 수정
            basic_info_submitted = st.form_submit_button("💾 기본 정보 저장", use_container_width=True)
            
            # 기본 정보 검증 및 세션 저장
            if basic_info_submitted:
                if not interviewer_id.strip():
                    st.error("면접관을 선택해주세요.")
                elif not candidate_name.strip():
                    st.error("면접자 이름을 입력해주세요.")
                elif not candidate_email.strip():
                    st.error("면접자 이메일을 입력해주세요.")
                elif not position_name.strip():
                    st.error("공고명을 입력해주세요.")
                elif not validate_email(candidate_email):
                    st.error("올바른 이메일 형식을 입력해주세요.")
                else:
                    # 세션에 기본 정보 저장
                    st.session_state.basic_info = {
                        'interviewer_id': interviewer_id,
                        'candidate_name': candidate_name,
                        'candidate_email': candidate_email,
                        'position_name': position_name
                    }
                    st.success("✅ 기본 정보가 저장되었습니다. 아래에서 면접 희망 일시를 선택해 주세요.")
        
        # ✅ 면접 희망일시 선택 섹션 (폼 밖)
        if 'basic_info' in st.session_state:
            st.markdown("---")
            st.markdown("**📅 면접 희망일시 선택 (최대 5개)**")
            
            available_dates = get_next_weekdays(20)
            
            # 단일 선택 박스로 통합
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                selected_date = st.selectbox(
                    "날짜 선택",
                    options=["선택안함"] + available_dates,
                    format_func=lambda x: format_date_korean(x) if x != "선택안함" else x,
                    key=f"date_selector_{key_suffix}"  # ✅ 동적 key
                )
            
            with col2:
                time_options = ["선택안함", "면접관 선택"] + Config.TIME_SLOTS
                selected_time = st.selectbox(
                    "시간 선택",
                    options=time_options,
                    key=f"time_selector_{key_suffix}",  # ✅ 동적 key
                    help="면접관 선택을 선택하면 면접관이 시간을 직접 선택합니다"
                )

            with col3:
                # ✅ 빈 레이블을 추가해서 높이 맞추기
                st.markdown("""
                <div style="font-size:16px;">
                    　
                </div>
                """, unsafe_allow_html=True)
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
                        else:
                            st.warning("⚠️ 최대 5개까지 선택 가능합니다.")
                    else:
                        st.warning("⚠️ 이미 선택된 일정입니다.")
            
            # ✅ 선택된 일정을 테이블로 실시간 표시
            if st.session_state.selected_slots:
                st.markdown("**📋 선택된 희망일시**")
                
                # DataFrame으로 변환하여 표시
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
                
                # ✅ DataFrame 타입 문제 해결
                df = pd.DataFrame(table_data)
                # 모든 컬럼을 문자열로 변환하여 Arrow 변환 에러 방지
                for col in df.columns:
                    df[col] = df[col].astype(str)
                
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                if len(st.session_state.selected_slots) > 0:
                    # 전체 삭제 버튼만 오른쪽에 위치
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

                # ✅ 면접 요청 탭만 초기화하는 버튼
                if st.button("새로운 면접 요청", type="primary", use_container_width=True):
                    reset_interview_request_tab()  # 면접 요청 탭만 초기화
                    st.rerun()
                    
            else:
                if st.button("면접 일정 조율 시작", type="primary", use_container_width=True):
                    basic_info = st.session_state.basic_info
                    
                    # 유효성 검사
                    if not st.session_state.selected_slots:
                        st.error("1개 이상의 면접 희망일시를 선택해주세요.")
                    else:
                        # 면접 요청 생성
                        request = InterviewRequest.create_new(
                            interviewer_id=basic_info['interviewer_id'],
                            candidate_email=basic_info['candidate_email'],
                            candidate_name=basic_info['candidate_name'],
                            position_name=basic_info['position_name'],
                            preferred_datetime_slots=st.session_state.selected_slots.copy()
                        )
                        
                        try:
                            db.save_interview_request(request)
                            
                            if email_service.send_interviewer_invitation(request):
                                st.session_state.last_request_id = request.id
                                st.session_state.submission_done = True
                                st.rerun()
                            else:
                                st.error("이메일 발송에 실패했습니다.")
                        except Exception as e:
                            st.error(f"❌ 면접 요청 저장 실패: {e}")
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
                    
                    # 필요한 컬럼만 선택 (구글 시트 컬럼명에 맞게 조정)
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
                    
                    # 관리 기능
                    st.subheader("🔧 관리 기능")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("🔄 데이터 새로고침", use_container_width=True):
                            st.cache_resource.clear()  # 캐시 클리어
                            st.rerun()
                    
                    with col2:
                        if st.button("📋 구글 시트 열기", use_container_width=True):
                            if Config.GOOGLE_SHEET_ID:
                                st.markdown(f"[구글 시트 바로가기]({Config.GOOGLE_SHEET_URL})")
                            else:
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



