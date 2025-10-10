
import streamlit as st
from datetime import datetime
from database import DatabaseManager
from email_service import EmailService
from config import Config
from utils import format_date_korean, create_calendar_invite

# 페이지 설정
st.set_page_config(
    page_title="면접 일정 선택 - AI 면접 시스템",
    page_icon="📅",
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
    st.title("📅 면접 일정 선택")
    
    # URL 파라미터에서 요청 ID 가져오기
    query_params = st.query_params
    request_id = query_params.get('id', None)
    
    if not request_id:
        st.error("❌ 유효하지 않은 접근입니다. 이메일의 링크를 통해 접속해주세요.")
        return
    
    show_candidate_page(request_id)

def show_candidate_page(request_id: str):
    """면접자 일정 선택 페이지 (개선된 HTML 테이블 기반)"""
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