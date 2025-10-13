import streamlit as st
from datetime import datetime
from database import DatabaseManager
from email_service import EmailService
from config import Config
from utils import format_date_korean, create_calendar_invite, get_employee_info

# 페이지 설정
st.set_page_config(
    page_title="면접 일정 선택 - AI 면접 시스템",
    page_icon="👤",
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
    st.title("👤 면접 일정 선택")
    st.caption("면접자 전용 독립 페이지")
    
    # 🔧 새로운 인증 방식: 이름 + 이메일
    if 'authenticated_candidate' not in st.session_state:
        show_candidate_login()
    else:
        show_candidate_dashboard()

def show_candidate_login():
    """면접자 인증 페이지 (이름 + 이메일)"""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 40px; border-radius: 15px; text-align: center; margin: 30px 0; box-shadow: 0 10px 30px rgba(40,167,69,0.3);">
        <div style="font-size: 3rem; margin-bottom: 20px;">🔐</div>
        <h1 style="margin: 0 0 15px 0; font-size: 2rem; font-weight: 300;">면접자 인증</h1>
        <p style="font-size: 1.1rem; opacity: 0.9; margin: 0;">이름과 이메일 주소를 입력하여 면접 일정을 확인하세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("candidate_login"):
            st.subheader("📝 정보 입력")
            
            candidate_name = st.text_input(
                "이름을 입력해주세요",
                placeholder="홍길동",
                help="면접 신청 시 입력한 이름을 정확히 입력해주세요"
            )
            
            candidate_email = st.text_input(
                "이메일 주소를 입력해주세요",
                placeholder="hongkildong@example.com",
                help="면접 신청 시 입력한 이메일 주소를 정확히 입력해주세요"
            )
            
            submitted = st.form_submit_button("🔍 면접 일정 확인", use_container_width=True, type="primary")
            
            if submitted:
                if not candidate_name.strip():
                    st.error("❌ 이름을 입력해주세요.")
                elif not candidate_email.strip():
                    st.error("❌ 이메일 주소를 입력해주세요.")
                else:
                    # 해당 면접자의 요청 찾기
                    matching_requests = find_candidate_requests(candidate_name.strip(), candidate_email.strip())
                    
                    if matching_requests:
                        st.session_state.authenticated_candidate = {
                            'name': candidate_name.strip(),
                            'email': candidate_email.strip()
                        }
                        st.session_state.candidate_requests = matching_requests
                        st.rerun()
                    else:
                        st.error("❌ 입력하신 정보와 일치하는 면접 요청을 찾을 수 없습니다.")
                        st.info("💡 이름과 이메일 주소를 정확히 입력했는지 확인해주세요.")
                        st.warning("⚠️ 면접관이 아직 일정을 입력하지 않았을 수도 있습니다.")
    
    # 도움말
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="background-color: #f8f9fa; padding: 25px; border-radius: 12px; text-align: center; border: 1px solid #dee2e6;">
            <h4 style="color: #495057; margin-top: 0;">💡 이용 안내</h4>
            <div style="text-align: left; margin: 15px 0;">
                <p style="margin: 8px 0; color: #6c757d;">• 면접 신청 시 입력한 <strong>정확한 이름과 이메일</strong>을 입력해주세요</p>
                <p style="margin: 8px 0; color: #6c757d;">• 대소문자와 띄어쓰기까지 <strong>정확히 일치</strong>해야 합니다</p>
                <p style="margin: 8px 0; color: #6c757d;">• 면접관이 일정을 입력해야 <strong>선택 가능</strong>합니다</p>
            </div>
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 15px;">
                <p style="margin: 0; color: #1565c0;"><strong>📞 문의:</strong> <a href="mailto:hr@ajnet.co.kr">hr@ajnet.co.kr</a></p>
            </div>
        </div>
        """, unsafe_allow_html=True)

def find_candidate_requests(name: str, email: str):
    """면접자의 요청 찾기 (이름 + 이메일 매칭)"""
    try:
        all_requests = db.get_all_requests()
        matching_requests = []
        
        for request in all_requests:
            # 이름과 이메일이 정확히 일치하는 경우
            if (request.candidate_name.strip().lower() == name.lower() and 
                request.candidate_email.strip().lower() == email.lower()):
                # 취소되지 않은 요청만
                if request.status != Config.Status.CANCELLED:
                    matching_requests.append(request)
        
        return matching_requests
    except Exception as e:
        st.error(f"요청 조회 중 오류가 발생했습니다: {e}")
        return []

def show_candidate_dashboard():
    """면접자 대시보드"""
    candidate_info = st.session_state.authenticated_candidate
    candidate_requests = st.session_state.candidate_requests
    
    # 헤더
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%); padding: 25px; border-radius: 12px; margin: 20px 0;">
            <h2 style="color: #155724; margin: 0; display: flex; align-items: center;">
                <span style="margin-right: 15px;">👋</span> 안녕하세요, {candidate_info['name']}님!
            </h2>
            <p style="color: #155724; margin: 8px 0 0 0; font-size: 1rem;">({candidate_info['email']})</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        if st.button("🚪 로그아웃", use_container_width=True):
            # 세션 상태 초기화
            for key in ['authenticated_candidate', 'candidate_requests']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # 요청 목록 표시
    if not candidate_requests:
        st.markdown("""
        <div style="text-align: center; padding: 60px; background-color: #f8f9fa; border-radius: 15px; margin: 30px 0;">
            <div style="font-size: 4rem; margin-bottom: 20px; color: #6c757d;">📭</div>
            <h3 style="color: #6c757d; margin: 0 0 15px 0;">면접 요청을 찾을 수 없습니다</h3>
            <p style="color: #6c757d; font-size: 1.1rem;">입력하신 정보와 일치하는 면접 요청이 없거나, 아직 면접관이 일정을 입력하지 않았습니다.</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    st.subheader(f"📋 나의 면접 일정 ({len(candidate_requests)}건)")
    
    # 각 요청에 대해 처리
    for i, request in enumerate(candidate_requests):
        with st.expander(f"📅 {request.position_name} - {request.created_at.strftime('%m/%d')} 신청", expanded=len(candidate_requests)==1):
            show_request_detail(request, i)

def show_request_detail(request, index):
    """개별 면접 요청 상세 정보 및 처리"""
    
    if request.status == Config.Status.CONFIRMED:
        show_confirmed_schedule(request)
        return
    
    if request.status == Config.Status.PENDING_INTERVIEWER:
        show_pending_interviewer_status(request)
        return
    
    if request.status == Config.Status.PENDING_CONFIRMATION:
        show_pending_confirmation_status(request)
        return
    
    if request.status != Config.Status.PENDING_CANDIDATE:
        st.info(f"현재 상태: {request.status}")
        return
    
    # 면접 정보 표시
    interviewer_info = get_employee_info(request.interviewer_id)
    
    st.markdown(f"""
    <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid #28a745; margin: 20px 0; box-shadow: 0 2px 10px rgba(40,167,69,0.1);">
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #28a745; width: 120px;">포지션</td>
                <td style="padding: 10px 0; color: #333; font-size: 1.1rem; font-weight: bold;">{request.position_name}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #28a745;">면접관</td>
                <td style="padding: 10px 0; color: #333;">{interviewer_info['name']} ({interviewer_info['department']})</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #28a745;">신청일</td>
                <td style="padding: 10px 0; color: #333;">{request.created_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    # 제안된 일정 표시
    if not request.available_slots:
        st.warning("⚠️ 면접관이 아직 가능한 일정을 입력하지 않았습니다.")
        return
    
    st.write("**🗓️ 제안된 면접 일정 중 선택해주세요**")
    
    # 제안된 일정을 테이블로 표시
    table_html = """
    <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden; margin: 15px 0;">
        <thead>
            <tr style="background-color: #28a745; color: white;">
                <th style="padding: 15px; text-align: center; font-weight: bold;">옵션</th>
                <th style="padding: 15px; text-align: center; font-weight: bold;">날짜</th>
                <th style="padding: 15px; text-align: center; font-weight: bold;">시간</th>
                <th style="padding: 15px; text-align: center; font-weight: bold;">소요시간</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for i, slot in enumerate(request.available_slots, 1):
        bg_color = "#f8f9fa" if i % 2 == 0 else "white"
        table_html += f"""
            <tr style="background-color: {bg_color};">
                <td style="padding: 15px; text-align: center; font-weight: bold;">옵션 {i}</td>
                <td style="padding: 15px; text-align: center; font-weight: bold;">{format_date_korean(slot.date)}</td>
                <td style="padding: 15px; text-align: center; color: #007bff; font-weight: bold;">{slot.time}</td>
                <td style="padding: 15px; text-align: center;">{slot.duration}분</td>
            </tr>
        """
    
    table_html += """
        </tbody>
    </table>
    """
    
    st.markdown(table_html, unsafe_allow_html=True)
    
    # 선택 폼
    with st.form(f"candidate_selection_{index}"):
        # 라디오 버튼으로 일정 선택
        slot_options = []
        for i, slot in enumerate(request.available_slots):
            slot_text = f"옵션 {i+1}: {format_date_korean(slot.date)} {slot.time} ({slot.duration}분)"
            slot_options.append(slot_text)
        
        slot_options.append("❌ 제안된 일정으로는 불가능 (다른 일정 요청)")
        
        selected_option = st.radio(
            "원하는 면접 일정을 선택해주세요:",
            options=range(len(slot_options)),
            format_func=lambda x: slot_options[x],
            help="가장 편리한 일정을 선택하거나, 다른 일정이 필요한 경우 마지막 옵션을 선택해주세요"
        )
        
        # 다른 일정이 필요한 경우
        candidate_note = ""
        if selected_option == len(slot_options) - 1:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); padding: 25px; border-radius: 12px; border-left: 6px solid #ffc107; margin: 25px 0;">
                <h4 style="color: #856404; margin-top: 0; font-size: 1.3rem;">📝 다른 일정 요청</h4>
                <p style="color: #856404; margin-bottom: 15px;">제안된 일정이 맞지 않으시나요? 가능한 일정을 구체적으로 알려주세요.</p>
            </div>
            """, unsafe_allow_html=True)
            
            candidate_note = st.text_area(
                "가능한 면접 일정이나 요청사항을 입력해주세요:",
                placeholder="예시:\n• 다음 주 화요일 오후 2시 이후 가능합니다\n• 월요일과 수요일은 전체 불가능합니다\n• 오전 시간대를 선호합니다\n• 온라인 면접을 희망합니다",
                height=150,
                help="구체적으로 작성해주시면 더 빠른 조율이 가능합니다"
            )
        
        submitted = st.form_submit_button(
            "✅ 면접 일정 선택 완료", 
            use_container_width=True, 
            type="primary"
        )
        
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
                    st.error("❌ 가능한 일정이 없는 경우 구체적인 가능 일정을 입력해주세요.")
                    return
                request.status = Config.Status.PENDING_CONFIRMATION
                success_message = "📧 일정 재조율 요청이 인사팀에 전달되었습니다!"
            
            request.candidate_note = candidate_note
            request.updated_at = datetime.now()
            
            db.save_interview_request(request)
            
            # 🔧 자동 이메일 알림 발송
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
                                mime="text/calendar",
                                use_container_width=True,
                                type="secondary"
                            )
                    except Exception as e:
                        st.info("캘린더 초대장 생성에 실패했지만, 면접 일정은 정상적으로 확정되었습니다.")
                    
                    # 요청 목록에서 업데이트
                    for i, req in enumerate(st.session_state.candidate_requests):
                        if req.id == request.id:
                            st.session_state.candidate_requests[i] = request
                            break
                    
                    st.rerun()
                else:
                    st.info("인사팀에서 검토 후 별도 연락드리겠습니다.")
            else:
                st.error("❌ 면접 일정은 저장되었지만 알림 발송에 실패했습니다.")

def show_confirmed_schedule(request):
    """확정된 일정 표시"""
    if not request.selected_slot:
        return
    
    st.markdown("""
    <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #28a745; margin: 20px 0; text-align: center;">
        <div style="font-size: 3rem; margin-bottom: 15px;">🎉</div>
        <h3 style="color: #155724; margin: 0 0 10px 0;">면접 일정이 확정되었습니다!</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # 확정 일정 표시
    interviewer_info = get_employee_info(request.interviewer_id)
    
    confirmed_html = f"""
    <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden; margin: 20px 0;">
        <tbody>
            <tr style="background-color: #28a745; color: white;">
                <td style="padding: 15px; font-weight: bold; text-align: center;">구분</td>
                <td style="padding: 15px; font-weight: bold; text-align: center;">내용</td>
            </tr>
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 15px; font-weight: bold; color: #28a745;">📅 면접 일시</td>
                <td style="padding: 15px; text-align: center; font-size: 1.2rem; color: #28a745; font-weight: bold;">
                    {format_date_korean(request.selected_slot.date)} {request.selected_slot.time}
                </td>
            </tr>
            <tr>
                <td style="padding: 15px; font-weight: bold; color: #28a745;">⏱️ 소요 시간</td>
                <td style="padding: 15px; text-align: center; font-weight: bold;">{request.selected_slot.duration}분</td>
            </tr>
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 15px; font-weight: bold; color: #28a745;">👨‍💼 면접관</td>
                <td style="padding: 15px; text-align: center;">{interviewer_info['name']} ({interviewer_info['department']})</td>
            </tr>
            <tr>
                <td style="padding: 15px; font-weight: bold; color: #28a745;">💼 포지션</td>
                <td style="padding: 15px; text-align: center; font-weight: bold;">{request.position_name}</td>
            </tr>
        </tbody>
    </table>
    """
    
    st.markdown(confirmed_html, unsafe_allow_html=True)
    
    # 캘린더 초대장 다운로드
    try:
        ics_content = create_calendar_invite(request)
        if ics_content:
            st.download_button(
                label="📅 내 캘린더에 추가하기 (.ics 파일 다운로드)",
                data=ics_content,
                file_name=f"면접일정_{request.candidate_name}_{request.selected_slot.date}.ics",
                mime="text/calendar",
                use_container_width=True,
                type="primary"
            )
    except Exception:
        pass
    
    # 면접 준비 안내
    st.markdown("""
    <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 25px; border-radius: 12px; border-left: 6px solid #2196f3; margin: 25px 0;">
        <h4 style="color: #1565c0; margin-top: 0;">📝 면접 준비 안내</h4>
        <ul style="color: #1565c0; line-height: 1.8;">
            <li>⏰ 면접 당일 <strong>10분 전까지 도착</strong>해주세요</li>
            <li>📞 일정 변경이 필요한 경우 <strong>최소 24시간 전</strong>에 인사팀에 연락해주세요</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

def show_pending_interviewer_status(request):
    """면접관 일정 대기 상태"""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); padding: 30px; border-radius: 15px; text-align: center; margin: 20px 0;">
        <div style="font-size: 3rem; margin-bottom: 15px;">🕐</div>
        <h4 style="color: #856404; margin: 0;">면접관이 가능한 일정을 입력하는 중입니다</h4>
        <p style="color: #856404; margin: 10px 0 0 0;">잠시만 기다려주세요. 면접관이 일정을 입력하면 자동으로 알림을 받게 됩니다.</p>
    </div>
    """, unsafe_allow_html=True)

def show_pending_confirmation_status(request):
    """재조율 대기 상태"""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%); padding: 30px; border-radius: 15px; text-align: center; margin: 20px 0;">
        <div style="font-size: 3rem; margin-bottom: 15px;">📋</div>
        <h4 style="color: #0c5460; margin: 0;">인사팀에서 일정을 재조율하고 있습니다</h4>
        <p style="color: #0c5460; margin: 10px 0 0 0;">곧 연락드리겠습니다. 급한 사항이 있으시면 인사팀에 연락해주세요.</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
