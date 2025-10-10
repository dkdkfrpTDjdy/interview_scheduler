import streamlit as st
from datetime import datetime
from models import InterviewSlot
from config import Config
from utils import format_date_korean, get_employee_info

def show_interviewer_page(request_id: str, db, email_service):
    """면접관 일정 입력 페이지 (개선됨)"""
    request = db.get_interview_request(request_id)
    
    if not request:
        st.error("❌ 유효하지 않은 요청입니다.")
        return
    
    if request.status != Config.Status.PENDING_INTERVIEWER:
        st.warning(f"⚠️ 이미 처리된 요청입니다. (현재 상태: {request.status})")
        return
    
    st.header("📅 면접 가능 일정 입력")
    
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
                else:
                    st.error("면접 일정은 저장되었지만 이메일 발송에 실패했습니다.")