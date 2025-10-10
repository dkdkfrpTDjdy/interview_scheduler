import streamlit as st
import pandas as pd
from datetime import datetime, date
from urllib.parse import parse_qs
from database import DatabaseManager
from email_service import EmailService
from models import InterviewRequest, InterviewSlot
from config import Config
from utils import get_next_weekdays, format_date_korean, validate_email, load_employee_data, get_employee_email, get_employee_info, create_calendar_invite

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
    # URL 파라미터 확인으로 페이지 라우팅
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
                data.append({
                    "요청ID": req.id[:8] + "...",
                    "포지션": req.position_name,
                    "면접관": req.interviewer_id,
                    "면접자": f"{req.candidate_name} ({req.candidate_email})",
                    "상태": req.status,
                    "생성일시": req.created_at.strftime('%m/%d %H:%M'),
                    "확정일시": f"{req.selected_slot.date} {req.selected_slot.time}" if req.selected_slot else "-"
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

def show_interviewer_page(request_id: str):
    """면접관 일정 입력 페이지 (단일 앱 내에서)"""
    request = db.get_interview_request(request_id)
    
    if not request:
        st.error("❌ 유효하지 않은 요청입니다.")
        return
    
    if request.status != Config.Status.PENDING_INTERVIEWER:
        st.warning(f"⚠️ 이미 처리된 요청입니다. (현재 상태: {request.status})")
        return
    
    st.title("📅 면접 가능 일정 입력")
    st.caption("면접관용 페이지")
    
    # 뒤로가기 버튼
    if st.button("🏠 메인 페이지로 돌아가기"):
        st.query_params.clear()
        st.rerun()
    
    # 면접 정보 표시
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**포지션:** {request.position_name}")
        st.info(f"**면접자:** {request.candidate_name}")
    with col2:
        st.info(f"**면접자 이메일:** {request.candidate_email}")
        st.info(f"**요청일:** {request.created_at.strftime('%Y-%m-%d %H:%M')}")
    
    # 인사팀에서 제안한 희망일시 표시 (HTML 테이블)
    if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
        st.subheader("🌟 인사팀에서 제안한 면접 희망일시")
        
        # HTML 테이블로 표시
        table_html = """
        <div style="margin: 20px 0;">
            <table style="width: 100%; border-collapse: collapse; border: 2px solid #0078d4; border-radius: 8px; overflow: hidden;">
                <thead>
                    <tr style="background-color: #0078d4; color: white;">
                        <th style="padding: 12px; text-align: center;">번호</th>
                        <th style="padding: 12px; text-align: center;">날짜</th>
                        <th style="padding: 12px; text-align: center;">시간</th>
                        <th style="padding: 12px; text-align: center;">비고</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, datetime_slot in enumerate(request.preferred_datetime_slots, 1):
            if "면접관선택" in datetime_slot:
                date_part = datetime_slot.split(' ')[0]
                time_note = "면접관이 시간 선택"
                time_display = "09:00~17:00 중 선택"
            else:
                date_part, time_part = datetime_slot.split(' ')
                time_note = "시간 고정"
                time_display = time_part
            
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            table_html += f"""
                    <tr style="background-color: {bg_color};">
                        <td style="padding: 12px; text-align: center; font-weight: bold;">{i}</td>
                        <td style="padding: 12px; text-align: center;">{format_date_korean(date_part)}</td>
                        <td style="padding: 12px; text-align: center; color: #0078d4; font-weight: bold;">{time_display}</td>
                        <td style="padding: 12px; text-align: center; font-size: 12px; color: #666;">{time_note}</td>
                    </tr>
            """
        
        table_html += """
                </tbody>
            </table>
        </div>
        """
        
        st.markdown(table_html, unsafe_allow_html=True)
    
    st.subheader("가능한 면접 일정을 선택해주세요")
    st.info("💡 **안내:** 인사팀이 제안한 일정 중에서만 선택 가능하며, 여러 개 선택할 수 있습니다.")
    
    with st.form("interviewer_schedule"):
        selected_slots = []
        
        # 인사팀 제안 일시만 선택 가능하도록 제한
        if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
            st.write("**제안된 일시 중 가능한 시간을 모두 선택해주세요:**")
            
            for i, datetime_slot in enumerate(request.preferred_datetime_slots):
                if "면접관선택" in datetime_slot:
                    # 면접관이 시간을 직접 선택해야 하는 경우
                    date_part = datetime_slot.split(' ')[0]
                    
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        is_selected = st.checkbox(
                            f"{format_date_korean(date_part)} (시간 선택 필요)",
                            key=f"slot_{i}"
                        )
                    
                    with col2:
                        selected_time = st.selectbox(
                            "시간 선택",
                            options=["선택안함"] + Config.TIME_SLOTS,
                            key=f"time_select_{i}",
                            disabled=not is_selected
                        )
                    
                    with col3:
                        duration = st.selectbox(
                            "소요시간",
                            options=[30, 60, 90],
                            index=1,
                            format_func=lambda x: f"{x}분",
                            key=f"duration_{i}",
                            disabled=not is_selected
                        )
                    
                    if is_selected and selected_time != "선택안함":
                        selected_slots.append(InterviewSlot(date_part, selected_time, duration))
                        
                else:
                    # 시간이 고정된 경우
                    date_part, time_part = datetime_slot.split(' ')
                    
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        is_selected = st.checkbox(
                            f"{format_date_korean(date_part)} {time_part}",
                            key=f"slot_{i}"
                        )
                    
                    with col2:
                        st.write(f"**{time_part}** (고정)")
                    
                    with col3:
                        duration = st.selectbox(
                            "소요시간",
                            options=[30, 60, 90],
                            index=1,
                            format_func=lambda x: f"{x}분",
                            key=f"duration_{i}",
                            disabled=not is_selected
                        )
                    
                    if is_selected:
                        selected_slots.append(InterviewSlot(date_part, time_part, duration))
        
        else:
            st.error("인사팀에서 제안한 희망일시가 없습니다. 인사팀에 문의해주세요.")
            return
        
        # 제출 버튼
        submitted = st.form_submit_button("📧 면접자에게 일정 전송", use_container_width=True)
        
        if submitted:
            if not selected_slots:
                st.error("최소 1개 이상의 면접 일정을 선택해주세요.")
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
                    st.success("📧 면접자가 일정을 선택하면 자동으로 알림을 받게 됩니다.")
                    
                    # 선택된 일정 미리보기 (HTML 테이블)
                    st.subheader("📋 전송된 면접 일정")
                    
                    preview_html = """
                    <div style="margin: 20px 0;">
                        <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background-color: #28a745; color: white;">
                                    <th style="padding: 12px; text-align: center;">번호</th>
                                    <th style="padding: 12px; text-align: center;">날짜</th>
                                    <th style="padding: 12px; text-align: center;">시간</th>
                                    <th style="padding: 12px; text-align: center;">소요시간</th>
                                </tr>
                            </thead>
                            <tbody>
                    """
                    
                    for i, slot in enumerate(selected_slots, 1):
                        bg_color = "#f8f9fa" if i % 2 == 0 else "white"
                        preview_html += f"""
                                <tr style="background-color: {bg_color};">
                                    <td style="padding: 12px; text-align: center; font-weight: bold;">{i}</td>
                                    <td style="padding: 12px; text-align: center;">{format_date_korean(slot.date)}</td>
                                    <td style="padding: 12px; text-align: center; color: #28a745; font-weight: bold;">{slot.time}</td>
                                    <td style="padding: 12px; text-align: center;">{slot.duration}분</td>
                                </tr>
                        """
                    
                    preview_html += """
                            </tbody>
                        </table>
                    </div>
                    """
                    
                    st.markdown(preview_html, unsafe_allow_html=True)
                    
                    # 완료 후 자동으로 메인 페이지로 이동하는 옵션
                    if st.button("🏠 메인 페이지로 돌아가기", type="primary"):
                        st.query_params.clear()
                        st.rerun()
                else:
                    st.error("면접 일정은 저장되었지만 이메일 발송에 실패했습니다.")

def show_candidate_page(request_id: str):
    """면접자 일정 선택 페이지 (단일 앱 내에서)"""
    request = db.get_interview_request(request_id)
    
    if not request:
        st.error("❌ 유효하지 않은 요청입니다.")
        return
    
    if request.status == Config.Status.CONFIRMED:
        show_confirmed_schedule(request)
        return
    
    if request.status != Config.Status.PENDING_CANDIDATE:
        st.warning(f"⚠️ 현재 면접자 선택 단계가 아닙니다. (현재 상태: {request.status})")
        return
    
    st.title("📅 면접 일정 선택")
    st.caption("면접자용 페이지")
    
    # 면접 정보 표시 (HTML 테이블)
    st.markdown(f"""
    <div style="background-color: #f8f9fa; padding: 25px; border-radius: 10px; margin: 20px 0; border-left: 6px solid #007bff;">
        <h3 style="color: #007bff; margin-top: 0;">👋 안녕하세요, {request.candidate_name}님!</h3>
        <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
            <tr>
                <td style="padding: 8px 0; font-weight: bold; width: 120px; color: #333;">포지션</td>
                <td style="padding: 8px 0; color: #555;">{request.position_name}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #333;">면접관</td>
                <td style="padding: 8px 0; color: #555;">{request.interviewer_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #333;">요청일</td>
                <td style="padding: 8px 0; color: #555;">{request.created_at.strftime('%Y년 %m월 %d일')}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    st.subheader("🗓️ 제안된 면접 일정 중 선택해주세요")
    
    # 제안된 일정을 HTML 테이블로 표시
    if request.available_slots:
        slots_html = """
        <div style="margin: 25px 0;">
            <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <thead>
                    <tr style="background-color: #28a745; color: white;">
                        <th style="padding: 15px; text-align: center; font-weight: bold;">선택</th>
                        <th style="padding: 15px; text-align: center; font-weight: bold;">날짜</th>
                        <th style="padding: 15px; text-align: center; font-weight: bold;">시간</th>
                        <th style="padding: 15px; text-align: center; font-weight: bold;">소요시간</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, slot in enumerate(request.available_slots):
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            slots_html += f"""
                    <tr style="background-color: {bg_color}; border-bottom: 1px solid #dee2e6;">
                        <td style="padding: 15px; text-align: center;">
                            <div style="font-size: 18px; font-weight: bold; color: #28a745;">옵션 {i+1}</div>
                        </td>
                        <td style="padding: 15px; text-align: center; font-weight: bold;">{format_date_korean(slot.date)}</td>
                        <td style="padding: 15px; text-align: center; font-size: 16px; color: #007bff; font-weight: bold;">{slot.time}</td>
                        <td style="padding: 15px; text-align: center;">{slot.duration}분</td>
                    </tr>
            """
        
        slots_html += """
                </tbody>
            </table>
        </div>
        """
        
        st.markdown(slots_html, unsafe_allow_html=True)
        
        # 선택 폼
        with st.form("candidate_selection"):
            # 라디오 버튼으로 일정 선택
            slot_options = []
            for i, slot in enumerate(request.available_slots):
                slot_text = f"옵션 {i+1}: {format_date_korean(slot.date)} {slot.time} ({slot.duration}분)"
                slot_options.append(slot_text)
            
            slot_options.append("❌ 제안된 일정으로는 불가능 (다른 일정 요청)")
            
            selected_option = st.radio(
                "원하는 면접 일정을 선택해주세요:",
                options=range(len(slot_options)),
                format_func=lambda x: slot_options[x]
            )
            
            # 다른 일정이 필요한 경우
            candidate_note = ""
            if selected_option == len(slot_options) - 1:
                st.markdown("""
                <div style="background-color: #fff3cd; padding: 20px; border-radius: 8px; border-left: 4px solid #ffc107; margin: 20px 0;">
                    <h4 style="color: #856404; margin-top: 0;">📝 다른 일정 요청</h4>
                    <p style="color: #856404; margin-bottom: 15px;">제안된 일정이 맞지 않으시나요? 가능한 일정을 구체적으로 알려주세요.</p>
                </div>
                """, unsafe_allow_html=True)
                
                candidate_note = st.text_area(
                    "가능한 면접 일정이나 요청사항을 입력해주세요:",
                    placeholder="예시:\n• 다음 주 화요일 오후 2시 이후 가능합니다\n• 월요일과 수요일은 전체 불가능합니다\n• 오전 시간대를 선호합니다",
                    height=120
                )
            
            submitted = st.form_submit_button("✅ 면접 일정 선택 완료", use_container_width=True)
            
            if submitted:
                if selected_option < len(request.available_slots):
                    # 정규 일정 선택
                    selected_slot = request.available_slots[selected_option]
                    request.selected_slot = selected_slot
                    request.status = Config.Status.CONFIRMED
                    success_message = "🎉 면접 일정이 확정되었습니다!"
                    
                else:
                    # 다른 일정 필요
                    if not candidate_note.strip():
                        st.error("가능한 일정이 없는 경우 구체적인 가능 일정을 입력해주세요.")
                        return
                    request.status = Config.Status.PENDING_CONFIRMATION
                    success_message = "📧 일정 재조율 요청이 인사팀에 전달되었습니다!"
                
                request.candidate_note = candidate_note
                request.updated_at = datetime.now()
                
                db.save_interview_request(request)
                db.update_google_sheet(request)
                
                # 확정 알림 발송
                if email_service.send_confirmation_notification(request):
                    st.success(success_message)
                    if request.status == Config.Status.CONFIRMED:
                        st.success("📧 관련자 모두에게 확정 알림을 발송했습니다.")
                        
                        # 캘린더 초대장 생성
                        try:
                            ics_content = create_calendar_invite(request)
                            if ics_content:
                                st.download_button(
                                    label="📅 캘린더에 추가하기 (.ics 파일 다운로드)",
                                    data=ics_content,
                                    file_name=f"면접일정_{request.candidate_name}_{request.selected_slot.date}.ics",
                                    mime="text/calendar"
                                )
                        except Exception as e:
                            st.info("캘린더 초대장 생성에 실패했지만, 면접 일정은 정상적으로 확정되었습니다.")
                        
                        # 확정된 면접 정보 표시
                        show_confirmed_schedule(request)
                    else:
                        st.info("인사팀에서 검토 후 별도 연락드리겠습니다.")
                else:
                    st.error("면접 일정은 저장되었지만 알림 발송에 실패했습니다.")
    
    else:
        st.error("제안된 면접 일정이 없습니다. 인사팀에 문의해주세요.")

def show_confirmed_schedule(request):
    """확정된 일정 표시"""
    if not request.selected_slot:
        return
    
    st.markdown("""
    <div style="background-color: #d4edda; padding: 25px; border-radius: 10px; border-left: 6px solid #28a745; margin: 20px 0;">
        <h3 style="color: #155724; margin-top: 0;">🎉 면접 일정이 확정되었습니다!</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # 확정 일정 HTML 테이블
    confirmed_html = f"""
    <div style="margin: 25px 0;">
        <h4 style="color: #28a745; margin-bottom: 15px;">📋 확정된 면접 정보</h4>
        <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden;">
            <thead>
                <tr style="background-color: #28a745; color: white;">
                    <th style="padding: 15px; text-align: center;">구분</th>
                    <th style="padding: 15px; text-align: center;">내용</th>
                </tr>
            </thead>
            <tbody>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 15px; font-weight: bold; text-align: center;">면접 일시</td>
                    <td style="padding: 15px; text-align: center; font-size: 18px; color: #28a745; font-weight: bold;">
                        {format_date_korean(request.selected_slot.date)} {request.selected_slot.time}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 15px; font-weight: bold; text-align: center;">소요 시간</td>
                    <td style="padding: 15px; text-align: center; font-size: 16px;">{request.selected_slot.duration}분</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 15px; font-weight: bold; text-align: center;">면접관</td>
                    <td style="padding: 15px; text-align: center;">{request.interviewer_id}</td>
                </tr>
                <tr>
                    <td style="padding: 15px; font-weight: bold; text-align: center;">포지션</td>
                    <td style="padding: 15px; text-align: center;">{request.position_name}</td>
                </tr>
            </tbody>
        </table>
    </div>
    """
    
    st.markdown(confirmed_html, unsafe_allow_html=True)
    
    # 캘린더 초대장 다운로드
    try:
        ics_content = create_calendar_invite(request)
        if ics_content:
            st.download_button(
                label="📅 캘린더에 추가하기 (.ics 파일 다운로드)",
                data=ics_content,
                file_name=f"면접일정_{request.candidate_name}_{request.selected_slot.date}.ics",
                mime="text/calendar"
            )
    except Exception:
        pass
    
    st.markdown("""
    <div style="background-color: #d1ecf1; padding: 20px; border-radius: 8px; border-left: 4px solid #17a2b8; margin: 20px 0;">
        <h4 style="color: #0c5460; margin-top: 0;">📝 면접 안내사항</h4>
        <ul style="color: #0c5460; line-height: 1.6;">
            <li><strong>면접 당일 10분 전까지 도착</strong>해주시기 바랍니다</li>
            <li>신분증과 필요 서류를 지참해주세요</li>
            <li>일정 변경이 필요한 경우 <strong>최소 24시간 전</strong>에 인사팀에 연락해주세요</li>
            <li>궁금한 사항이 있으시면 언제든 인사팀으로 문의해주세요</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
