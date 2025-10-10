import streamlit as st
from datetime import datetime
import sys
import os

# 상위 디렉터리의 모듈들을 import하기 위해 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager
from email_service import EmailService
from config import Config
from utils import format_date_korean, create_calendar_invite

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
    st.caption("면접자 전용 페이지")
    
    # URL 파라미터에서 요청 ID 가져오기
    query_params = st.query_params
    request_id = query_params.get('id', None)
    
    if not request_id:
        show_access_guide()
        return
    
    show_candidate_page(request_id)

def show_access_guide():
    """접근 안내 페이지"""
    st.markdown("""
    <div style="text-align: center; padding: 50px; background-color: #f8f9fa; border-radius: 10px; margin: 20px 0;">
        <h2 style="color: #6c757d;">🔒 인증이 필요합니다</h2>
        <p style="font-size: 18px; color: #495057; margin: 20px 0;">이 페이지는 면접자 전용 페이지입니다.</p>
        <p style="color: #6c757d;">이메일로 받으신 링크를 통해 접속해주세요.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("📧 이메일을 받지 못하셨나요?")
        st.markdown("""
        **다음을 확인해주세요:**
        - 스팸 메일함을 확인해주세요
        - 이메일 주소가 정확한지 확인해주세요
        - 인사팀에 문의해주세요 (hr@ajnet.co.kr)
        """)
        
        st.info("💡 **참고:** 면접 일정 선택은 면접관이 가능한 일정을 제안한 후에 가능합니다.")

def show_candidate_page(request_id: str):
    """면접자 일정 선택 페이지"""
    request = db.get_interview_request(request_id)
    
    if not request:
        st.error("❌ 유효하지 않은 요청입니다.")
        st.info("이메일의 링크가 올바른지 확인하거나 인사팀에 문의해주세요.")
        return
    
    if request.status == Config.Status.CONFIRMED:
        show_confirmed_schedule(request)
        return
    
    if request.status != Config.Status.PENDING_CANDIDATE:
        st.warning(f"⚠️ 현재 면접자 선택 단계가 아닙니다.")
        
        if request.status == Config.Status.PENDING_INTERVIEWER:
            st.info("🕐 면접관이 가능한 일정을 입력하는 중입니다. 잠시만 기다려주세요.")
        elif request.status == Config.Status.PENDING_CONFIRMATION:
            st.info("📋 인사팀에서 일정을 재조율하고 있습니다. 곧 연락드리겠습니다.")
        return
    
    # 면접 정보 표시 (HTML 테이블)
    st.markdown(f"""
    <div style="background-color: #e8f5e8; padding: 25px; border-radius: 10px; margin: 20px 0; border-left: 6px solid #28a745;">
        <h3 style="color: #155724; margin-top: 0;">👋 안녕하세요, {request.candidate_name}님!</h3>
        <p style="color: #155724; margin-bottom: 20px;">면접 일정을 선택해주세요. 아래 정보를 확인하시고 편리한 시간을 선택하시면 됩니다.</p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
            <tr>
                <td style="padding: 10px 0; font-weight: bold; width: 120px; color: #155724;">포지션</td>
                <td style="padding: 10px 0; color: #155724; font-weight: bold; font-size: 16px;">{request.position_name}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #155724;">면접관</td>
                <td style="padding: 10px 0; color: #155724;">{request.interviewer_id}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #155724;">요청일</td>
                <td style="padding: 10px 0; color: #155724;">{request.created_at.strftime('%Y년 %m월 %d일')}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    st.subheader("🗓️ 제안된 면접 일정 중 선택해주세요")
    
    # 제안된 일정을 HTML 테이블로 표시
    if request.available_slots:
        slots_html = """
        <div style="margin: 25px 0;">
            <table style="width: 100%; border-collapse: collapse; border: 3px solid #28a745; border-radius: 8px; overflow: hidden; box-shadow: 0 6px 12px rgba(0,0,0,0.15);">
                <thead>
                    <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                        <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">선택</th>
                        <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">날짜</th>
                        <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">시간</th>
                        <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">소요시간</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, slot in enumerate(request.available_slots):
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            slots_html += f"""
                    <tr style="background-color: {bg_color}; border-bottom: 1px solid #dee2e6;">
                        <td style="padding: 20px; text-align: center;">
                            <div style="font-size: 20px; font-weight: bold; color: #28a745;">옵션 {i+1}</div>
                        </td>
                        <td style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">{format_date_korean(slot.date)}</td>
                        <td style="padding: 20px; text-align: center; font-size: 18px; color: #007bff; font-weight: bold;">{slot.time}</td>
                        <td style="padding: 20px; text-align: center; font-size: 16px;">{slot.duration}분</td>
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
            
            submitted = st.form_submit_button("✅ 면접 일정 선택 완료", use_container_width=True, type="primary")
            
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
                        
                        # 새로고침으로 확정 화면 표시
                        st.rerun()
                    else:
                        st.info("인사팀에서 검토 후 별도 연락드리겠습니다.")
                        st.markdown("""
                        <div style="background-color: #d1ecf1; padding: 20px; border-radius: 8px; border-left: 4px solid #17a2b8; margin: 20px 0;">
                            <h4 style="color: #0c5460; margin-top: 0;">📞 연락처 안내</h4>
                            <p style="color: #0c5460; margin: 0;">급한 사항이 있으시면 인사팀(hr@ajnet.co.kr)으로 연락해주세요.</p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.error("면접 일정은 저장되었지만 알림 발송에 실패했습니다.")
    
    else:
        st.error("제안된 면접 일정이 없습니다.")
        st.info("면접관이 아직 가능한 일정을 입력하지 않았습니다. 잠시만 기다려주세요.")

def show_confirmed_schedule(request):
    """확정된 일정 표시"""
    if not request.selected_slot:
        return
    
    st.markdown("""
    <div style="background-color: #d4edda; padding: 30px; border-radius: 15px; border-left: 8px solid #28a745; margin: 20px 0; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h1 style="color: #155724; margin-top: 0; font-size: 2.5rem;">🎉</h1>
        <h2 style="color: #155724; margin: 10px 0;">면접 일정이 확정되었습니다!</h2>
        <p style="color: #155724; font-size: 18px;">아래 확정된 면접 정보를 확인해주세요.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 확정 일정 HTML 테이블
    confirmed_html = f"""
    <div style="margin: 30px 0;">
        <table style="width: 100%; border-collapse: collapse; border: 3px solid #28a745; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 16px rgba(0,0,0,0.1);">
            <thead>
                <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                    <th style="padding: 25px; text-align: center; font-size: 20px; font-weight: bold;">구분</th>
                    <th style="padding: 25px; text-align: center; font-size: 20px; font-weight: bold;">내용</th>
                </tr>
            </thead>
            <tbody>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 25px; font-weight: bold; text-align: center; font-size: 18px;">📅 면접 일시</td>
                    <td style="padding: 25px; text-align: center; font-size: 24px; color: #28a745; font-weight: bold;">
                        {format_date_korean(request.selected_slot.date)} {request.selected_slot.time}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 25px; font-weight: bold; text-align: center; font-size: 18px;">⏱️ 소요 시간</td>
                    <td style="padding: 25px; text-align: center; font-size: 20px; font-weight: bold;">{request.selected_slot.duration}분</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 25px; font-weight: bold; text-align: center; font-size: 18px;">👨‍💼 면접관</td>
                    <td style="padding: 25px; text-align: center; font-size: 18px;">{request.interviewer_id}</td>
                </tr>
                <tr>
                    <td style="padding: 25px; font-weight: bold; text-align: center; font-size: 18px;">💼 포지션</td>
                    <td style="padding: 25px; text-align: center; font-size: 18px;">{request.position_name}</td>
                </tr>
            </tbody>
        </table>
    </div>
    """
    
    st.markdown(confirmed_html, unsafe_allow_html=True)
    
    # 캘린더 초대장 다운로드
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
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
    
    st.markdown("""
    <div style="background-color: #e3f2fd; padding: 25px; border-radius: 12px; border-left: 6px solid #2196f3; margin: 30px 0;">
        <h4 style="color: #1565c0; margin-top: 0; font-size: 20px;">📝 면접 준비 안내</h4>
        <ul style="color: #1565c0; line-height: 2; font-size: 16px; margin: 15px 0;">
            <li><strong>면접 당일 10분 전까지 도착</strong>해주시기 바랍니다</li>
            <li><strong>신분증</strong>과 필요 서류를 지참해주세요</li>
            <li>일정 변경이 필요한 경우 <strong>최소 24시간 전</strong>에 인사팀에 연락해주세요</li>
            <li>면접 장소나 기타 문의사항은 인사팀으로 연락해주세요</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # 연락처 정보
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 25px; border-radius: 12px; text-align: center; margin: 30px 0; border: 2px solid #dee2e6;">
        <h4 style="color: #495057; margin-top: 0; font-size: 18px;">📞 문의사항이 있으시면</h4>
        <p style="margin: 0; color: #6c757d; font-size: 16px;">인사팀: <a href="mailto:hr@ajnet.co.kr" style="color: #007bff; text-decoration: none; font-weight: bold;">hr@ajnet.co.kr</a></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
