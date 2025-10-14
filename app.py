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
    db = DatabaseManager()
    email_service = EmailService()
    
    # ✅ 모니터링 시작
    sync_manager = SyncManager(db, email_service)
    sync_manager.start_monitoring()
    
    return db, email_service, sync_manager

@st.cache_data
def load_organization_data():
    """조직도 데이터 로드"""
    return load_employee_data()

db, email_service = init_services()

def main():
    st.title("📅 AI 면접 일정 조율 시스템")
    st.header("인사팀 관리 페이지")
    
    # 조직도 데이터 로드
    org_data = load_organization_data()
        
    tab1, tab2, tab3 = st.tabs(["새 면접 요청", "진행 현황", "구글 시트 관리"])
    
    with tab1:
        st.subheader("새로운 면접 일정 조율 요청")
        
        with st.form("new_interview_request"):
            col1, col2 = st.columns(2)
            
            with col1:
                # ✅ 면접관 선택 로직 수정
                if not org_data:  # 조직도 데이터가 없는 경우
                    interviewer_id = st.text_input(
                        "면접관 사번",
                        placeholder="예: 223286",
                        help="면접관의 사번을 입력해주세요"
                    )
                else:  # 조직도 데이터가 있는 경우
                    interviewer_options = [f"{emp['employee_id']} - {emp['name']} ({emp['department']})" 
                                         for emp in org_data]
                    selected_interviewer = st.selectbox(
                        "면접관 선택",
                        options=["선택해주세요"] + interviewer_options,
                        help="조직도에서 면접관을 선택해주세요"
                    )
                    interviewer_id = selected_interviewer.split(' - ')[0] if selected_interviewer != "선택해주세요" else ""

                candidate_name = st.text_input(
                    "면접자 이름",
                    placeholder="홍길동",
                    help="면접자의 이름을 입력해주세요"
                )
                
                position_name = st.text_input(
                    "공고명",
                    placeholder="로지스 유통사업팀",
                    help="채용 공고명을 입력해주세요"
                )
            
            with col2:
                candidate_email = st.text_input(
                    "면접자 이메일",
                    placeholder="candidate@example.com",
                    help="면접자의 이메일 주소를 입력해주세요"
                )
                
                # 📅 개선된 면접 희망일 및 시간 선택 (최대 5개)
                st.write("**면접 희망일 및 시간 선택 (최대 5개)**")
                available_dates = get_next_weekdays(20)
                
                selected_datetime_slots = []
                for i in range(5):
                    st.markdown(f"**옵션 {i+1}**")
                    col_date, col_time = st.columns([2, 1])
                    
                    with col_date:
                        selected_date = st.selectbox(
                            "날짜",
                            options=["선택안함"] + available_dates,
                            format_func=lambda x: format_date_korean(x) if x != "선택안함" else x,
                            key=f"date_{i}"
                        )
                    
                    with col_time:
                        # 시간 선택 옵션 개선
                        time_options = ["선택안함", "면접관선택"] + Config.TIME_SLOTS
                        selected_time = st.selectbox(
                            "시간",
                            options=time_options,
                            key=f"time_{i}",
                            help="면접관선택을 선택하면 면접관이 시간을 직접 선택합니다"
                        )
                    
                    if selected_date != "선택안함" and selected_time != "선택안함":
                        # "면접관선택" 선택 시 면접관이 고르도록 처리
                        if selected_time == "면접관선택":
                            time_value = "면접관선택"
                        else:
                            time_value = selected_time
                        
                        datetime_slot = f"{selected_date} {time_value}"
                        if datetime_slot not in selected_datetime_slots:
                            selected_datetime_slots.append(datetime_slot)
            
            submitted = st.form_submit_button("📧 면접 일정 조율 시작", use_container_width=True, type="primary")
            
            if submitted:
                # 유효성 검사
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
                elif not selected_datetime_slots:
                    st.error("1개 이상의 면접 희망일시를 선택해주세요.")
                else:
                    # 새 면접 요청 생성
                    request = InterviewRequest.create_new(
                        interviewer_id=interviewer_id,
                        candidate_email=candidate_email,
                        candidate_name=candidate_name,
                        position_name=position_name,
                        preferred_datetime_slots=selected_datetime_slots
                    )
                    db.save_interview_request(request)
                    
                    # 면접관에게 이메일 발송
                    if email_service.send_interviewer_invitation(request):
                        st.success(f"✅ 면접 요청이 생성되었습니다! (ID: {request.id[:8]}...)")
                        st.success(f"📧 면접관({interviewer_id})에게 일정 입력 요청 메일을 발송했습니다.")
                        st.info("면접관이 일정을 입력하면 자동으로 면접자에게 알림이 전송됩니다.")
                        
                        # ✅ 선택된 희망일시 미리보기 (Streamlit 테이블만 사용)
                        if selected_datetime_slots:
                            st.subheader("📋 전송된 희망일시")
                            
                            # DataFrame으로 변환하여 표시
                            table_data = []
                            for i, slot in enumerate(selected_datetime_slots, 1):
                                if "면접관선택" in slot:
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
                            
                            # ✅ Streamlit 테이블로만 표시 (HTML 테이블 제거)
                            st.dataframe(
                                pd.DataFrame(table_data), 
                                use_container_width=True, 
                                hide_index=True
                            )
                    else:
                        st.error("이메일 발송에 실패했습니다.")
    
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
                    "요청ID": req.id[:8],
                    "포지션": req.position_name,
                    "면접관": req.interviewer_id,
                    "면접자": f"{req.candidate_name} ({req.candidate_email})",
                    "상태": req.status,
                    "생성일시": req.created_at.strftime('%m/%d %H:%M'),
                    "확정일시": f"{req.selected_slot.date} {req.selected_slot.time}" if req.selected_slot else "-"
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
            
            # 🔧 추가: 개별 요청 관리
            st.subheader("🔧 개별 요청 관리")
            
            # 요청 선택
            selected_request_id = st.selectbox(
                "관리할 요청을 선택하세요",
                options=["선택하세요"] + [f"{req.id[:8]}... - {req.position_name} ({req.candidate_name})" for req in requests]
            )
            
            if selected_request_id != "선택하세요":
                # 선택된 요청 찾기
                request_short_id = selected_request_id.split(' - ')[0]
                selected_request = None
                for req in requests:
                    if req.id.startswith(request_short_id.replace('...', '')):
                        selected_request = req
                        break
                
                if selected_request:
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("📧 면접관에게 다시 알림", use_container_width=True):
                            if email_service.send_interviewer_invitation(selected_request):
                                st.success("✅ 면접관에게 알림을 다시 발송했습니다.")
                            else:
                                st.error("❌ 알림 발송에 실패했습니다.")
                    
                    with col2:
                        if st.button("📧 면접자에게 다시 알림", use_container_width=True):
                            if selected_request.available_slots:
                                if email_service.send_candidate_invitation(selected_request):
                                    st.success("✅ 면접자에게 알림을 다시 발송했습니다.")
                                else:
                                    st.error("❌ 알림 발송에 실패했습니다.")
                            else:
                                st.warning("⚠️ 면접관이 아직 일정을 입력하지 않았습니다.")
                    
                    with col3:
                        if st.button("❌ 요청 취소", use_container_width=True, type="secondary"):
                            selected_request.status = Config.Status.CANCELLED
                            selected_request.updated_at = datetime.now()
                            db.save_interview_request(selected_request)
                            db.update_google_sheet(selected_request)
                            st.success("✅ 요청이 취소되었습니다.")
                            st.rerun()
    
    with tab3:
        st.subheader("📊 구글 시트 관리")
        
        col1, col2, col3, col4 = st.columns(4)  # ✅ 4개 컬럼으로 변경
        
        with col1:
            if st.button("🔄 전체 동기화", use_container_width=True):
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
        
        with col2:
            if st.button("📊 통계 업데이트", use_container_width=True):
                try:
                    stats = db.get_statistics()
                    st.success("✅ 통계 정보가 업데이트되었습니다.")
                    
                    # 통계 표시
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.metric("전체 요청", stats['total'])
                    with col_b:
                        st.metric("확정 완료", stats['confirmed'])
                    with col_c:
                        avg_time = f"{stats['avg_processing_time']:.1f}시간" if stats['avg_processing_time'] > 0 else "N/A"
                        st.metric("평균 처리시간", avg_time)
                        
                except Exception as e:
                    st.error(f"❌ 통계 업데이트 실패: {e}")
        
        with col3:
            if st.button("📋 시트 열기", use_container_width=True):
                if Config.GOOGLE_SHEET_ID:
                    st.markdown(f"[구글 시트 바로가기]({Config.GOOGLE_SHEET_URL})")
                else:
                    st.error("구글 시트 ID가 설정되지 않았습니다.")
        
        # ✅ 새로 추가: 수동 이메일 발송 트리거
        with col4:
            if st.button("📧 확정 알림 재발송", use_container_width=True):
                try:
                    confirmed_requests = [req for req in db.get_all_requests() 
                                        if req.status == Config.Status.CONFIRMED and req.selected_slot]
                    
                    sent_count = 0
                    for req in confirmed_requests:
                        if email_service.send_confirmation_notification(req, sender_type="system"):
                            sent_count += 1
                    
                    st.success(f"✅ {sent_count}건의 확정 알림을 재발송했습니다.")
                    
                except Exception as e:
                    st.error(f"❌ 재발송 실패: {e}")
        
        # 실시간 시트 미리보기
        st.subheader("📋 실시간 시트 미리보기")
        try:
            if db.sheet:
                sheet_data = db.sheet.get_all_records()
                if sheet_data:
                    df = pd.DataFrame(sheet_data)
                    st.dataframe(df, use_container_width=True, height=400)
                else:
                    st.info("구글 시트가 비어있습니다.")
            else:
                st.warning("구글 시트에 연결되지 않았습니다.")
        except Exception as e:
            st.error(f"시트 데이터 로드 실패: {e}")

if __name__ == "__main__":
    main()


