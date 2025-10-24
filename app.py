import streamlit as st
import pandas as pd
from datetime import datetime, date
import sys
import os
import time  # ✅ time 모듈 추가

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import DatabaseManager
from email_service import EmailService
from models import InterviewRequest, InterviewSlot
from config import Config

# ✅ utils에서 필요한 함수들 import
try:
    from utils import (
        load_employee_data, 
        validate_email, 
        get_next_weekdays, 
        format_date_korean,
        group_requests_by_interviewer_and_position
    )
except ImportError as e:
    st.error(f"❌ utils.py에서 필요한 함수를 import할 수 없습니다: {e}")
    st.stop()

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
    try:
        return load_employee_data()
    except Exception as e:
        st.warning(f"⚠️ 조직도 데이터 로드 실패: {e}")
        return []
    
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

# ✅ 면접 요청 탭만 초기화
def reset_interview_request_tab():
    """면접 요청 탭만 완전 초기화"""
    st.session_state.form_reset_counter += 1
    
    keys_to_clean = [
        "interviewer_id_input",
        "interviewer_select", 
        "candidate_name_input",
        "position_name_input",
        "candidate_email_input",
        "date_selector",
        "start_time_selector",
        "end_time_selector",
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

# ✅ 면접관 선택 섹션
def render_interviewer_selection(key_suffix, org_data):
    """면접관 선택 섹션 렌더링 (최대 3명)"""
    st.markdown("**👨‍💼 면접관 선택 (최대 3명)**")
    
    # ✅ 동적 key 생성 (카운터 사용)
    input_key = f"interviewer_input_{key_suffix}_{st.session_state.interviewer_input_counter}"
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if not org_data:
            new_interviewer_id = st.text_input(
                "면접관 사번",
                placeholder="예: 223286",
                help="면접관의 사번을 입력해주세요",
                key=f"new_interviewer_id_{input_key}"
            )
        else:
            interviewer_options = [f"{emp['employee_id']} - {emp['name']} ({emp['department']})" 
                                 for emp in org_data]
            selected_interviewer = st.selectbox(
                "면접관 선택",
                options=["선택해주세요"] + interviewer_options,
                help="면접관을 선택해주세요 (최대 3명)",
                key=f"new_interviewer_select_{input_key}"
            )
            new_interviewer_id = selected_interviewer.split(' - ')[0] if selected_interviewer != "선택해주세요" else ""
    
    with col2:
        st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
        add_interviewer_clicked = st.button(
            "➕ 면접관 추가",
            disabled=(not new_interviewer_id.strip() or len(st.session_state.selected_interviewers) >= 3),
            key=f"add_interviewer_{input_key}"
        )
    
    if add_interviewer_clicked and new_interviewer_id.strip():
        if new_interviewer_id not in st.session_state.selected_interviewers:
            if len(st.session_state.selected_interviewers) < 3:
                st.session_state.selected_interviewers.append(new_interviewer_id)
                
                # ✅ 카운터 증가 → 입력 필드 key 변경 → 강제 초기화
                st.session_state.interviewer_input_counter += 1
                
                st.success(f"✅ 면접관 {new_interviewer_id}이(가) 추가되었습니다.")
                time.sleep(0.5)
                st.rerun()
            else:
                st.warning("⚠️ 최대 3명까지만 선택 가능합니다.")
        else:
            st.warning("⚠️ 이미 선택된 면접관입니다.")
    
    if st.session_state.selected_interviewers:
        st.markdown("**선택된 면접관:**")
        for i, interviewer_id in enumerate(st.session_state.selected_interviewers):
            col1, col2 = st.columns([4, 1])
            with col1:
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

# ✅ 면접자 선택 섹션
def render_candidate_selection(key_suffix):
    """면접자 선택 섹션 렌더링 (n명)"""
    st.markdown("**👤 면접자 선택**")
    
    # ✅ 동적 key 생성 (카운터 사용)
    input_key = f"candidate_input_{key_suffix}_{st.session_state.candidate_input_counter}"
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        new_candidate_name = st.text_input(
            "면접자 이름",
            placeholder="정면접",
            key=f"new_candidate_name_{input_key}"
        )
    
    with col2:
        new_candidate_email = st.text_input(
            "면접자 이메일",
            placeholder="candidate@example.com",
            key=f"new_candidate_email_{input_key}"
        )
    
    with col3:
        st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
        add_candidate_clicked = st.button(
            "➕ 면접자 추가",
            disabled=(not new_candidate_name.strip() or not new_candidate_email.strip()),
            key=f"add_candidate_{input_key}"
        )
    
    if add_candidate_clicked:
        if new_candidate_name.strip() and new_candidate_email.strip():
            if validate_email(new_candidate_email):
                candidate_info = {
                    'name': new_candidate_name.strip(),
                    'email': new_candidate_email.strip()
                }
                
                existing_emails = [c['email'] for c in st.session_state.selected_candidates]
                if new_candidate_email not in existing_emails:
                    st.session_state.selected_candidates.append(candidate_info)
                    
                    # ✅ 카운터 증가 → 입력 필드 key 변경 → 강제 초기화
                    st.session_state.candidate_input_counter += 1
                    
                    st.success(f"✅ 면접자 {new_candidate_name}이(가) 추가되었습니다.")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.warning("⚠️ 이미 등록된 이메일입니다.")
            else:
                st.error("❌ 올바른 이메일 형식을 입력해주세요.")
    
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

    init_session_state()
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
    
    # ✅ 입력 필드 초기화용 카운터 추가
    if "interviewer_input_counter" not in st.session_state:
        st.session_state.interviewer_input_counter = 0
    if "candidate_input_counter" not in st.session_state:
        st.session_state.candidate_input_counter = 0
    
    db, email_service, sync_manager = init_services()
    org_data = load_organization_data()
        
    # ✅ 탭 구성 변경: 새 탭 추가
    tab1, tab2, tab3 = st.tabs(["새 면접 요청", "면접자 메일 발송", "진행 현황"])
    
    with tab1:
        key_suffix = st.session_state.form_reset_counter
        
        # ✅ 상세 공고명 추가
        with st.form("new_interview_request"):
            st.markdown("**📋 기본 정보**")
            
            col1, col2 = st.columns(2)
            
            with col1:
                position_name = st.text_input(
                    "공고명",
                    placeholder="공고명",
                    key=f"position_name_input_{key_suffix}"
                )
            
            with col2:
                detailed_position_name = st.text_input(
                    "상세 공고명",
                    placeholder="팀명",
                    key=f"detailed_position_name_input_{key_suffix}"
                )
            
            basic_info_submitted = st.form_submit_button("💾 기본 정보 저장", use_container_width=True)
            
            if basic_info_submitted:
                if not position_name.strip():
                    st.error("공고명을 입력해주세요.")
                else:
                    st.session_state.basic_info = {
                        'position_name': position_name,
                        'detailed_position_name': detailed_position_name or ""
                    }
                    st.success("✅ 기본 정보가 저장되었습니다. 아래에서 면접관과 면접자를 선택해 주세요.")
        
        # ✅ 면접관 및 면접자 선택 섹션 (폼 밖)
        if 'basic_info' in st.session_state:
            st.markdown("---")
            
            render_interviewer_selection(key_suffix, org_data)
            
            st.markdown("---")
            
            render_candidate_selection(key_suffix)
            
            st.markdown("---")
            
            # ✅ 면접관 및 면접자 선택 섹션 (폼 밖)
            if 'basic_info' in st.session_state:
                st.markdown("---")
                
                render_interviewer_selection(key_suffix, org_data)
                
                st.markdown("---")
                
                render_candidate_selection(key_suffix)
                
                st.markdown("---")
                
                # ✅ 면접 희망일시 선택 섹션 (시간 범위 입력)
                st.markdown("**📅 면접 희망 날짜 및 시간대 선택 (최대 5개)**")

                available_dates = get_next_weekdays(30)

                col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 1])

                with col1:
                    selected_date = st.selectbox(
                        "날짜 선택",
                        options=["선택안함"] + available_dates,
                        format_func=lambda x: format_date_korean(x) if x != "선택안함" else x,
                        key=f"date_selector_{key_suffix}"
                    )

                with col2:
                    start_time = st.selectbox(
                        "시작 시간",
                        options=["선택안함"] + Config.TIME_SLOTS,
                        key=f"start_time_selector_{key_suffix}",
                        help="면접 가능 시작 시간"
                    )

                with col3:
                    # ✅ 면접자 수에 따른 자동 종료 시간 계산
                    candidate_count = len(st.session_state.selected_candidates)
                    
                    # 시작 시간이 선택되었고 면접자가 있으면 자동 계산
                    if start_time != "선택안함" and candidate_count > 0:
                        try:
                            # 시작 시간 파싱
                            start_hour, start_min = map(int, start_time.split(':'))
                            start_total_minutes = start_hour * 60 + start_min
                            
                            # 종료 시간 계산 (면접자 수 × 30분)
                            duration_minutes = candidate_count * 30
                            end_total_minutes = start_total_minutes + duration_minutes
                            
                            # 시간 형식으로 변환
                            end_hour = end_total_minutes // 60
                            end_min = end_total_minutes % 60
                            auto_end_time = f"{end_hour:02d}:{end_min:02d}"
                            
                            # 종료 시간 표시 (비활성화)
                            st.text_input(
                                "종료 시간",
                                value=f"{auto_end_time} (자동계산: {candidate_count}명 × 30분)",
                                disabled=True,
                                key=f"end_time_display_{key_suffix}",
                                help=f"면접자 {candidate_count}명 기준 자동 계산"
                            )
                            
                            # 실제 사용할 종료 시간 저장
                            calculated_end_time = auto_end_time
                            
                        except Exception as e:
                            st.error(f"시간 계산 오류: {e}")
                            calculated_end_time = "선택안함"
                    else:
                        # 면접자가 없거나 시작 시간 미선택 시 안내 메시지
                        if candidate_count == 0:
                            st.text_input(
                                "종료 시간",
                                value="면접자를 먼저 추가해주세요",
                                disabled=True,
                                key=f"end_time_display_{key_suffix}"
                            )
                        else:
                            st.text_input(
                                "종료 시간",
                                value="시작 시간을 선택해주세요",
                                disabled=True,
                                key=f"end_time_display_{key_suffix}"
                            )
                        calculated_end_time = "선택안함"

                with col4:
                    st.markdown("<div style='margin-top: 32px;'></div>", unsafe_allow_html=True)
                    add_clicked = st.button(
                        "➕ 시간대 추가",
                        disabled=(
                            selected_date == "선택안함" or 
                            start_time == "선택안함" or 
                            calculated_end_time == "선택안함" or
                            candidate_count == 0
                        ),
                        key=f"add_range_btn_{key_suffix}"
                    )

                if add_clicked:
                    if selected_date != "선택안함" and start_time != "선택안함" and calculated_end_time != "선택안함":
                        # ✅ 자동 계산된 종료 시간 사용
                        time_range_str = f"{selected_date} {start_time}~{calculated_end_time}"
                        
                        if time_range_str not in st.session_state.selected_slots:
                            if len(st.session_state.selected_slots) < 5:
                                st.session_state.selected_slots.append(time_range_str)
                                st.success(f"✅ 시간대 추가: {format_date_korean(selected_date)} {start_time}~{calculated_end_time} (면접자 {candidate_count}명)")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.warning("⚠️ 최대 5개까지 선택 가능합니다.")
                        else:
                            st.warning("⚠️ 이미 선택된 시간대입니다.")

                # ✅ 선택된 시간대를 테이블로 표시
                if st.session_state.selected_slots:
                    st.markdown("**📋 선택된 면접 가능 시간대**")
                    
                    table_data = []
                    for i, slot in enumerate(st.session_state.selected_slots, 1):
                        parts = slot.split(' ')
                        date_part = parts[0]
                        time_range = parts[1] if len(parts) > 1 else "시간 미정"
                        
                        # 30분 단위 슬롯 개수 계산
                        if '~' in time_range:
                            start, end = time_range.split('~')
                            start_parts = start.split(':')
                            end_parts = end.split(':')
                            start_hour = int(start_parts[0])
                            start_min = int(start_parts[1]) if len(start_parts) > 1 else 0
                            end_hour = int(end_parts[0])
                            end_min = int(end_parts[1]) if len(end_parts) > 1 else 0
                            
                            # 분 단위로 계산
                            total_minutes = (end_hour * 60 + end_min) - (start_hour * 60 + start_min)
                            slot_count = total_minutes // 30
                            slot_info = f"(약 {slot_count}개 면접 가능)"
                        else:
                            slot_info = ""
                        
                        table_data.append({
                            "번호": i,
                            "날짜": format_date_korean(date_part),
                            "시간대": time_range,
                            "비고": slot_info
                        })
                    
                    df = pd.DataFrame(table_data)
                    for col in df.columns:
                        df[col] = df[col].astype(str)
                    
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # 초기화 버튼
                    col1, col2 = st.columns([10, 1])
                    with col2:
                        if st.button("시간대 초기화", key=f"clear_slots_{key_suffix}"):
                            st.session_state.selected_slots = []
                            st.success("✅ 모든 시간대가 삭제되었습니다.")
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
                        st.error("1개 이상의 면접 희망 시간대를 선택해주세요.")
                    else:
                        # ✅ Step 1: 모든 면접 요청 생성 (DB 저장)
                        all_requests = []
                        failed_candidates = []

                        for candidate in st.session_state.selected_candidates:
                            try:
                                request = InterviewRequest.create_new(
                                    interviewer_id=",".join(st.session_state.selected_interviewers),
                                    candidate_email=candidate['email'],
                                    candidate_name=candidate['name'],
                                    position_name=st.session_state.basic_info['position_name'],
                                    preferred_datetime_slots=st.session_state.selected_slots.copy()
                                )
                                
                                db.save_interview_request(request)
                                all_requests.append(request)
                                
                            except Exception as e:
                                st.error(f"❌ {candidate['name']} 면접 요청 생성 실패: {e}")
                                failed_candidates.append(candidate['name'])

                        # ✅ 실패한 면접자가 있으면 경고 표시
                        if failed_candidates:
                            st.warning(f"""
                            ⚠️ 일부 면접자의 요청 생성 실패:
                            {', '.join(failed_candidates)}
                            """)

                        # ✅ 성공한 요청이 없으면 중단
                        if not all_requests:
                            st.error("❌ 모든 면접 요청 생성에 실패했습니다. 다시 시도해주세요.")
                            st.stop()
                        
                        # ✅ Step 2: 면접관 + 포지션 조합으로 그룹핑
                        try:
                            from utils import group_requests_by_interviewer_and_position
                            grouped_requests = group_requests_by_interviewer_and_position(all_requests)
                        except ImportError:
                            st.error("❌ utils.py에 group_requests_by_interviewer_and_position 함수가 없습니다.")
                            st.stop()
                        except Exception as e:
                            st.error(f"❌ 그룹핑 중 오류 발생: {e}")
                            st.stop()
                        
                        # ✅ Step 3: 그룹별로 1회만 이메일 발송
                        success_count = 0
                        total_groups = len(grouped_requests)
                        total_emails_sent = 0  # ✅ 실제 발송된 이메일 수

                        if total_groups == 0:
                            st.warning("⚠️ 발송할 이메일 그룹이 없습니다.")
                        else:
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            for i, (group_key, requests) in enumerate(grouped_requests.items()):
                                # 면접관 수 계산
                                interviewer_count = len(requests[0].interviewer_id.split(','))
                                
                                status_text.text(f"📧 이메일 발송 중... {i+1}/{total_groups} ({len(requests)}명 면접자, {interviewer_count}명 면접관)")
                                
                                try:
                                    if email_service.send_interviewer_invitation(requests):
                                        success_count += 1
                                        total_emails_sent += interviewer_count  # ✅ 실제 발송 수 누적
                                    else:
                                        st.warning(f"⚠️ 그룹 {i+1} 발송 실패")
                                except Exception as e:
                                    st.error(f"❌ 그룹 {i+1} 발송 중 오류: {e}")
                                
                                progress_bar.progress((i + 1) / total_groups)
                                time.sleep(0.5)
                            
                            progress_bar.empty()
                            status_text.empty()
                            
                            # 결과 표시
                            if success_count > 0:
                                st.session_state.submission_done = True
                                
                                if success_count == total_groups:
                                    st.success(f"""
                                    ✅ 모든 면접 요청이 성공적으로 생성되었습니다!
                                    
                                    📊 발송 통계:
                                    • 총 면접자: {len(all_requests)}명
                                    • 그룹 수: {total_groups}개
                                    • 실제 이메일 발송: {total_emails_sent}통
                                    • 중복 방지: {len(all_requests) - total_groups}회 절약
                                    """)
                                else:
                                    st.warning(f"""
                                    ⚠️ 일부 면접 요청이 생성되었습니다.
                                    
                                    📊 발송 통계:
                                    • 총 면접자: {len(all_requests)}명
                                    • 성공한 그룹: {success_count}/{total_groups}개
                                    • 실제 이메일 발송: {total_emails_sent}통
                                    """)
                                st.rerun()

    # ✅ 새 탭: 면접자 메일 발송
    with tab2:
        st.subheader("📧 면접자 메일 발송")
        
        try:
            if db.sheet:
                sheet_data = db.sheet.get_all_records()
                
                # "면접자_선택대기" 상태만 필터링
                pending_candidates = [
                    row for row in sheet_data 
                    if str(row.get('상태', '')).strip() == '면접자_선택대기'
                ]
                
                if not pending_candidates:
                    st.info("현재 메일 발송 대기 중인 면접자가 없습니다.")
                else:
                    st.success(f"📊 총 {len(pending_candidates)}명의 면접자가 메일 발송 대기 중입니다.")
                    
                    # 테이블 표시
                    df = pd.DataFrame(pending_candidates)
                    
                    display_columns = []
                    if '포지션명' in df.columns:
                        display_columns.append('포지션명')
                    if '면접자명' in df.columns:
                        display_columns.append('면접자명')
                    if '면접자이메일' in df.columns:
                        display_columns.append('면접자이메일')
                    if '면접자전화번호' in df.columns:  # ✅ 추가
                        display_columns.append('면접자전화번호')
                    if '제안일시목록' in df.columns:
                        display_columns.append('제안일시목록')
                    if '생성일시' in df.columns:
                        display_columns.append('생성일시')
                    
                    if display_columns:
                        display_df = df[display_columns].copy()
                        st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    # 일괄 발송 버튼
                    if st.button("📧 선택된 면접자들에게 메일 일괄 발송", type="primary", use_container_width=True):
                        success_count = 0
                        fail_count = 0
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for i, row in enumerate(pending_candidates):
                            try:
                                request_id = row.get('요청ID', '')
                                if not request_id:
                                    continue
                                
                                status_text.text(f"📧 메일 발송 중... {i+1}/{len(pending_candidates)}")
                                
                                # DB에서 요청 조회
                                request = db.get_interview_request(request_id)
                                if request:
                                    result = email_service.send_candidate_invitation(request)
                                    if result:
                                        success_count += 1
                                    else:
                                        fail_count += 1
                                else:
                                    fail_count += 1
                                
                                progress_bar.progress((i + 1) / len(pending_candidates))
                                time.sleep(0.5)
                                
                            except Exception as e:
                                fail_count += 1
                                st.error(f"❌ {row.get('면접자명', '알 수 없음')} 발송 실패: {e}")
                        
                        progress_bar.empty()
                        status_text.empty()
                        
                        if success_count > 0:
                            st.success(f"✅ 메일 발송 완료: {success_count}명 성공, {fail_count}명 실패")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(f"❌ 모든 메일 발송 실패: {fail_count}명")
                            
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")

    
    with tab3:
        st.subheader("📊 진행 현황")
        
        try:
            if db.sheet:
                sheet_data = db.sheet.get_all_records()
                
                if not sheet_data:
                    st.info("구글 시트에 데이터가 없습니다.")
                else:
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
                    
                    st.subheader("📋 상세 현황")
                    
                    df = pd.DataFrame(sheet_data)
                    
                    display_columns = []
                    if '포지션명' in df.columns:
                        display_columns.append('공고명')
                    if '상세공고명' in df.columns:
                        display_columns.append('상세공고명')
                    if '면접관이름' in df.columns:
                        display_columns.append('면접관이름')
                    if '제안일시목록' in df.columns:
                        display_columns.append('면접관 희망 일시')
                    if '면접자명' in df.columns:
                        display_columns.append('면접자 이름')
                    if '면접자전화번호' in df.columns:
                        display_columns.append('면접자전화번호')
                    if '면접자이메일' in df.columns:
                        display_columns.append('면접자 메일')
                    if '상태' in df.columns:
                        display_columns.append('상태')
                    if '확정일시' in df.columns:
                        display_columns.append('확정일시')
                    
                    if display_columns:
                        display_df = df[display_columns].copy()
                        
                        for col in display_df.columns:
                            display_df[col] = display_df[col].astype(str)
                        
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
                    
                    st.subheader("🔧 관리 기능")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("🔄 데이터 새로고침", use_container_width=True):
                            st.cache_resource.clear()
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