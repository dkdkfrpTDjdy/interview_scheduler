import streamlit as st
import pandas as pd
from datetime import datetime, date
from database import DatabaseManager
from email_service import EmailService
from models import InterviewRequest, InterviewSlot
from config import Config
from utils import get_next_weekdays, format_date_korean, validate_email, load_employee_data, get_employee_email

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

@st.cache_data
def load_organization_data():
    """조직도 데이터 로드"""
    return load_employee_data()

db, email_service = init_services()

def main():
    st.title("📅 AI 면접 일정 조율 시스템")
    st.header("🏢 인사팀 관리 대시보드")
    
    # 조직도 데이터 로드
    org_data = load_organization_data()
    
    # 시스템 상태 확인
    with st.sidebar:
        st.subheader("🔧 시스템 상태")
        
        # 이메일 서비스 연결 테스트
        if st.button("📧 이메일 연결 테스트"):
            test_result = email_service._create_smtp_connection()
            if test_result:
                test_result.quit()
                st.success("✅ 이메일 서버 연결 성공")
            else:
                st.error("❌ 이메일 서버 연결 실패")
        
        # 조직도 데이터 상태
        if org_data:
            st.success(f"✅ 조직도 데이터: {len(org_data)}명")
        else:
            st.error("❌ 조직도 데이터 로드 실패")
            st.info("employee_data.xlsx 파일을 확인해주세요")
        
        # 페이지 링크 안내
        st.divider()
        st.subheader("🔗 다른 페이지")
        st.markdown("**면접관용:** `/면접관_일정입력?id=요청ID`")
        st.markdown("**면접자용:** `/면접자_일정선택?id=요청ID`")
        st.caption("이메일에서 자동으로 링크가 생성됩니다")
    
    tab1, tab2, tab3 = st.tabs(["새 면접 요청", "진행 현황", "구글 시트 관리"])
    
    with tab1:
        st.subheader("새로운 면접 일정 조율 요청")
        
        with st.form("new_interview_request"):
            col1, col2 = st.columns(2)
            
            with col1:
                # 면접관 선택 (조직도에서)
                if org_data:
                    interviewer_options = [f"{emp['employee_id']} - {emp['name']} ({emp['department']})" 
                                         for emp in org_data]
                    selected_interviewer = st.selectbox(
                        "면접관 선택",
                        options=["선택해주세요"] + interviewer_options,
                        help="조직도에서 면접관을 선택해주세요"
                    )
                    interviewer_id = selected_interviewer.split(' - ')[0] if selected_interviewer != "선택해주세요" else ""
                else:
                    interviewer_id = st.text_input(
                        "면접관 사번",
                        placeholder="예: EMP001",
                        help="면접관의 사번을 입력해주세요"
                    )
                
                candidate_name = st.text_input(
                    "면접자 이름",
                    placeholder="홍길동",
                    help="면접자의 이름을 입력해주세요"
                )
                
                position_name = st.text_input(
                    "공고명 (포지션명)",
                    placeholder="백엔드 개발자",
                    help="채용 공고명 또는 포지션명을 입력해주세요"
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
                    col_date, col_time, col_any_time = st.columns([3, 2, 1])
                    
                    with col_date:
                        selected_date = st.selectbox(
                            f"희망일 {i+1}",
                            options=["선택안함"] + available_dates,
                            format_func=lambda x: format_date_korean(x) if x != "선택안함" else x,
                            key=f"date_{i}"
                        )
                    
                    with col_time:
                        time_options = ["선택안함", "상관없음"] + Config.TIME_SLOTS
                        selected_time = st.selectbox(
                            f"시간 {i+1}",
                            options=time_options,
                            key=f"time_{i}"
                        )
                    
                    with col_any_time:
                        st.write("")  # 공간 확보용
                        if selected_time == "상관없음":
                            st.info("면접관이 선택")
                    
                    if selected_date != "선택안함" and selected_time != "선택안함":
                        # "상관없음" 선택 시 면접관이 고르도록 처리
                        time_value = selected_time if selected_time != "상관없음" else "면접관선택"
                        datetime_slot = f"{selected_date} {time_value}"
                        if datetime_slot not in selected_datetime_slots:
                            selected_datetime_slots.append(datetime_slot)
            
            submitted = st.form_submit_button("📧 면접 일정 조율 시작", use_container_width=True)
            
            if submitted:
                # 유효성 검사
                if not interviewer_id.strip():
                    st.error("면접관을 선택해주세요.")
                elif not candidate_name.strip():
                    st.error("면접자 이름을 입력해주세요.")
                elif not candidate_email.strip():
                    st.error("면접자 이메일을 입력해주세요.")
                elif not position_name.strip():
                    st.error("공고명(포지션명)을 입력해주세요.")
                elif not validate_email(candidate_email):
                    st.error("올바른 이메일 형식을 입력해주세요.")
                elif not selected_datetime_slots:
                    st.error("최소 1개 이상의 면접 희망일시를 선택해주세요.")
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
                    
                    # 구글 시트에 저장
                    db.save_to_google_sheet(request)
                    
                    # 면접관에게 이메일 발송
                    if email_service.send_interviewer_invitation(request):
                        st.success(f"✅ 면접 요청이 생성되었습니다! (ID: {request.id[:8]}...)")
                        st.success(f"📧 면접관({interviewer_id})에게 일정 입력 요청 메일을 발송했습니다.")
                        st.info("면접관이 일정을 입력하면 자동으로 면접자에게 알림이 전송됩니다.")
                        
                        # 생성된 링크 표시
                        interviewer_link = f"{Config.APP_URL}/면접관_일정입력?id={request.id}"
                        st.info(f"**면접관 링크:** {interviewer_link}")
                        
                        # 선택된 희망일시 미리보기
                        st.subheader("📋 전송된 희망일시")
                        for i, slot in enumerate(selected_datetime_slots, 1):
                            if "면접관선택" in slot:
                                date_part = slot.split(' ')[0]
                                st.write(f"{i}. {format_date_korean(date_part)} (시간: 면접관이 선택)")
                            else:
                                date_part, time_part = slot.split(' ')
                                st.write(f"{i}. {format_date_korean(date_part)} {time_part}")
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
                interviewer_link = f"{Config.APP_URL}/면접관_일정입력?id={req.id}"
                candidate_link = f"{Config.APP_URL}/면접자_일정선택?id={req.id}"
                
                data.append({
                    "요청ID": req.id[:8] + "...",
                    "포지션": req.position_name,
                    "면접관": req.interviewer_id,
                    "면접자": f"{req.candidate_name} ({req.candidate_email})",
                    "상태": req.status,
                    "생성일시": req.created_at.strftime('%m/%d %H:%M'),
                    "확정일시": f"{req.selected_slot.date} {req.selected_slot.time}" if req.selected_slot else "-",
                    "면접관링크": interviewer_link,
                    "면접자링크": candidate_link
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True)
    
    with tab3:
        st.subheader("📊 구글 시트 관리")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 구글 시트 동기화"):
                try:
                    requests = db.get_all_requests()
                    success_count = 0
                    for req in requests:
                        if db.update_google_sheet(req):
                            success_count += 1
                    st.success(f"✅ 구글 시트 동기화 완료 ({success_count}/{len(requests)})")
                except Exception as e:
                    st.error(f"❌ 구글 시트 동기화 실패: {e}")
        
        with col2:
            if st.button("📋 구글 시트 열기"):
                if Config.GOOGLE_SHEET_ID:
                    st.markdown(f"[구글 시트 바로가기]({Config.GOOGLE_SHEET_URL})")
                else:
                    st.error("구글 시트 ID가 설정되지 않았습니다.")

if __name__ == "__main__":
    main()
