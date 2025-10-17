
import streamlit as st
import os
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import time

# 🔧 면접자 앱임을 명시
os.environ["APP_TYPE"] = "candidate"

# 페이지 설정을 맨 처음에 실행
st.set_page_config(
    page_title="면접 일정 선택 - AI 면접 시스템",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ✅ 전역 CSS 스타일 적용
st.markdown("""
<style>
    /* 전역 폰트 및 배경 */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    
    * {
        font-family: 'Noto Sans KR', sans-serif;
    }
    
    .main {
        background-color: #efeff1;
    }
    
    /* Streamlit 기본 요소 숨기기 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 입력 필드 스타일 */
    .stTextInput > div > div > input {
        border: 2px solid #e7e7e7;
        border-radius: 8px;
        padding: 12px;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #EF3340;
        box-shadow: 0 0 0 2px rgba(239, 51, 64, 0.1);
    }
    
    /* 텍스트 영역 스타일 */
    .stTextArea > div > div > textarea {
        border: 2px solid #e7e7e7;
        border-radius: 8px;
        padding: 12px;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    
    .stTextArea > div > div > textarea:focus {
        border-color: #EF3340;
        box-shadow: 0 0 0 2px rgba(239, 51, 64, 0.1);
    }
    
    /* 셀렉트박스 스타일 */
    .stSelectbox > div > div > div {
        border: 2px solid #e7e7e7;
        border-radius: 8px;
        background-color: white;
    }
    
    .stSelectbox > div > div > div:hover {
        border-color: #EF3340;
    }
    
    /* 폼 제출 버튼 */
    div.stFormSubmitButton > button,
    div[data-testid="stFormSubmitButton"] > button {
        background-color: #EF3340 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        padding: 0.6em 1.5em !important;
        transition: all 0.3s ease !important;
        font-size: 1rem !important;
    }
    
    div.stFormSubmitButton > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: #d42a36 !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(239, 51, 64, 0.3);
    }
    
    /* 일반 버튼 (Primary) */
    .stButton > button[kind="primary"] {
        background-color: #EF3340 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        padding: 0.6em 1.5em !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        background-color: #d42a36 !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(239, 51, 64, 0.3);
    }
    
    /* 일반 버튼 (Secondary) */
    .stButton > button {
        background-color: #e7e7e7 !important;
        color: #1A1A1A !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        padding: 0.6em 1.5em !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton > button:hover {
        background-color: #737272 !important;
        color: white !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(115, 114, 114, 0.3);
    }
    
    /* 데이터프레임 스타일 */
    .stDataFrame {
        border: 2px solid #e7e7e7;
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* 익스팬더 스타일 */
    .streamlit-expanderHeader {
        background-color: white;
        border: 2px solid #e7e7e7;
        border-radius: 8px;
        font-weight: 500;
        color: #1A1A1A;
    }
    
    .streamlit-expanderHeader:hover {
        border-color: #EF3340;
    }
    
    /* 스피너 */
    .stSpinner > div {
        border-top-color: #EF3340 !important;
    }
</style>
""", unsafe_allow_html=True)

# (기존 함수들 - 변경사항 없음)
@st.cache_resource
def init_google_sheet():
    """구글 시트 직접 연결"""
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        service_account_info = {
            "type": st.secrets["google_credentials"]["type"],
            "project_id": st.secrets["google_credentials"]["project_id"],
            "private_key_id": st.secrets["google_credentials"]["private_key_id"],
            "private_key": st.secrets["google_credentials"]["private_key"].replace("\\n", "\n"),
            "client_email": st.secrets["google_credentials"]["client_email"],
            "client_id": st.secrets["google_credentials"]["client_id"],
            "auth_uri": st.secrets["google_credentials"]["auth_uri"],
            "token_uri": st.secrets["google_credentials"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["google_credentials"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["google_credentials"]["client_x509_cert_url"],
            "universe_domain": st.secrets["google_credentials"]["universe_domain"]
        }
        
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scope)
        gc = gspread.authorize(credentials)
        
        sheet_id = st.secrets["GOOGLE_SHEET_ID"]
        sheet = gc.open_by_key(sheet_id).sheet1
        
        return sheet
        
    except Exception as e:
        return None

# 전역 변수
google_sheet = init_google_sheet()

def normalize_text(text: str) -> str:
    """텍스트 정규화 - 공백, 대소문자, 특수문자 제거"""
    if not text:
        return ""
    return str(text).strip().lower().replace(" ", "").replace("\n", "").replace("\t", "")

def find_candidate_requests(name: str, email: str):
    """구글 시트에서 직접 면접자 요청 찾기 - 개선된 버전"""
    try:
        if not google_sheet:
            return []
        
        all_values = google_sheet.get_all_values()
        if not all_values or len(all_values) < 2:
            return []
        
        headers = all_values[0]
        
        try:
            name_col_idx = None
            email_col_idx = None
            
            for i, header in enumerate(headers):
                header_normalized = normalize_text(header)
                if header_normalized in ['면접자명', '면접자이름', '이름', 'name', 'candidate_name']:
                    name_col_idx = i
                elif header_normalized in ['면접자이메일', '면접자메일', '이메일', 'email', 'candidate_email']:
                    email_col_idx = i
            
            if name_col_idx is None or email_col_idx is None:
                st.markdown(f"""
                <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="color: #1A1A1A; margin: 0;">❌ 필요한 컬럼을 찾을 수 없습니다. 현재 컬럼: {headers}</p>
                </div>
                """, unsafe_allow_html=True)
                return []
                
        except Exception as e:
            st.markdown(f"""
            <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="color: #1A1A1A; margin: 0;">❌ 헤더 분석 실패: {e}</p>
            </div>
            """, unsafe_allow_html=True)
            return []
        
        normalized_search_name = normalize_text(name)
        normalized_search_email = normalize_text(email)
        
        matching_requests = []
        
        for row_idx, row in enumerate(all_values[1:], start=2):
            try:
                row_name = row[name_col_idx] if name_col_idx < len(row) else ""
                row_email = row[email_col_idx] if email_col_idx < len(row) else ""
                
                normalized_row_name = normalize_text(row_name)
                normalized_row_email = normalize_text(row_email)
                
                if (normalized_row_name == normalized_search_name and 
                    normalized_row_email == normalized_search_email):
                    
                    request_obj = {'_row_number': row_idx}
                    
                    for col_idx, header in enumerate(headers):
                        value = row[col_idx] if col_idx < len(row) else ""
                        request_obj[header] = value
                    
                    request_obj.update({
                        'id': request_obj.get('요청ID', ''),
                        'position_name': request_obj.get('포지션명', ''),
                        'candidate_name': request_obj.get('면접자명', ''),
                        'candidate_email': request_obj.get('면접자이메일', ''),
                        'interviewer_id': request_obj.get('면접관ID', ''),
                        'interviewer_name': request_obj.get('면접관이름', ''),
                        'status': request_obj.get('상태', ''),
                        'created_at': request_obj.get('생성일시', ''),
                        'proposed_slots': request_obj.get('제안일시목록', ''),
                        'confirmed_datetime': request_obj.get('확정일시', ''),
                        'candidate_note': request_obj.get('면접자요청사항', ''),
                        'row_number': row_idx
                    })
                    
                    matching_requests.append(request_obj)
                    
            except Exception as e:
                continue
        
        return matching_requests
        
    except Exception as e:
        st.markdown(f"""
        <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p style="color: #1A1A1A; margin: 0;">❌ 데이터 조회 중 오류: {e}</p>
        </div>
        """, unsafe_allow_html=True)
        return []

def parse_proposed_slots(slots_str: str):
    """제안일시목록 문자열을 파싱"""
    if not slots_str:
        return []
    
    slots = []
    parts = slots_str.split(' | ')
    
    for part in parts:
        try:
            if '(' in part and ')' in part:
                datetime_part, duration_part = part.split('(')
                duration = duration_part.replace('분)', '')
                
                date_part, time_part = datetime_part.strip().split(' ')
                
                slots.append({
                    'date': date_part,
                    'time': time_part,
                    'duration': int(duration)
                })
        except:
            continue
    
    return slots

def format_date_korean(date_str: str) -> str:
    """날짜를 한국어 형식으로 변환"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        weekday_names = ['월', '화', '수', '목', '금', '토', '일']
        weekday = weekday_names[date_obj.weekday()]
        return f"{date_obj.month}월 {date_obj.day}일 ({weekday})"
    except:
        return date_str

def update_sheet_selection(request, selected_slot=None, candidate_note="", is_alternative_request=False):
    """구글 시트에 면접자 선택 결과 업데이트"""
    try:
        if not google_sheet:
            st.markdown("""
            <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="color: #1A1A1A; margin: 0;">❌ 구글 시트 연결이 없습니다.</p>
            </div>
            """, unsafe_allow_html=True)
            return False
        
        if 'row_number' not in request:
            st.markdown("""
            <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="color: #1A1A1A; margin: 0;">❌ 행 번호 정보가 없습니다.</p>
            </div>
            """, unsafe_allow_html=True)
            return False
        
        row_number = request['row_number']
        
        headers = google_sheet.row_values(1)
        
        try:
            confirmed_col = headers.index('확정일시') + 1
            status_col = headers.index('상태') + 1  
            note_col = headers.index('면접자요청사항') + 1
            update_col = headers.index('마지막업데이트') + 1
        except ValueError as e:
            st.markdown(f"""
            <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="color: #1A1A1A; margin: 0;">❌ 필요한 컬럼을 찾을 수 없습니다: {e}</p>
            </div>
            """, unsafe_allow_html=True)
            return False
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        if is_alternative_request:
            google_sheet.update_cell(row_number, confirmed_col, "")
            google_sheet.update_cell(row_number, status_col, "일정재조율요청")
            google_sheet.update_cell(row_number, note_col, f"[다른 일정 요청] {candidate_note}")
            google_sheet.update_cell(row_number, update_col, current_time)
            
        else:
            if selected_slot:
                confirmed_datetime = f"{selected_slot['date']} {selected_slot['time']}({selected_slot['duration']}분)"
                note_text = f"[확정시 요청사항] {candidate_note}" if candidate_note.strip() else ""
                
                google_sheet.update_cell(row_number, confirmed_col, confirmed_datetime)
                google_sheet.update_cell(row_number, status_col, "확정완료")
                google_sheet.update_cell(row_number, note_col, note_text)
                google_sheet.update_cell(row_number, update_col, current_time)
            else:
                st.markdown("""
                <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="color: #1A1A1A; margin: 0;">❌ 선택된 슬롯 정보가 없습니다.</p>
                </div>
                """, unsafe_allow_html=True)
                return False
        
        time.sleep(1)
        
        return True
        
    except Exception as e:
        st.markdown(f"""
        <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p style="color: #1A1A1A; margin: 0;">❌ 시트 업데이트 실패: {e}</p>
        </div>
        """, unsafe_allow_html=True)
        return False

def force_refresh_candidate_data(name, email):
    """면접자 데이터 강제 새로고침"""
    try:
        try:
            st.cache_resource.clear()
        except:
            try:
                st.experimental_memo.clear()
                st.experimental_singleton.clear()
            except:
                pass
        
        global google_sheet
        google_sheet = init_google_sheet()
        
        if not google_sheet:
            return []
        
        return find_candidate_requests(name, email)
        
    except Exception as e:
        return []

def hide_pages():
    """면접자 앱에서 불필요한 페이지 숨기기"""
    hide_streamlit_style = """
    <style>
    .css-1d391kg {display: none}
    section[data-testid="stSidebar"] > div:first-child {display: none}
    </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def show_candidate_login():
    """면접자 인증 페이지 - HTML 커스텀 디자인"""
   
    if not google_sheet:
        st.markdown("""
        <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 25px; border-radius: 10px; margin: 30px auto; max-width: 600px; text-align: center;">
            <h3 style="color: #1A1A1A; margin: 0;">❌ 구글 시트에 연결할 수 없습니다</h3>
            <p style="color: #737272; margin: 10px 0 0 0;">관리자에게 문의해주세요.</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # 로그인 폼 컨테이너
        
        with st.form("candidate_login"):
            st.markdown("""
            <label style="color: #1A1A1A; font-weight: 500; font-size: 0.95rem; margin-bottom: 8px; display: block;">
                이름 <span style="color: #EF3340;">*</span>
            </label>
            """, unsafe_allow_html=True)
            
            candidate_name = st.text_input(
                "이름",
                placeholder="홍길동",
                help="지원 시 입력한 이름을 정확히 입력해주세요",
                label_visibility="collapsed"
            )
            
            st.markdown("""
            <label style="color: #1A1A1A; font-weight: 500; font-size: 0.95rem; margin: 20px 0 8px 0; display: block;">
                이메일 주소 <span style="color: #EF3340;">*</span>
            </label>
            """, unsafe_allow_html=True)
            
            candidate_email = st.text_input(
                "이메일",
                placeholder="example@naver.com",
                help="지원 시 입력한 이메일 주소를 정확히 입력해주세요",
                label_visibility="collapsed"
            )

            submitted = st.form_submit_button("면접 일정 확인", use_container_width=True)

            if submitted:
                if not candidate_name.strip():
                    st.markdown("""
                    <div style="background-color: #f7ddd4; border-left: 5px solid #EF3340; padding: 15px; border-radius: 8px; margin-top: 15px;">
                        <p style="color: #1A1A1A; margin: 0;">⚠️ 이름을 입력해주세요.</p>
                    </div>
                    """, unsafe_allow_html=True)
                elif not candidate_email.strip():
                    st.markdown("""
                    <div style="background-color: #f7ddd4; border-left: 5px solid #EF3340; padding: 15px; border-radius: 8px; margin-top: 15px;">
                        <p style="color: #1A1A1A; margin: 0;">⚠️ 이메일 주소를 입력해주세요.</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    with st.spinner("🔍 면접자 정보를 확인하고 있습니다..."):
                        matching_requests = find_candidate_requests(candidate_name.strip(), candidate_email.strip())
                    
                    if matching_requests:
                        st.session_state.authenticated_candidate = {
                            'name': candidate_name.strip(),
                            'email': candidate_email.strip()
                        }
                        st.session_state.candidate_requests = matching_requests
                        st.markdown(f"""
                        <div style="background-color: #e8f5e9; border-left: 5px solid #4caf50; padding: 15px; border-radius: 8px; margin-top: 15px;">
                            <p style="color: #1A1A1A; margin: 0;">✅ {len(matching_requests)}건의 면접 요청을 찾았습니다!</p>
                        </div>
                        """, unsafe_allow_html=True)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.markdown("""
                        <div style="background-color: #f7ddd4; border-left: 5px solid #EF3340; padding: 15px; border-radius: 8px; margin-top: 15px;">
                            <p style="color: #1A1A1A; margin: 0;">❌ 입력하신 정보와 일치하는 면접 요청을 찾을 수 없습니다.</p>
                        </div>
                        """, unsafe_allow_html=True)

    # 도움말
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="background: white; padding: 30px; margin: 20px 0;">
            <h4 style="color: #1A1A1A; margin: 0 0 20px 0; font-weight: 500; text-align: center;">💡 이용 안내</h4>
            <div style="background-color: #efeff1; padding: 20px; border-radius: 8px; margin: 15px 0;">
                <p style="margin: 10px 0; color: #1A1A1A; line-height: 1.6;">
                    • 지원 시 입력한 <strong>정확한 이름과 이메일</strong>을 입력해주세요
                </p>
                <p style="margin: 10px 0; color: #1A1A1A; line-height: 1.6;">
                    • 면접관이 일정을 입력해야 <strong>선택 가능</strong>합니다
                </p>
            </div>
            <div style="background-color: white; padding: 10px; border-radius: 8px; margin-top: 20px; text-align: center;">
                <p style="margin: 0; color: #1A1A1A;">
                    <strong>기타 문의:</strong> 
                    <a href="mailto:hr@ajnet.co.kr" style="color: #EF3340; text-decoration: none; font-weight: 500;">
                        hr@ajnet.co.kr
                    </a>
                </p>
            </div>
        </div>
        """, unsafe_allow_html=True)

def show_candidate_dashboard():
    """면접자 대시보드 - HTML 커스텀"""
    candidate_info = st.session_state.authenticated_candidate
    candidate_requests = st.session_state.candidate_requests
    
    # 헤더
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #EF3340 0%, #d42a36 100%); color: white; padding: 30px; border-radius: 15px; margin-bottom: 30px; box-shadow: 0 4px 15px rgba(239, 51, 64, 0.2);">
        <h2 style="margin: 0; font-weight: 500;">📋 {candidate_info['name']}님의 면접 일정</h2>
        <p style="margin: 10px 0 0 0; opacity: 0.9;">총 {len(candidate_requests)}건의 면접 요청</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 각 요청 처리
    for i, request in enumerate(candidate_requests):
        with st.expander(f"📅 {request['position_name']} - {request['created_at']} 신청", expanded=len(candidate_requests)==1):
            show_request_detail(request, i)

def show_alternative_request_success(candidate_note: str):
    """다른 일정 요청 성공 화면"""
    
    st.markdown("""
    <div style="background: linear-gradient(135deg, #e0752e 0%, #d46825 100%); color: white; padding: 50px; border-radius: 15px; text-align: center; margin: 40px 0; box-shadow: 0 10px 30px rgba(224, 117, 46, 0.3);">
        <div style="font-size: 4rem; margin-bottom: 20px;">📧</div>
        <h1 style="margin: 0 0 15px 0; font-size: 2rem; font-weight: 500;">일정 재조율 요청이 전달되었습니다!</h1>
        <p style="font-size: 1.1rem; opacity: 0.95; margin: 0;">인사팀에서 검토 후 별도 연락드리겠습니다.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 요청사항 표시
    st.markdown(f"""
    <div style="background: white; padding: 30px; border-radius: 12px; margin: 30px 0; border-left: 5px solid #e0752e; box-shadow: 0 2px 10px rgba(224, 117, 46, 0.1);">
        <h4 style="color: #1A1A1A; margin: 0 0 15px 0; font-weight: 500;">📝 전달된 요청사항</h4>
        <div style="background: #efeff1; padding: 20px; border-radius: 8px;">
            <p style="color: #1A1A1A; margin: 0; white-space: pre-line; line-height: 1.8;">{candidate_note}</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 안내 메시지
    st.markdown("""
    <div style="background: white; padding: 30px; border-radius: 12px; border-left: 5px solid #EF3340; margin: 30px 0; box-shadow: 0 2px 10px rgba(239, 51, 64, 0.1);">
        <h4 style="color: #1A1A1A; margin: 0 0 15px 0; font-weight: 500;">📋 다음 단계</h4>
        <ul style="color: #737272; line-height: 2; margin: 0; padding-left: 20px;">
            <li>인사팀에서 요청사항을 검토합니다</li>
            <li>가능한 대안 일정을 찾아 연락드립니다</li>
            <li>추가 문의가 있으시면 <strong style="color: #EF3340;">hr@ajnet.co.kr</strong>로 연락해주세요</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div style="text-align: center; margin: 30px 0;">
        <p style="color: #737272; font-size: 0.95rem;">잠시 후 초기 화면으로 돌아갑니다...</p>
    </div>
    """, unsafe_allow_html=True)
    
    time.sleep(3)
    
    for key in ['authenticated_candidate', 'candidate_requests']:
        if key in st.session_state:
            del st.session_state[key]
    
    st.rerun()

def show_request_detail(request, index):
    """요청 상세 정보 및 일정 선택 폼 - HTML 커스텀"""
    
    # 면접 정보 표시
    st.markdown(f"""
    <div style="background: white; padding: 30px; border-radius: 12px; border-left: 5px solid #EF3340; margin: 25px 0; box-shadow: 0 2px 10px rgba(239, 51, 64, 0.08);">
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 12px 0; font-weight: 500; color: #737272; width: 120px;">포지션</td>
                <td style="padding: 12px 0; color: #1A1A1A; font-size: 1.15rem; font-weight: 500;">{request['position_name']}</td>
            </tr>
            <tr style="border-top: 1px solid #efeff1;">
                <td style="padding: 12px 0; font-weight: 500; color: #737272;">면접관</td>
                <td style="padding: 12px 0; color: #1A1A1A;">{request['interviewer_name']} <span style="color: #737272; font-size: 0.9rem;">(ID: {request['interviewer_id']})</span></td>
            </tr>
            <tr style="border-top: 1px solid #efeff1;">
                <td style="padding: 12px 0; font-weight: 500; color: #737272;">신청일</td>
                <td style="padding: 12px 0; color: #1A1A1A;">{request['created_at']}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    # 확정된 일정이 있는 경우
    if request.get('status') == '확정완료' and request.get('confirmed_datetime'):
        show_confirmed_schedule(request)
        return
    
    # 제안된 일정 파싱
    proposed_slots = parse_proposed_slots(request['proposed_slots'])
    
    if not proposed_slots:
        st.markdown("""
        <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 25px; border-radius: 10px; margin: 25px 0;">
            <h4 style="color: #1A1A1A; margin: 0 0 10px 0;">⚠️ 제안된 일정 없음</h4>
            <p style="color: #737272; margin: 0;">면접관이 아직 가능한 일정을 입력하지 않았습니다.</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"🔄 상태 새로고침", key=f"refresh_{index}"):
            candidate_info = st.session_state.authenticated_candidate
            updated_requests = force_refresh_candidate_data(candidate_info['name'], candidate_info['email'])
            st.session_state.candidate_requests = updated_requests
            st.rerun()
        return
    
    # 제안된 일정 섹션
    st.markdown("""
    <div style="margin: 30px 0 15px 0;">
        <h4 style="color: #1A1A1A; margin: 0; font-weight: 500;">🗓️ 제안된 면접 일정</h4>
        <p style="color: #737272; margin: 5px 0 15px 0; font-size: 0.95rem;">아래 일정 중 하나를 선택해주세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 제안된 일정 테이블
    if proposed_slots:
        table_html = """
        <div style="background: white; border-radius: 10px; overflow: hidden; border: 2px solid #efeff1; margin-bottom: 25px;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #efeff1;">
                        <th style="padding: 15px; text-align: left; color: #1A1A1A; font-weight: 500; border-bottom: 2px solid #e7e7e7;">옵션</th>
                        <th style="padding: 15px; text-align: left; color: #1A1A1A; font-weight: 500; border-bottom: 2px solid #e7e7e7;">날짜</th>
                        <th style="padding: 15px; text-align: left; color: #1A1A1A; font-weight: 500; border-bottom: 2px solid #e7e7e7;">시간</th>
                        <th style="padding: 15px; text-align: left; color: #1A1A1A; font-weight: 500; border-bottom: 2px solid #e7e7e7;">소요시간</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for i, slot in enumerate(proposed_slots, 1):
            row_bg = "#fafafa" if i % 2 == 0 else "white"
            table_html += f"""
                <tr style="background-color: {row_bg};">
                    <td style="padding: 15px; color: #1A1A1A; border-bottom: 1px solid #efeff1;">옵션 {i}</td>
                    <td style="padding: 15px; color: #1A1A1A; border-bottom: 1px solid #efeff1; font-weight: 500;">{format_date_korean(slot['date'])}</td>
                    <td style="padding: 15px; color: #1A1A1A; border-bottom: 1px solid #efeff1;">{slot['time']}</td>
                    <td style="padding: 15px; color: #1A1A1A; border-bottom: 1px solid #efeff1;">{slot['duration']}분</td>
                </tr>
            """
        
        table_html += """
                </tbody>
            </table>
        </div>
        """
        
        st.markdown(table_html, unsafe_allow_html=True)
    
    # 슬롯 옵션 생성
    slot_options = []
    for i, slot in enumerate(proposed_slots):
        slot_text = f"옵션 {i+1}: {format_date_korean(slot['date'])} {slot['time']} ({slot['duration']}분)"
        slot_options.append(slot_text)
    
    slot_options.append("💬 다른 일정 요청")
    
    # 셀렉트박스
    select_key = f"select_selection_{index}"
    if select_key not in st.session_state:
        st.session_state[select_key] = slot_options[0]
    
    st.markdown("""
    <label style="color: #1A1A1A; font-weight: 500; font-size: 1rem; margin-bottom: 10px; display: block;">
        원하는 면접 일정을 선택해주세요
    </label>
    """, unsafe_allow_html=True)
    
    selected_option_text = st.selectbox(
        "일정 선택",
        options=slot_options,
        index=slot_options.index(st.session_state[select_key]) if st.session_state[select_key] in slot_options else 0,
        key=select_key,
        label_visibility="collapsed"
    )
    
    selected_option = slot_options.index(selected_option_text)
    
    # 선택 반응 표시
    if selected_option < len(proposed_slots):
        selected_slot_info = proposed_slots[selected_option]
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-left: 6px solid #4caf50; border-radius: 10px; padding: 20px; margin: 20px 0;">
            <h4 style="color: #2e7d32; margin: 0 0 8px 0; font-weight: 500;">✅ 선택하신 일정</h4>
            <p style="color: #1b5e20; font-size: 1.1rem; margin: 0;">
                <strong>{format_date_korean(selected_slot_info['date'])}</strong>
                &nbsp;&nbsp;{selected_slot_info['time']}
                &nbsp;&nbsp;<span style="opacity: 0.8;">({selected_slot_info['duration']}분)</span>
            </p>
        </div>
        """, unsafe_allow_html=True)

    elif selected_option == len(slot_options) - 1:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #f7ddd4 0%, #f5cfc1 100%); border-left: 6px solid #e0752e; border-radius: 10px; padding: 20px; margin: 20px 0;">
            <h4 style="color: #1A1A1A; margin: 0 0 8px 0; font-weight: 500;">⚠️ 다른 일정 요청</h4>
            <p style="color: #737272; font-size: 1rem; margin: 0;">
                아래 입력창에 가능한 일정을 구체적으로 작성해주세요.
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    # 다른 일정 요청 입력창
    candidate_note = ""
    if selected_option == len(slot_options) - 1:
        st.markdown("""
        <label style="color: #1A1A1A; font-weight: 500; font-size: 1rem; margin: 20px 0 10px 0; display: block;">
            가능한 면접 일정이나 요청사항을 입력해주세요
        </label>
        """, unsafe_allow_html=True)
        
        candidate_note = st.text_area(
            "요청사항",
            placeholder="예시:\n• 월요일과 수요일은 전체 불가능합니다\n• 오전 시간대를 선호합니다\n• 온라인 면접을 희망합니다",
            height=180,
            key=f"candidate_note_{index}",
            label_visibility="collapsed"
        )
    
    # 제출 버튼
    st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
    
    submit_key = f"submit_{index}"
    if st.button("✅ 면접 일정 선택 완료", key=submit_key, use_container_width=True, type="primary"):
        if 'row_number' not in request:
            st.markdown("""
            <div style="background-color: #f7ddd4; border-left: 5px solid #EF3340; padding: 20px; border-radius: 8px; margin-top: 15px;">
                <p style="color: #1A1A1A; margin: 0;">❌ 요청 데이터에 문제가 있습니다. 페이지를 새로고침해주세요.</p>
            </div>
            """, unsafe_allow_html=True)
            return
        
        if selected_option < len(proposed_slots):
            selected_slot = proposed_slots[selected_option]
            
            with st.spinner("📝 일정을 확정하고 있습니다..."):
                success = update_sheet_selection(
                    request, 
                    selected_slot=selected_slot, 
                    candidate_note=candidate_note, 
                    is_alternative_request=False
                )
                
                if success:
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); padding: 30px; border-radius: 12px; margin: 25px 0; text-align: center; border-left: 6px solid #4caf50;">
                        <h3 style="color: #2e7d32; margin: 0 0 15px 0;">🎉 일정이 확정되었습니다!</h3>
                        <p style="color: #1b5e20; font-size: 1.2rem; font-weight: 500; margin: 0;">
                            {format_date_korean(selected_slot['date'])} {selected_slot['time']} ({selected_slot['duration']}분)
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    time.sleep(2)
                    candidate_info = st.session_state.authenticated_candidate
                    updated_requests = force_refresh_candidate_data(candidate_info['name'], candidate_info['email'])
                    if updated_requests:
                        st.session_state.candidate_requests = updated_requests
                    
                    st.rerun()
                else:
                    st.markdown("""
                    <div style="background-color: #f7ddd4; border-left: 5px solid #EF3340; padding: 20px; border-radius: 8px; margin-top: 15px;">
                        <p style="color: #1A1A1A; margin: 0;">❌ 일정 확정 중 오류가 발생했습니다.</p>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            if not candidate_note.strip():
                st.markdown("""
                <div style="background-color: #f7ddd4; border-left: 5px solid #EF3340; padding: 20px; border-radius: 8px; margin-top: 15px;">
                    <p style="color: #1A1A1A; margin: 0;">❌ 가능한 일정을 구체적으로 입력해주세요.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                with st.spinner("📝 일정 재조율 요청을 전송하고 있습니다..."):
                    success = update_sheet_selection(
                        request, 
                        selected_slot=None, 
                        candidate_note=candidate_note, 
                        is_alternative_request=True
                    )
                    
                    if success:
                        show_alternative_request_success(candidate_note)
                    else:
                        st.markdown("""
                        <div style="background-color: #f7ddd4; border-left: 5px solid #EF3340; padding: 20px; border-radius: 8px; margin-top: 15px;">
                            <p style="color: #1A1A1A; margin: 0;">❌ 일정 재조율 요청 전송 중 오류가 발생했습니다.</p>
                        </div>
                        """, unsafe_allow_html=True)

def show_confirmed_schedule(request):
    """확정된 일정 표시 - HTML 커스텀"""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); padding: 40px; border-radius: 15px; text-align: center; margin: 30px 0; border-left: 8px solid #4caf50; box-shadow: 0 4px 15px rgba(76, 175, 80, 0.2);">
        <div style="font-size: 4rem; margin-bottom: 20px;">🎉</div>
        <h2 style="color: #2e7d32; margin: 0; font-weight: 500;">면접 일정이 확정되었습니다!</h2>
    </div>
    """, unsafe_allow_html=True)
    
    if request['confirmed_datetime']:
        st.markdown(f"""
        <div style="background: white; padding: 35px; border-radius: 12px; margin: 30px 0; text-align: center; border: 2px solid #4caf50; box-shadow: 0 2px 10px rgba(76, 175, 80, 0.1);">
            <h4 style="color: #737272; margin: 0 0 15px 0; font-weight: 400; font-size: 1rem;">📅 확정된 면접 일정</h4>
            <p style="color: #1A1A1A; font-size: 1.4rem; font-weight: 500; margin: 15px 0;">{request['confirmed_datetime']}</p>
            <p style="color: #737272; margin: 15px 0 0 0; font-size: 1rem;">면접관: <strong style="color: #1A1A1A;">{request['interviewer_name']}</strong></p>
        </div>
        """, unsafe_allow_html=True)
    
    # 면접 준비 안내
    st.markdown("""
    <div style="background: white; padding: 30px; border-radius: 12px; border-left: 5px solid #EF3340; margin: 30px 0; box-shadow: 0 2px 10px rgba(239, 51, 64, 0.08);">
        <h4 style="color: #1A1A1A; margin: 0 0 20px 0; font-weight: 500;">📝 면접 준비 안내</h4>
        <ul style="color: #737272; line-height: 2; margin: 0; padding-left: 25px;">
            <li>⏰ 면접 당일 <strong style="color: #1A1A1A;">10분 전까지 도착</strong>해주세요</li>
            <li>📞 일정 변경이 필요한 경우 <strong style="color: #1A1A1A;">최소 24시간 전</strong>에 인사팀에 연락해주세요</li>
            <li>📧 문의사항: <a href="mailto:hr@ajnet.co.kr" style="color: #EF3340; text-decoration: none; font-weight: 500;">hr@ajnet.co.kr</a></li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

def main():
    hide_pages()
    
    # 이미지 헤더
    st.markdown("""
    <div style="text-align: center; margin: 30px 0 40px 0;">
        <img src="https://i.imgur.com/JxtMWx3.png" 
             alt="면접 일정 선택"
             style="max-width: 280px; height: auto;">
    </div>
    """, unsafe_allow_html=True)

    if 'authenticated_candidate' not in st.session_state:
        show_candidate_login()
    else:
        show_candidate_dashboard()

if __name__ == "__main__":
    main()