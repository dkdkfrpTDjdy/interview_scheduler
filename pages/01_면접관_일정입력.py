import streamlit as st
import pandas as pd
import os
from datetime import datetime
import sys
import time  # 추가
import logging  # 추가

# 부모 디렉토리를 Python 경로에 추가
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from database import DatabaseManager
from email_service import EmailService
from models import InterviewSlot, TimeRange
from config import Config
from utils import format_date_korean, get_employee_info

# 로거 설정 추가
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="면접관 일정 입력 - AI 면접 시스템",
    page_icon="👨‍💼",
    layout="wide"
)

@st.cache_resource
def init_services():
    db = DatabaseManager()
    email_service = EmailService()
    return db, email_service

db, email_service = init_services()

def main():
    st.title("👨‍💼 면접관 일정 입력")
    
    if 'authenticated_interviewer' not in st.session_state:
        show_login_form()
    else:
        show_interviewer_dashboard()

def show_login_form():
    """면접관 사번 입력 폼"""
    st.markdown("""
    <div style="background-color: #1A1A1A;
                color: white;
                padding: 10px;
                border-radius: 12px;
                text-align: center;
                margin: 15px 0;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);">
        <div style="font-size: 2rem; margin-bottom: 10px;">🔐</div>
        <h1 style="margin: 0 0 10px 0; font-size: 1.5rem; font-weight: 400;">면접관 인증</h1>
        <p style="font-size: 0.95rem; opacity: 0.9; margin: 0;">면접 요청을 확인하세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("interviewer_login"):
            employee_id = st.text_input(
                label="사번 입력",
                placeholder="예: 223286"
            )
            
            submitted = st.form_submit_button("🔍 면접 요청 확인", type="primary")
            
            if submitted:
                if not employee_id.strip():
                    st.error("사번을 입력해주세요.")
                else:
                    interviewer_info = get_employee_info(employee_id)
                    
                    is_valid = (interviewer_info['employee_id'] == employee_id)
                    
                    if is_valid:
                        grouped_requests = find_pending_requests_by_position(employee_id)
                        
                        if grouped_requests:
                            st.session_state.authenticated_interviewer = employee_id
                            st.session_state.interviewer_info = interviewer_info
                            st.session_state.grouped_requests = grouped_requests
                            st.rerun()
                        else:
                            st.warning("현재 처리할 면접 요청이 없습니다.")
                    else:
                        st.error("등록되지 않은 사번입니다. 인사팀에 문의해주세요.")
    
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="background-color: #f8f9fa; padding: 25px; border-radius: 12px; text-align: center; border: 1px solid #dee2e6;">
            <h4 style="color: #495057; margin-top: 0;">이용 안내</h4>
            <div style="text-align: left; margin: 15px 0;">
                <p style="margin: 8px 0; color: #6c757d;">• <strong>사번</strong>을 정확히 입력하세요</p>
                <p style="margin: 8px 0; color: #6c757d;">• 예정된 면접이 표시됩니다</p>
            </div>
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 15px;">
                <p style="margin: 0; color: #1565c0;"><strong>📞 기타 문의:</strong> <a href="mailto:hr@ajnet.co.kr">hr@ajnet.co.kr</a></p>
            </div>
        </div>
        """, unsafe_allow_html=True)

def find_pending_requests_by_position(employee_id: str):
    """면접관의 대기 중인 요청을 공고별로 그룹핑"""
    try:
        all_requests = db.get_all_requests()
        grouped = {}
        
        for request in all_requests:
            interviewer_ids = [id.strip() for id in request.interviewer_id.split(',')]
            
            if employee_id in interviewer_ids and request.status == Config.Status.PENDING_INTERVIEWER:
                position_name = request.position_name
                
                if position_name not in grouped:
                    grouped[position_name] = {
                        'requests': [],
                        'preferred_datetime_slots': request.preferred_datetime_slots
                    }
                
                grouped[position_name]['requests'].append(request)
        
        return grouped
    except Exception as e:
        st.error(f"요청 조회 중 오류가 발생했습니다: {e}")
        return {}

def show_interviewer_dashboard():
    """면접관 대시보드"""
    interviewer_info = st.session_state.interviewer_info
    grouped_requests = st.session_state.grouped_requests

    if not grouped_requests:
        st.markdown("""
        <div style="text-align: center; margin: 30px 0;">
            <h3 style="color: #1A1A1A; margin: 0 0 15px 0;">모든 면접 일정을 처리하였습니다</h3>
        </div>
        """, unsafe_allow_html=True)
        return

    st.subheader(f"📋 {interviewer_info['name']} ({interviewer_info['department']}) 님의 대기 중인 면접 공고 ({len(grouped_requests)}건)")

    for i, (position_name, group_data) in enumerate(grouped_requests.items()):
        requests = group_data['requests']
        candidate_count = len(requests)
        
        with st.expander(
            f"📅 {position_name} - {candidate_count}명의 면접자", 
            expanded=len(grouped_requests) == 1
        ):
            show_position_detail(position_name, group_data, i)

def parse_datetime_slot(datetime_slot: str) -> dict:
    """datetime_slot 파싱"""
    try:
        parts = datetime_slot.split(' ')
        date_part = parts[0]
        time_range = parts[1] if len(parts) > 1 else None
        
        if time_range and '~' in time_range:
            start_time, end_time = time_range.split('~')
            return {
                'date': date_part,
                'start_time': start_time,
                'end_time': end_time
            }
        else:
            return None
    except Exception as e:
        return None

def show_position_detail(position_name: str, group_data: dict, index: int):
    """공고별 상세 정보 및 통합 일정 선택"""
    
    requests = group_data['requests']
    preferred_datetime_slots = group_data['preferred_datetime_slots']
    
    first_request = requests[0]
    current_interviewer_id = st.session_state.authenticated_interviewer
    
    interviewer_ids = [id.strip() for id in first_request.interviewer_id.split(',')]
    sorted_interviewers = "_".join(sorted(interviewer_ids))
    group_key = f"{position_name}_{sorted_interviewers}"

    is_multiple_interviewers = len(interviewer_ids) > 1
    
    # ✅ 현재 응답 현황 확인 (에러 처리 강화)
    try:
        all_responded, responded_count, total_count = db.check_all_interviewers_responded(first_request)
    except Exception as e:
        st.error(f"응답 현황 확인 중 오류: {e}")
        all_responded = False
        responded_count = 0
        total_count = len(interviewer_ids)
    
    st.markdown(f"""
    <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid #0078d4; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,120,212,0.1);">
        <h4 style="color: #1A1A1A; margin: 0 0 15px 0;">📋 공고 정보</h4>
    
        <table style="width: 100%; border-collapse: collapse; text-align: center;">
            <tbody>
                <tr>
                    <td style="padding: 10px 0; font-weight: bold; color: #1A1A1A; width: 120px;">공고명</td>
                    <td style="padding: 10px 0; color: #333;">{position_name}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 0; font-weight: bold; color: #1A1A1A;">면접자 수</td>
                    <td style="padding: 10px 0; color: #333;">{len(requests)}명</td>
                </tr>
                <tr>
                    <td style="padding: 10px 0; font-weight: bold; color: #1A1A1A;">면접관 응답</td>
                    <td style="padding: 10px 0; color: #EF3340;">{responded_count}/{total_count}명 완료</td>
                </tr>
            </tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    if is_multiple_interviewers:
        st.info(f"""
        💡 **공동 면접 안내**
        
        이 공고는 **{total_count}명의 면접관**이 함께 진행합니다.
        - 현재 **{responded_count}명**이 일정을 입력했습니다.
        - 모든 면접관이 일정을 입력하면 **공통 일정**만 면접자에게 전송됩니다.
        """)
    
    st.markdown("**👥 면접자 목록**")
    candidate_data = []
    for i, req in enumerate(requests, 1):
        candidate_data.append({
            "번호": i,
            "이름": req.candidate_name,
            "이메일": req.candidate_email,
            "신청일": req.created_at.strftime('%Y-%m-%d')
        })
    
    st.dataframe(pd.DataFrame(candidate_data), use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    st.write("**아래에서 이 공고의 면접 가능한 날짜를 선택해 주세요**")
    
    with st.form(f"interviewer_schedule_{index}"):
        selected_datetime_slots = []
        
        if preferred_datetime_slots:
            st.markdown("**📅 인사팀이 지정한 면접 희망 일정**")
            
            schedule_data = []
            for i, datetime_slot in enumerate(preferred_datetime_slots, 1):
                parsed = parse_datetime_slot(datetime_slot)
                if parsed:
                    schedule_data.append({
                        "번호": i,
                        "날짜": format_date_korean(parsed['date']),
                        "시간": f"{parsed['start_time']} ~ {parsed['end_time']}"
                    })
            
            if schedule_data:
                df = pd.DataFrame(schedule_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.markdown("**✅ 가능한 날짜를 선택해주세요**")
            
            for i, datetime_slot in enumerate(preferred_datetime_slots):
                parsed = parse_datetime_slot(datetime_slot)
                
                if parsed:
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        is_selected = st.checkbox(
                            f"📅 {format_date_korean(parsed['date'])} - {parsed['start_time']} ~ {parsed['end_time']}",
                            key=f"date_check_{index}_{i}",
                            help="해당 날짜/시간이 가능하면 선택해주세요"
                        )
                    
                    with col2:
                        if is_selected:
                            start_hour, start_min = map(int, parsed['start_time'].split(':'))
                            end_hour, end_min = map(int, parsed['end_time'].split(':'))
                            total_minutes = (end_hour * 60 + end_min) - (start_hour * 60 + start_min)
                            slot_count = total_minutes // 30
                            st.markdown(
                                f'<div style="margin-top:8px;color:#4caf50;font-weight:bold;">{slot_count}개</div>',
                                unsafe_allow_html=True
                            )
                    
                    if is_selected:
                        selected_datetime_slots.append(datetime_slot)
        
        if selected_datetime_slots:
            st.markdown("---")
            st.write("**✅ 선택된 시간대:**")
            
            all_generated_slots = []
            for datetime_slot in selected_datetime_slots:
                parsed = parse_datetime_slot(datetime_slot)
                if parsed:
                    from models import TimeRange
                    time_range = TimeRange(
                        date=parsed['date'],
                        start_time=parsed['start_time'],
                        end_time=parsed['end_time']
                    )
                    slots = time_range.generate_30min_slots()
                    all_generated_slots.extend(slots)
            
            preview_data = []
            for i, slot in enumerate(all_generated_slots, 1):
                preview_data.append({
                    "번호": i,
                    "날짜": format_date_korean(slot.date),
                    "시간": slot.time,
                    "소요시간": "30분"
                })
            
            st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)
            

        col1, col2, col3 = st.columns([6, 1, 1])
        
        with col3:
            submitted = st.form_submit_button("일정 확정", use_container_width=True)

        if submitted:
            if not selected_datetime_slots:
                st.error("최소 1개 이상의 날짜를 선택해주세요.")
            else:
                try:
                    # 30분 단위 시간 생성
                    all_slots = []
                    for datetime_slot in selected_datetime_slots:
                        parsed = parse_datetime_slot(datetime_slot)
                        if parsed:
                            from models import TimeRange
                            time_range = TimeRange(
                                date=parsed['date'],
                                start_time=parsed['start_time'],
                                end_time=parsed['end_time']
                            )
                            slots = time_range.generate_30min_slots()
                            all_slots.extend(slots)
                    
                    # 모든 요청에 대해 면접관 응답 저장
                    for request in requests:
                        try:
                            db.save_interviewer_response(
                                request_id=request.id,
                                interviewer_id=current_interviewer_id,
                                slots=all_slots
                            )
                        except Exception as e:
                            st.error(f"❌ {request.candidate_name} 응답 저장 실패: {e}")
                    
                    if len(interviewer_ids) == 1:
                        # ✅ 단일 면접관: 즉시 상태 변경 (면접자 메일 발송 안함!)
                        for request in requests:
                            try:
                                request.available_slots = all_slots.copy()
                                request.status = Config.Status.PENDING_CANDIDATE
                                request.updated_at = datetime.now()
                                
                                db.save_interview_request(request)
                                db.update_google_sheet(request)
                                
                                st.write(f"✅ {request.candidate_name} 상태 변경 완료")
                            except Exception as e:
                                st.error(f"❌ {request.candidate_name} 처리 오류: {e}")
                    else:
                        # ✅ 복수 면접관: 모두 응답했는지 확인
                        for request in requests:
                            try:
                                all_responded, responded_count, total_count = db.check_all_interviewers_responded(request)
                                
                                if all_responded:
                                    common_slots = db.get_common_available_slots(request)
                                    
                                    if common_slots:
                                        request.available_slots = common_slots.copy()
                                        request.status = Config.Status.PENDING_CANDIDATE
                                        request.updated_at = datetime.now()
                                        
                                        db.save_interview_request(request)
                                        db.update_google_sheet(request)
                                        
                                        st.write(f"✅ {request.candidate_name} 공통 시간 저장 완료")
                            except Exception as e:
                                st.error(f"❌ {request.candidate_name} 처리 오류: {e}")
                    
                    # ✅ HR 알림만 발송 (면접자에게는 발송 안함!)
                    try:
                        hr_notification_sent = email_service.send_hr_notification_on_interviewer_completion(
                            group_key=group_key,
                            position_name=position_name,
                            candidate_count=len(requests)
                        )
            
                        if hr_notification_sent:
                            st.success("🎉 일정 제출 완료! 모든 면접관이 완료되어 인사팀에게 알림을 보냈습니다.")
                            st.info("💡 인사팀에서 '면접자 메일 발송' 탭에서 직접 메일을 발송할 예정입니다.")
                            st.balloons()
                        else:
                            st.success("✅ 일정 제출 완료! 다른 면접관들의 일정 선택을 기다리고 있습니다.")
                            st.info("💡 모든 면접관이 완료되면 인사팀에 알림이 갑니다.")
                        
                    except Exception as e:
                        logger.error(f"HR 알림 처리 중 오류: {e}")
                        st.success("✅ 일정 제출 완료!")
                        st.info("💡 인사팀에 별도로 연락하여 진행 상황을 알려주세요.")
                    
                    # 세션 정리
                    if 'grouped_requests' in st.session_state:
                        if position_name in st.session_state.grouped_requests:
                            del st.session_state.grouped_requests[position_name]
                    
                    time.sleep(2)
                    st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ 처리 중 오류: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())

if __name__ == "__main__":

    main()








