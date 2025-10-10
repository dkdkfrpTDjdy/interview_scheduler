import streamlit as st
from datetime import datetime
import sys
import os

# 상위 디렉터리의 모듈들을 import하기 위해 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager
from email_service import EmailService
from models import InterviewSlot
from config import Config
from utils import format_date_korean, get_employee_info

# 페이지 설정
st.set_page_config(
    page_title="면접관 일정 입력 - AI 면접 시스템",
    page_icon="👨‍💼",
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
    st.title("👨‍💼 면접 가능 일정 입력")
    st.caption("면접관 전용 페이지")
    
    # URL 파라미터에서 요청 ID 가져오기
    query_params = st.query_params
    request_id = query_params.get('id', None)
    
    if not request_id:
        show_access_guide()
        return
    
    show_interviewer_page(request_id)

def show_access_guide():
    """접근 안내 페이지"""
    st.markdown("""
    <div style="text-align: center; padding: 50px; background-color: #f8f9fa; border-radius: 10px; margin: 20px 0;">
        <h2 style="color: #6c757d;">🔒 인증이 필요합니다</h2>
        <p style="font-size: 18px; color: #495057; margin: 20px 0;">이 페이지는 면접관 전용 페이지입니다.</p>
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

def show_interviewer_page(request_id: str):
    """면접관 일정 입력 페이지"""
    request = db.get_interview_request(request_id)
    
    if not request:
        st.error("❌ 유효하지 않은 요청입니다.")
        st.info("이메일의 링크가 올바른지 확인하거나 인사팀에 문의해주세요.")
        return
    
    if request.status != Config.Status.PENDING_INTERVIEWER:
        st.warning(f"⚠️ 이미 처리된 요청입니다.")
        
        if request.status == Config.Status.PENDING_CANDIDATE:
            st.info("✅ 면접자가 일정을 선택하는 중입니다.")
        elif request.status == Config.Status.CONFIRMED:
            st.success(f"🎉 면접 일정이 확정되었습니다!")
            if request.selected_slot:
                st.info(f"**확정 일시:** {format_date_korean(request.selected_slot.date)} {request.selected_slot.time}")
        elif request.status == Config.Status.PENDING_CONFIRMATION:
            st.info("📋 인사팀에서 일정을 재조율하고 있습니다.")
        return
    
    # 면접 정보 표시
    st.markdown(f"""
    <div style="background-color: #e3f2fd; padding: 25px; border-radius: 10px; margin: 20px 0; border-left: 6px solid #2196f3;">
        <h3 style="color: #1565c0; margin-top: 0;">📋 면접 요청 정보</h3>
        <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
            <tr>
                <td style="padding: 8px 0; font-weight: bold; width: 120px; color: #1565c0;">포지션</td>
                <td style="padding: 8px 0; color: #1565c0; font-weight: bold;">{request.position_name}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #1565c0;">면접자</td>
                <td style="padding: 8px 0; color: #1565c0;">{request.candidate_name}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #1565c0;">이메일</td>
                <td style="padding: 8px 0; color: #1565c0;">{request.candidate_email}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #1565c0;">요청일</td>
                <td style="padding: 8px 0; color: #1565c0;">{request.created_at.strftime('%Y년 %m월 %d일')}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    # 인사팀에서 제안한 희망일시 표시 (HTML 테이블)
    if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
        st.subheader("🌟 인사팀에서 제안한 면접 희망일시")
        
        # HTML 테이블로 표시
        table_html = """
        <div style="margin: 20px 0;">
            <table style="width: 100%; border-collapse: collapse; border: 2px solid #0078d4; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <thead>
                    <tr style="background-color: #0078d4; color: white;">
                        <th style="padding: 15px; text-align: center; font-weight: bold;">번호</th>
                        <th style="padding: 15px; text-align: center; font-weight: bold;">날짜</th>
                        <th style="padding: 15px; text-align: center; font-weight: bold;">시간</th>
                        <th style="padding: 15px; text-align: center; font-weight: bold;">비고</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, datetime_slot in enumerate(request.preferred_datetime_slots, 1):
            if "면접관선택" in datetime_slot:
                date_part = datetime_slot.split(' ')[0]
                time_note = "면접관이 시간 선택"
                time_display = "09:00~17:00 중 선택"
                time_color = "#dc3545"
            else:
                date_part, time_part = datetime_slot.split(' ')
                time_note = "시간 고정"
                time_display = time_part
                time_color = "#28a745"
            
            bg_color = "#f8f9fa" if i % 2 == 0 else "white"
            table_html += f"""
                    <tr style="background-color: {bg_color};">
                        <td style="padding: 15px; text-align: center; font-weight: bold; font-size: 16px;">{i}</td>
                        <td style="padding: 15px; text-align: center; font-weight: bold;">{format_date_korean(date_part)}</td>
                        <td style="padding: 15px; text-align: center; color: {time_color}; font-weight: bold; font-size: 15px;">{time_display}</td>
                        <td style="padding: 15px; text-align: center; font-size: 12px; color: #666; font-style: italic;">{time_note}</td>
                    </tr>
            """
        
        table_html += """
                </tbody>
            </table>
        </div>
        """
        
        st.markdown(table_html, unsafe_allow_html=True)
    
    st.subheader("⏰ 가능한 면접 일정을 선택해주세요")
    st.info("💡 **안내:** 인사팀이 제안한 일정 중에서만 선택 가능하며, 여러 개 선택할 수 있습니다.")
    
    with st.form("interviewer_schedule"):
        selected_slots = []
        
        # 인사팀 제안 일시만 선택 가능하도록 제한
        if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
            st.write("**제안된 일시 중 가능한 시간을 모두 선택해주세요:**")
            
            for i, datetime_slot in enumerate(request.preferred_datetime_slots):
                st.markdown(f"### 옵션 {i+1}")
                
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
        submitted = st.form_submit_button("📧 면접자에게 일정 전송", use_container_width=True, type="primary")
        
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
                        <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <thead>
                                <tr style="background-color: #28a745; color: white;">
                                    <th style="padding: 15px; text-align: center; font-weight: bold;">번호</th>
                                    <th style="padding: 15px; text-align: center; font-weight: bold;">날짜</th>
                                    <th style="padding: 15px; text-align: center; font-weight: bold;">시간</th>
                                    <th style="padding: 15px; text-align: center; font-weight: bold;">소요시간</th>
                                </tr>
                            </thead>
                            <tbody>
                    """
                    
                    for i, slot in enumerate(selected_slots, 1):
                        bg_color = "#f8f9fa" if i % 2 == 0 else "white"
                        preview_html += f"""
                                <tr style="background-color: {bg_color};">
                                    <td style="padding: 15px; text-align: center; font-weight: bold;">{i}</td>
                                    <td style="padding: 15px; text-align: center;">{format_date_korean(slot.date)}</td>
                                    <td style="padding: 15px; text-align: center; color: #28a745; font-weight: bold;">{slot.time}</td>
                                    <td style="padding: 15px; text-align: center;">{slot.duration}분</td>
                                </tr>
                        """
                    
                    preview_html += """
                            </tbody>
                        </table>
                    </div>
                    """
                    
                    st.markdown(preview_html, unsafe_allow_html=True)
                    
                    # 완료 안내
                    st.markdown("""
                    <div style="background-color: #d4edda; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745; margin: 20px 0;">
                        <h4 style="color: #155724; margin-top: 0;">🎉 완료되었습니다!</h4>
                        <p style="color: #155724; margin: 0;">면접자가 일정을 선택하면 확정 알림을 받게 됩니다.</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error("면접 일정은 저장되었지만 이메일 발송에 실패했습니다.")
    
    # 연락처 정보
    st.markdown("---")
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; margin: 30px 0; border: 1px solid #dee2e6;">
        <h4 style="color: #495057; margin-top: 0;">📞 문의사항이 있으시면</h4>
        <p style="margin: 0; color: #6c757d;">인사팀: <a href="mailto:hr@ajnet.co.kr" style="color: #007bff;">hr@ajnet.co.kr</a></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
