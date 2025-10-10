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
    
    # 🔧 개선된 접근 제어: URL 파라미터 확인
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
    
    show_interviewer_page(request)

def show_access_guide():
    """접근 안내 페이지 (개선된 디자인)"""
    st.markdown("""
    <div style="text-align: center; padding: 80px 40px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 15px; margin: 40px 0; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
        <div style="font-size: 80px; margin-bottom: 20px;">🔒</div>
        <h1 style="margin: 0 0 20px 0; font-size: 2.5rem; font-weight: 300;">면접관 전용 페이지</h1>
        <p style="font-size: 1.2rem; margin: 20px 0; opacity: 0.9;">이메일로 받으신 링크를 통해 접속해주세요</p>
        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; margin-top: 30px;">
            <p style="margin: 0; font-size: 1rem;">🔗 올바른 링크 형식: <code>...면접관_일정입력?id=요청ID</code></p>
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
            <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 20px;">
                <p style="margin: 0; color: #1565c0;"><strong>📞 인사팀 연락처:</strong> <a href="mailto:hr@ajnet.co.kr" style="color: #1976d2;">hr@ajnet.co.kr</a></p>
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

def show_interviewer_page(request):
    """면접관 일정 입력 페이지 (시간 선택 기능 강화)"""
    
    if request.status != Config.Status.PENDING_INTERVIEWER:
        show_request_status(request)
        return
    
    # 면접관 정보 표시
    interviewer_info = get_employee_info(request.interviewer_id)
    
    # 면접 정보 표시 (개선된 HTML 테이블)
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 30px; border-radius: 15px; margin: 25px 0; border-left: 8px solid #2196f3; box-shadow: 0 4px 15px rgba(33,150,243,0.2);">
        <div style="display: flex; align-items: center; margin-bottom: 20px;">
            <div style="font-size: 2rem; margin-right: 15px;">👋</div>
            <div>
                <h2 style="color: #1565c0; margin: 0; font-size: 1.8rem;">안녕하세요, {interviewer_info['name']}님!</h2>
                <p style="color: #1976d2; margin: 5px 0 0 0; font-size: 1rem;">({interviewer_info['department']})</p>
            </div>
        </div>
        <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <thead>
                <tr style="background: linear-gradient(135deg, #2196f3 0%, #1976d2 100%); color: white;">
                    <th style="padding: 15px; text-align: left; font-weight: bold;">구분</th>
                    <th style="padding: 15px; text-align: left; font-weight: bold;">내용</th>
                </tr>
            </thead>
            <tbody>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 15px; font-weight: bold; color: #1565c0; width: 120px;">📋 포지션</td>
                    <td style="padding: 15px; color: #333; font-size: 1.1rem; font-weight: bold;">{request.position_name}</td>
                </tr>
                <tr>
                    <td style="padding: 15px; font-weight: bold; color: #1565c0;">👤 면접자</td>
                    <td style="padding: 15px; color: #333;">{request.candidate_name}</td>
                </tr>
                <tr style="background-color: #f8f9fa;">
                    <td style="padding: 15px; font-weight: bold; color: #1565c0;">📧 이메일</td>
                    <td style="padding: 15px; color: #333; font-size: 0.9rem;">{request.candidate_email}</td>
                </tr>
                <tr>
                    <td style="padding: 15px; font-weight: bold; color: #1565c0;">📅 요청일</td>
                    <td style="padding: 15px; color: #333;">{request.created_at.strftime('%Y년 %m월 %d일 %H:%M')}</td>
                </tr>
            </tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    # 인사팀에서 제안한 희망일시 표시 (개선된 HTML 테이블)
    if hasattr(request, 'preferred_datetime_slots') and request.preferred_datetime_slots:
        st.subheader("⭐ 인사팀에서 제안한 면접 희망일시")
        
        table_html = """
        <div style="margin: 25px 0;">
            <table style="width: 100%; border-collapse: collapse; border: 3px solid #ffc107; border-radius: 12px; overflow: hidden; box-shadow: 0 6px 20px rgba(255,193,7,0.3);">
                <thead>
                    <tr style="background: linear-gradient(135deg, #ffc107 0%, #ffb300 100%); color: #212529;">
                        <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">번호</th>
                        <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">날짜</th>
                        <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">시간</th>
                        <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">상태</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, datetime_slot in enumerate(request.preferred_datetime_slots, 1):
            bg_color = "#fffbf0" if i % 2 == 1 else "#fff8e1"
            
            if "면접관선택" in datetime_slot:
                date_part = datetime_slot.split(' ')[0]
                time_display = "09:00~17:00 중 선택"
                status = "시간 선택 필요"
                time_color = "#dc3545"
                status_color = "#dc3545"
            else:
                date_part, time_part = datetime_slot.split(' ')
                time_display = time_part
                status = "시간 고정"
                time_color = "#28a745"
                status_color = "#28a745"
            
            table_html += f"""
                    <tr style="background-color: {bg_color}; border-bottom: 1px solid #f0c14b;">
                        <td style="padding: 18px; text-align: center; font-weight: bold; font-size: 18px; color: #856404;">{i}</td>
                        <td style="padding: 18px; text-align: center; font-weight: bold; font-size: 16px;">{format_date_korean(date_part)}</td>
                        <td style="padding: 18px; text-align: center; font-weight: bold; color: {time_color}; font-size: 16px;">{time_display}</td>
                        <td style="padding: 18px; text-align: center; font-size: 14px; color: {status_color}; font-weight: bold;">{status}</td>
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
                st.markdown(f"### 📅 옵션 {i+1}")
                
                if "면접관선택" in datetime_slot:
                    # 면접관이 시간을 직접 선택해야 하는 경우
                    date_part = datetime_slot.split(' ')[0]
                    
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        is_selected = st.checkbox(
                            f"📅 {format_date_korean(date_part)} (시간 선택 필요)",
                            key=f"slot_{i}",
                            help="이 날짜를 선택하고 원하는 시간을 지정해주세요"
                        )
                    
                    with col2:
                        selected_time = st.selectbox(
                            "⏰ 시간 선택",
                            options=["선택안함"] + Config.TIME_SLOTS,
                            key=f"time_select_{i}",
                            disabled=not is_selected,
                            help="면접 시작 시간을 선택해주세요"
                        )
                    
                    with col3:
                        duration = st.selectbox(
                            "⏱️ 소요시간",
                            options=[30, 60, 90, 120],
                            index=1,
                            format_func=lambda x: f"{x}분",
                            key=f"duration_{i}",
                            disabled=not is_selected,
                            help="예상 면접 소요 시간"
                        )
                    
                    if is_selected and selected_time != "선택안함":
                        selected_slots.append(InterviewSlot(date_part, selected_time, duration))
                        
                else:
                    # 시간이 고정된 경우
                    date_part, time_part = datetime_slot.split(' ')
                    
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        is_selected = st.checkbox(
                            f"📅 {format_date_korean(date_part)} {time_part}",
                            key=f"slot_{i}",
                            help="이 일정이 가능하면 선택해주세요"
                        )
                    
                    with col2:
                        st.markdown(f"**⏰ {time_part}** (고정)")
                    
                    with col3:
                        duration = st.selectbox(
                            "⏱️ 소요시간",
                            options=[30, 60, 90, 120],
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
        submitted = st.form_submit_button(
            "📧 면접자에게 일정 전송", 
            use_container_width=True, 
            type="primary",
            help="선택한 일정을 면접자에게 전송합니다"
        )
        
        if submitted:
            if not selected_slots:
                st.error("❌ 최소 1개 이상의 면접 일정을 선택해주세요.")
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
                    
                    # 선택된 일정 미리보기 (개선된 HTML 테이블)
                    st.subheader("📋 전송된 면접 일정")
                    
                    preview_html = """
                    <div style="margin: 25px 0;">
                        <table style="width: 100%; border-collapse: collapse; border: 3px solid #28a745; border-radius: 12px; overflow: hidden; box-shadow: 0 6px 20px rgba(40,167,69,0.3);">
                            <thead>
                                <tr style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white;">
                                    <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">번호</th>
                                    <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">날짜</th>
                                    <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">시간</th>
                                    <th style="padding: 20px; text-align: center; font-weight: bold; font-size: 16px;">소요시간</th>
                                </tr>
                            </thead>
                            <tbody>
                    """
                    
                    for i, slot in enumerate(selected_slots, 1):
                        bg_color = "#f8f9fa" if i % 2 == 0 else "white"
                        preview_html += f"""
                                <tr style="background-color: {bg_color}; border-bottom: 1px solid #dee2e6;">
                                    <td style="padding: 18px; text-align: center; font-weight: bold; font-size: 18px; color: #28a745;">{i}</td>
                                    <td style="padding: 18px; text-align: center; font-weight: bold; font-size: 16px;">{format_date_korean(slot.date)}</td>
                                    <td style="padding: 18px; text-align: center; color: #28a745; font-weight: bold; font-size: 16px;">{slot.time}</td>
                                    <td style="padding: 18px; text-align: center; font-size: 16px;">{slot.duration}분</td>
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
                    <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #28a745; margin: 30px 0; text-align: center; box-shadow: 0 4px 15px rgba(40,167,69,0.2);">
                        <div style="font-size: 3rem; margin-bottom: 15px;">🎉</div>
                        <h3 style="color: #155724; margin: 0 0 15px 0; font-size: 1.5rem;">완료되었습니다!</h3>
                        <p style="color: #155724; margin: 0; font-size: 1.1rem;">면접자가 일정을 선택하면 확정 알림을 받게 됩니다.</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error("❌ 면접 일정은 저장되었지만 이메일 발송에 실패했습니다.")
    
    # 연락처 정보
    st.markdown("---")
    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 25px; border-radius: 12px; text-align: center; margin: 30px 0; border: 2px solid #dee2e6; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
        <h4 style="color: #495057; margin-top: 0; font-size: 1.2rem;">📞 문의사항이 있으시면</h4>
        <p style="margin: 0; color: #6c757d; font-size: 1.1rem;">인사팀: <a href="mailto:hr@ajnet.co.kr" style="color: #007bff; text-decoration: none; font-weight: bold;">hr@ajnet.co.kr</a></p>
    </div>
    """, unsafe_allow_html=True)

def show_request_status(request):
    """요청 상태별 안내 페이지"""
    if request.status == Config.Status.PENDING_CANDIDATE:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); padding: 40px; border-radius: 15px; text-align: center; margin: 30px 0; border-left: 8px solid #ffc107;">
            <div style="font-size: 4rem; margin-bottom: 20px;">⏳</div>
            <h2 style="color: #856404; margin: 0 0 20px 0;">면접자가 일정을 선택하는 중입니다</h2>
            <p style="color: #856404; font-size: 1.2rem;">면접자가 일정을 선택하면 자동으로 알림을 받게 됩니다.</p>
        </div>
        """, unsafe_allow_html=True)
        
    elif request.status == Config.Status.CONFIRMED:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); padding: 40px; border-radius: 15px; text-align: center; margin: 30px 0; border-left: 8px solid #28a745;">
            <div style="font-size: 4rem; margin-bottom: 20px;">🎉</div>
            <h2 style="color: #155724; margin: 0 0 20px 0;">면접 일정이 확정되었습니다!</h2>
            {f'<p style="color: #155724; font-size: 1.3rem; font-weight: bold;">📅 확정 일시: {format_date_korean(request.selected_slot.date)} {request.selected_slot.time}</p>' if request.selected_slot else ''}
        </div>
        """, unsafe_allow_html=True)
        
    elif request.status == Config.Status.PENDING_CONFIRMATION:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%); padding: 40px; border-radius: 15px; text-align: center; margin: 30px 0; border-left: 8px solid #17a2b8;">
            <div style="font-size: 4rem; margin-bottom: 20px;">📋</div>
            <h2 style="color: #0c5460; margin: 0 0 20px 0;">인사팀에서 일정을 재조율하고 있습니다</h2>
            <p style="color: #0c5460; font-size: 1.2rem;">면접자가 다른 일정을 요청하여 재조율 중입니다.</p>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
