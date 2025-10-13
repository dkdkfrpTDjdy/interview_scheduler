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
        
        # 🔧 수정된 페이지 링크 안내
        st.divider()
        st.subheader("🔗 시스템 페이지")
        st.markdown("**면접관용:** `/면접관_일정입력`")
        st.markdown("**면접자용:** `/면접자_일정선택`")
        st.caption("각 페이지에서 사번/이메일로 인증합니다")
        
        # 빠른 링크 버튼
        st.markdown("### 🚀 빠른 이동")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👨‍💼 면접관", use_container_width=True):
                st.markdown(f'<meta http-equiv="refresh" content="0; url={Config.APP_URL}/면접관_일정입력">', unsafe_allow_html=True)
        with col2:
            if st.button("👤 면접자", use_container_width=True):
                st.markdown(f'<meta http-equiv="refresh" content="0; url={Config.APP_URL}/면접자_일정선택">', unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["새 면접 요청", "진행 현황", "구글 시트 관리", "시스템 관리"])
    
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
                        placeholder="예: 223286",
                        help="면접관의 사번을 입력해주세요"
                    )
                
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
                        time_options = ["선택안함", "상관없음(면접관선택)"] + Config.TIME_SLOTS
                        selected_time = st.selectbox(
                            "시간",
                            options=time_options,
                            key=f"time_{i}",
                            help="상관없음 선택 시 면접관이 시간을 직접 선택합니다"
                        )
                    
                    if selected_date != "선택안함" and selected_time != "선택안함":
                        # "상관없음" 선택 시 면접관이 고르도록 처리
                        if selected_time == "상관없음(면접관선택)":
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
                        
                        # 🔧 수정된 링크 표시
                        st.markdown("### 📎 관련 링크")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.info(f"**면접관 페이지:** {Config.APP_URL}/면접관_일정입력")
                        with col2:
                            st.info(f"**면접자 페이지:** {Config.APP_URL}/면접자_일정선택")
                        
                        # 선택된 희망일시 미리보기 (HTML 테이블)
                        st.subheader("📋 전송된 희망일시")
                        preview_html = """
                        <table style="width: 100%; border-collapse: collapse; border: 2px solid #0078d4; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background-color: #0078d4; color: white;">
                                    <th style="padding: 10px; text-align: center;">번호</th>
                                    <th style="padding: 10px; text-align: center;">날짜</th>
                                    <th style="padding: 10px; text-align: center;">시간</th>
                                </tr>
                            </thead>
                            <tbody>
                        """
                        
                        for i, slot in enumerate(selected_datetime_slots, 1):
                            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
                            if "면접관선택" in slot:
                                date_part = slot.split(' ')[0]
                                time_display = "면접관이 선택"
                            else:
                                date_part, time_part = slot.split(' ')
                                time_display = time_part
                            
                            preview_html += f"""
                                <tr style="background-color: {bg_color};">
                                    <td style="padding: 10px; text-align: center;">{i}</td>
                                    <td style="padding: 10px; text-align: center;">{format_date_korean(date_part)}</td>
                                    <td style="padding: 10px; text-align: center;">{time_display}</td>
                                </tr>
                            """
                        
                        preview_html += """
                            </tbody>
                        </table>
                        """
                        st.markdown(preview_html, unsafe_allow_html=True)
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
                # 🔧 수정된 링크 (파라미터 없음)
                interviewer_link = f"{Config.APP_URL}/면접관_일정입력"
                candidate_link = f"{Config.APP_URL}/면접자_일정선택"
                
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
        
        # 구글 시트 설정 확인
        st.subheader("🔧 구글 시트 설정")
        
        if Config.GOOGLE_SHEET_ID:
            st.success(f"✅ 구글 시트 ID: {Config.GOOGLE_SHEET_ID}")
            st.info(f"🔗 시트 URL: {Config.GOOGLE_SHEET_URL}")
        else:
            st.error("❌ 구글 시트 ID가 설정되지 않았습니다.")
            st.info("환경변수 GOOGLE_SHEET_ID를 설정해주세요.")
        
        # 수동 시트 생성
        if st.button("📝 새 구글 시트 생성 (수동)"):
            st.info("구글 시트를 수동으로 생성하고 ID를 환경변수에 설정해주세요.")
    
    with tab4:
        st.subheader("⚙️ 시스템 관리")
        
        # 환경 설정 확인
        st.subheader("🔍 환경 설정 확인")
        
        config_status = {
            "이메일 서버": "✅" if Config.EmailConfig.EMAIL_USER else "❌",
            "구글 시트": "✅" if Config.GOOGLE_SHEET_ID else "❌",
            "조직도 파일": "✅" if org_data else "❌",
            "앱 URL": "✅" if Config.APP_URL else "❌"
        }
        
        for item, status in config_status.items():
            st.write(f"{status} {item}")
        
        # 데이터베이스 관리
        st.subheader("🗄️ 데이터베이스 관리")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📊 통계 보기"):
                requests = db.get_all_requests()
                st.write(f"**총 요청 수:** {len(requests)}")
                
                # 상태별 통계
                status_counts = {}
                for req in requests:
                    status_counts[req.status] = status_counts.get(req.status, 0) + 1
                
                st.write("**상태별 통계:**")
                for status, count in status_counts.items():
                    st.write(f"- {status}: {count}건")
        
        with col2:
            if st.button("🧹 완료된 요청 정리"):
                # 30일 이상 된 확정 요청들을 아카이브
                st.info("완료된 요청 정리 기능은 추후 구현 예정입니다.")
        
        with col3:
            if st.button("📤 데이터 백업"):
                # 데이터베이스 백업
                st.info("데이터 백업 기능은 추후 구현 예정입니다.")
        
        # 로그 확인
        st.subheader("📝 시스템 로그")
        
        if st.button("📋 최근 로그 보기"):
            st.info("로그 시스템은 추후 구현 예정입니다.")
        
        # 🔧 페이지 링크 테스트
        st.subheader("🔗 페이지 링크 테스트")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**면접관 페이지**")
            interviewer_url = f"{Config.APP_URL}/면접관_일정입력"
            st.code(interviewer_url)
            if st.button("🧪 면접관 페이지 테스트"):
                st.markdown(f'<a href="{interviewer_url}" target="_blank">면접관 페이지 열기</a>', unsafe_allow_html=True)
        
        with col2:
            st.write("**면접자 페이지**")
            candidate_url = f"{Config.APP_URL}/면접자_일정선택"
            st.code(candidate_url)
            if st.button("🧪 면접자 페이지 테스트"):
                st.markdown(f'<a href="{candidate_url}" target="_blank">면접자 페이지 열기</a>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

