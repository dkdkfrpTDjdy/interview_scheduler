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
    st.caption("면접자 전용 페이지")
    
    # URL 파라미터에서 요청 ID 가져오기
    query_params = st.query_params
    request_id = query_params.get('id', None)
    
    if not request_id:
        show_access_guide()
        return
    
    # 요청 유효성 검사
    request = db.get_interview_request(request_id)
    if not request:
        show_invalid_request()
        return
    
    show_candidate_page(request)

def show_access_guide():
    """접근 안내 페이지"""
    st.markdown("""
    <div style="text-align: center; padding: 80px 40px; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; border-radius: 15px; margin: 40px 0; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
        <div style="font-size: 80px; margin-bottom: 20px;">🎯</div>
        <h1 style="margin: 0 0 20px 0; font-size: 2.5rem; font-weight: 300;">면접자 전용 페이지</h1>
        <p style="font-size: 1.2rem; margin: 20px 0; opacity: 0.9;">이메일로 받으신 링크를 통해 접속해주세요</p>
        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; margin-top: 30px;">
            <p style="margin: 0; font-size: 1rem;">🔗 올바른 링크 형식: <code>candidate_app.py?id=요청ID</code></p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="background-color: #f8f9fa; padding: 30px; border-radius: 15px; text-align: center; margin: 30px 0; border: 1px solid #dee2e6; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h3 style="color: #495057; margin-top: 0;">📧 이메일을 받지 못하셨나요?</h3>
            <div style="text-align: left; margin: 20px 0;">
                <p style="margin: 10px 0; color: #6c757d;"><strong>✓</strong> 스팸 메일함을 확인해주세요</p>
                <p style="margin: 10px 0; color: #6c757d;"><strong>✓</strong> 이메일 주소가 정확한지 확인해주세요</p>
                <p style="margin: 10px 0; color: #6c757d;"><strong>✓</strong> 인사팀에 문의해주세요</p>
            </div>
            <div style="background-color: #e8f5e8; padding: 15px; border-radius: 8px; margin-top: 20px;">
                <p style="margin: 0; color: #155724;"><strong>📞 인사팀 연락처:</strong> <a href="mailto:hr@ajnet.co.kr" style="color: #28a745;">hr@ajnet.co.kr</a></p>
            </div>
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 15px;">
                <p style="margin: 0; color: #1565c0;"><strong>💡 참고:</strong> 면접 일정 선택은 면접관이 가능한 일정을 제안한 후에 가능합니다.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

def show_invalid_request():
    """유효하지 않은 요청 안내"""
    st.markdown("""
    <div style="text-align: center; padding: 60px 40px; background-color: #ffebee; border-radius: 15px; margin: 40px 0; border-left: 6px solid #f44336;">
        <div style="font-size: 60px; margin-bottom: 20px; color: #f44336;">❌</div>
        <h2 style="color: #c62828; margin: 0 0 20px 0;">유효하지 않은 요청입니다</h2>
        <p style="color: #d32f2f; font-size: 1.1rem; margin: 20px 0;">이메일의 링크가 올바른지 확인하거나 인사팀에 문의해주세요.</p>
        <div style="background-color: #ffcdd2; padding: 20px; border-radius: 10px; margin-top: 30px;">
            <p style="margin: 0; color: #b71c1c;"><strong>💡 도움말:</strong> 링크가 완전히 복사되었는지 확인해주세요</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

def show_candidate_page(request):
    """면접자 일정 선택 페이지"""
    
    if request.status == Config.Status.CONFIRMED:
        show_confirmed_schedule(request)
        return
    
    if request.status != Config.Status.PENDING_CANDIDATE:
        show_request_status(request)
        return
    
    # 면접자 정보 표시 (개선된 HTML 테이블)
    interviewer_info = get_employee_info(request.interviewer_id)
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%); padding: 30px; border-radius: 15px; margin: 25px 0; border-left: 8px solid #28a745; box-shadow: 0 4px 15px rgba(40,167,69,0.2);">
        <div style="display: flex; align-items: center; margin-bottom: 20px;">
            <div style="font-size: 2.5rem; margin-right: 15px;">👋</div>
            <div>
                <h1 style="color: #155724; margin: 0; font-size: 2rem;">안녕하세요, {request.candidate_name}님!</h1>
                <p style="color: #155724; margin: 10px 0 0 0; font-size: 1.2rem;">면접 일정을 선택해주세요. 아래 정보를 확인하시고 편리한 시간을 선택하시면 됩니다.</p>
            </div>
        </div>
        <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            <thead>
                <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                    <th style="padding: 18px; text-align: left; font-weight: bold; font-size: 16px;">구분</th>
                    <th style="padding: 18px; text-align: left; font-weight: bold; font-size: 16px;">내용</th>
                </tr>
            </thead>
            <tbody>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 18px; font-weight: bold; color: #155724; width: 140px;">💼 포지션</td>
                    <td style="padding: 18px; color: #333; font-size: 1.2rem; font-weight: bold;">{request.position_name}</td>
                </tr>
                <tr>
                    <td style="padding: 18px; font-weight: bold; color: #155724;">👨‍💼 면접관</td>
                    <td style="padding: 18px; color: #333; font-size: 1.1rem;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 18px; font-weight: bold; color: #155724;">📅 요청일</td>
                    <td style="padding: 18px; color: #333;">{request.created_at.strftime('%Y년 %m월 %d일')}</td>
                </tr>
            </tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    st.subheader("🗓️ 제안된 면접 일정 중 선택해주세요")
    
    # 제안된 일정을 개선된 HTML 테이블로 표시
    if request.available_slots:
        slots_html = """
        <div style="margin: 25px 0;">
            <table style="width: 100%; border-collapse: collapse; border: 3px solid #28a745; border-radius: 15px; overflow: hidden; box-shadow: 0 8px 25px rgba(40,167,69,0.3);">
                <thead>
                    <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                        <th style="padding: 25px; text-align: center; font-weight: bold; font-size: 18px;">선택</th>
                        <th style="padding: 25px; text-align: center; font-weight: bold; font-size: 18px;">날짜</th>
                        <th style="padding: 25px; text-align: center; font-weight: bold; font-size: 18px;">시간</th>
                        <th style="padding: 25px; text-align: center; font-weight: bold; font-size: 18px;">소요시간</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, slot in enumerate(request.available_slots):
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            slots_html += f"""
                    <tr style="background-color: {bg_color}; border-bottom: 2px solid #e9ecef; transition: background-color 0.3s ease;">
                        <td style="padding: 25px; text-align: center;">
                            <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 12px 20px; border-radius: 25px; font-size: 16px; font-weight: bold; display: inline-block; box-shadow: 0 4px 10px rgba(40,167,69,0.3);">
                                옵션 {i+1}
                            </div>
                        </td>
                        <td style="padding: 25px; text-align: center; font-weight: bold; font-size: 18px; color: #333;">{format_date_korean(slot.date)}</td>
                        <td style="padding: 25px; text-align: center; font-size: 20px; color: #007bff; font-weight: bold;">{slot.time}</td>
                        <td style="padding: 25px; text-align: center; font-size: 18px; color: #666;">{slot.duration}분</td>
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
                format_func=lambda x: slot_options[x],
                help="가장 편리한 일정을 선택하거나, 다른 일정이 필요한 경우 마지막 옵션을 선택해주세요"
            )
            
            # 다른 일정이 필요한 경우
            candidate_note = ""
            if selected_option == len(slot_options) - 1:
                st.markdown("""
                <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); padding: 25px; border-radius: 12px; border-left: 6px solid #ffc107; margin: 25px 0; box-shadow: 0 4px 15px rgba(255,193,7,0.2);">
                    <h4 style="color: #856404; margin-top: 0; font-size: 1.3rem; display: flex; align-items: center;">
                        <span style="margin-right: 10px;">📝</span> 다른 일정 요청
                    </h4>
                    <p style="color: #856404; margin-bottom: 15px; font-size: 1rem;">제안된 일정이 맞지 않으시나요? 가능한 일정을 구체적으로 알려주세요.</p>
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
                type="primary",
                help="선택한 일정으로 면접을 확정하거나 재조율 요청을 전송합니다"
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
                                    mime="text/calendar",
                                    use_container_width=True,
                                    type="secondary"
                                )
                        except Exception as e:
                            st.info("캘린더 초대장 생성에 실패했지만, 면접 일정은 정상적으로 확정되었습니다.")
                        
                        # 새로고침으로 확정 화면 표시
                        st.rerun()
                    else:
                        st.info("인사팀에서 검토 후 별도 연락드리겠습니다.")
                        st.markdown("""
                        <div style="background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%); padding: 25px; border-radius: 12px; border-left: 6px solid #17a2b8; margin: 25px 0;">
                            <h4 style="color: #0c5460; margin-top: 0; font-size: 1.2rem;">📞 연락처 안내</h4>
                            <p style="color: #0c5460; margin: 0; font-size: 1rem;">급한 사항이 있으시면 인사팀(<a href="mailto:hr@ajnet.co.kr" style="color: #17a2b8;">hr@ajnet.co.kr</a>)으로 연락해주세요.</p>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.error("❌ 면접 일정은 저장되었지만 알림 발송에 실패했습니다.")
    
    else:
        st.error("제안된 면접 일정이 없습니다.")
        st.info("면접관이 아직 가능한 일정을 입력하지 않았습니다. 잠시만 기다려주세요.")

def show_confirmed_schedule(request):
    """확정된 일정 표시 (개선된 디자인)"""
    if not request.selected_slot:
        return
    
    st.markdown("""
    <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); padding: 40px; border-radius: 20px; border-left: 10px solid #28a745; margin: 30px 0; text-align: center; box-shadow: 0 8px 25px rgba(40,167,69,0.3);">
        <div style="font-size: 4rem; margin-bottom: 20px; animation: bounce 2s infinite;">🎉</div>
        <h1 style="color: #155724; margin: 0 0 15px 0; font-size: 2.5rem; font-weight: 300;">면접 일정이 확정되었습니다!</h1>
        <p style="color: #155724; font-size: 1.3rem; margin: 0;">아래 확정된 면접 정보를 확인해주세요.</p>
    </div>
    
    <style>
    @keyframes bounce {
        0%, 20%, 50%, 80%, 100% {
            transform: translateY(0);
        }
        40% {
            transform: translateY(-10px);
        }
        60% {
            transform: translateY(-5px);
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 확정 일정 HTML 테이블 (더욱 개선된 디자인)
    interviewer_info = get_employee_info(request.interviewer_id)
    
    confirmed_html = f"""
    <div style="margin: 40px 0;">
        <table style="width: 100%; border-collapse: collapse; border: 4px solid #28a745; border-radius: 20px; overflow: hidden; box-shadow: 0 12px 30px rgba(40,167,69,0.4);">
            <thead>
                <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                    <th style="padding: 30px; text-align: center; font-size: 24px; font-weight: bold;">구분</th>
                    <th style="padding: 30px; text-align: center; font-size: 24px; font-weight: bold;">내용</th>
                </tr>
            </thead>
            <tbody>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 30px; font-weight: bold; text-align: center; font-size: 20px; color: #28a745;">📅 면접 일시</td>
                    <td style="padding: 30px; text-align: center; font-size: 28px; color: #28a745; font-weight: bold;">
                        {format_date_korean(request.selected_slot.date)} {request.selected_slot.time}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 30px; font-weight: bold; text-align: center; font-size: 20px; color: #28a745;">⏱️ 소요 시간</td>
                    <td style="padding: 30px; text-align: center; font-size: 24px; font-weight: bold;">{request.selected_slot.duration}분</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 30px; font-weight: bold; text-align: center; font-size: 20px; color: #28a745;">👨‍💼 면접관</td>
                    <td style="padding: 30px; text-align: center; font-size: 20px;">{interviewer_info['name']} ({interviewer_info['department']})</td>
                </tr>
                <tr>
                    <td style="padding: 30px; font-weight: bold; text-align: center; font-size: 20px; color: #28a745;">💼 포지션</td>
                    <td style="padding: 30px; text-align: center; font-size: 20px; font-weight: bold;">{request.position_name}</td>
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
    
    # 면접 준비 안내
    st.markdown("""
    <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #2196f3; margin: 40px 0; box-shadow: 0 4px 15px rgba(33,150,243,0.2);">
        <h3 style="color: #1565c0; margin-top: 0; font-size: 1.5rem; display: flex; align-items: center;">
            <span style="margin-right: 15px;">📝</span> 면접 준비 안내
        </h3>
        <div style="display: grid; gap: 15px; margin: 20px 0;">
            <div style="background: white; padding: 20px; border-radius: 10px; border-left: 4px solid #2196f3;">
                <p style="margin: 0; color: #1565c0; font-size: 1.1rem;"><strong>⏰ 면접 당일 10분 전까지 도착</strong>해주시기 바랍니다</p>
            </div>
            <div style="background: white; padding: 20px; border-radius: 10px; border-left: 4px solid #2196f3;">
                <p style="margin: 0; color: #1565c0; font-size: 1.1rem;"><strong>🆔 신분증</strong>과 필요 서류를 지참해주세요</p>
            </div>
            <div style="background: white; padding: 20px; border-radius: 10px; border-left: 4px solid #2196f3;">
                <p style="margin: 0; color: #1565c0; font-size: 1.1rem;">일정 변경이 필요한 경우 <strong>최소 24시간 전</strong>에 인사팀에 연락해주세요</p>
            </div>
            <div style="background: white; padding: 20px; border-radius: 10px; border-left: 4px solid #2196f3;">
                <p style="margin: 0; color: #1565c0; font-size: 1.1rem;">면접 장소나 기타 문의사항은 인사팀으로 연락해주세요</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 연락처 정보
    st.markdown("""
    <div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); padding: 30px; border-radius: 15px; text-align: center; margin: 40px 0; border: 3px solid #dee2e6; box-shadow: 0 6px 20px rgba(0,0,0,0.1);">
        <h3 style="color: #495057; margin-top: 0; font-size: 1.4rem;">📞 문의사항이 있으시면</h3>
        <div style="background: white; padding: 20px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
            <p style="margin: 0; color: #6c757d; font-size: 1.2rem;">인사팀: <a href="mailto:hr@ajnet.co.kr" style="color: #007bff; text-decoration: none; font-weight: bold; font-size: 1.3rem;">hr@ajnet.co.kr</a></p>
        </div>
    </div>
    """, unsafe_allow_html=True)

def show_request_status(request):
    """요청 상태별 안내 페이지"""
    if request.status == Config.Status.PENDING_INTERVIEWER:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); padding: 50px; border-radius: 20px; text-align: center; margin: 40px 0; border-left: 10px solid #ffc107; box-shadow: 0 8px 25px rgba(255,193,7,0.3);">
            <div style="font-size: 5rem; margin-bottom: 25px;">🕐</div>
            <h2 style="color: #856404; margin: 0 0 25px 0; font-size: 2rem;">면접관이 가능한 일정을 입력하는 중입니다</h2>
            <p style="color: #856404; font-size: 1.3rem; margin: 0;">잠시만 기다려주세요. 면접관이 일정을 입력하면 자동으로 알림을 받게 됩니다.</p>
        </div>
        """, unsafe_allow_html=True)
        
    elif request.status == Config.Status.PENDING_CONFIRMATION:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%); padding: 50px; border-radius: 20px; text-align: center; margin: 40px 0; border-left: 10px solid #17a2b8; box-shadow: 0 8px 25px rgba(23,162,184,0.3);">
            <div style="font-size: 5rem; margin-bottom: 25px;">📋</div>
            <h2 style="color: #0c5460; margin: 0 0 25px 0; font-size: 2rem;">인사팀에서 일정을 재조율하고 있습니다</h2>
            <p style="color: #0c5460; font-size: 1.3rem; margin: 0;">곧 연락드리겠습니다. 급한 사항이 있으시면 인사팀에 연락해주세요.</p>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()