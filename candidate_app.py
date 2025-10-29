import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # ✅ 추가

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import time
from utils import normalize_request_id, normalize_text, parse_proposed_slots  # ✅ 그대로 유지

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


def find_candidate_requests(name: str, email: str):
    """구글 시트에서 직접 면접자 요청 찾기 + 제안 일정 파싱"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        if not google_sheet:
            return []

        all_values = google_sheet.get_all_values()
        if not all_values or len(all_values) < 2:
            return []

        headers = all_values[0]
        
        # 🔧 정확한 컬럼 인덱스 찾기 (F열=5, G열=6)
        name_col_idx = None
        email_col_idx = None
        
        # 헤더를 통해 정확한 인덱스 찾기
        for i, header in enumerate(headers):
            if header.strip() == '면접자명':
                name_col_idx = i
            elif header.strip() == '면접자이메일':
                email_col_idx = i

        # 🔧 만약 헤더로 찾지 못했다면 직접 지정 (F=5, G=6)
        if name_col_idx is None:
            name_col_idx = 5  # F열 (0부터 시작하므로 5)
            
        if email_col_idx is None:
            email_col_idx = 6  # G열 (0부터 시작하므로 6)

        normalized_search_name = normalize_text(name)
        normalized_search_email = normalize_text(email)
        
        matching_requests = []

        # ✅ 조건에 맞는 요청만 필터링
        for row_idx, row in enumerate(all_values[1:], start=2):
            try:
                # 🔧 정확한 컬럼에서 데이터 가져오기
                row_name = row[name_col_idx].strip() if name_col_idx < len(row) else ""
                row_email = row[email_col_idx].strip() if email_col_idx < len(row) else ""
                
                normalized_row_name = normalize_text(row_name)
                normalized_row_email = normalize_text(row_email)
                
                # 🔧 정확한 매칭
                name_match = normalized_row_name == normalized_search_name
                email_match = normalized_row_email == normalized_search_email
                
                # 🔧 디버깅 로그 (처음 5개 행만)
                if row_idx <= 6:
                    logger.info(f"Row {row_idx}: 이름='{row_name}'→'{normalized_row_name}' (매칭:{name_match}), 이메일='{row_email}'→'{normalized_row_email}' (매칭:{email_match})")

                if name_match and email_match:
                    request_obj = {'_row_number': row_idx}

                    # 🔧 모든 컬럼 데이터 매핑
                    for col_idx, header in enumerate(headers):
                        request_obj[header] = row[col_idx].strip() if col_idx < len(row) else ""

                    # 요청 정보 정규화
                    raw_id = request_obj.get('요청ID', '')
                    clean_id = normalize_request_id(raw_id)

                    request_obj.update({
                        'id': clean_id,
                        'raw_id': raw_id,
                        'position_name': request_obj.get('공고명', ''),
                        'candidate_name': row_name,  # 🔧 직접 사용
                        'candidate_email': row_email,  # 🔧 직접 사용
                        'interviewer_id': request_obj.get('면접관ID', ''),
                        'interviewer_name': request_obj.get('면접관이름', ''),
                        'status': request_obj.get('상태', ''),
                        'created_at': request_obj.get('생성일시', ''),
                        'proposed_slots': request_obj.get('제안일시목록', ''),
                        'confirmed_datetime': request_obj.get('확정일시', ''),
                        'candidate_note': request_obj.get('면접자요청사항', ''),
                        'row_number': row_idx
                    })

                    # ✅ 선택 가능한 슬롯 필터링
                    if request_obj['status'] in ['면접자_선택대기', '면접자_메일발송']:  # ✅ 두 상태 모두 허용
                        proposed_slots_raw = request_obj.get('제안일시목록', '')
                        
                        if not proposed_slots_raw:
                            logger.warning(f"⚠️ {row_name} - 제안일시목록이 비어있음")
                            request_obj['available_slots_filtered'] = []
                            matching_requests.append(request_obj)
                            continue
                        
                        # 2단계: 기본 슬롯 파싱
                        base_slots = parse_proposed_slots(proposed_slots_raw)
                        
                        if not base_slots:
                            logger.warning(f"⚠️ {request_obj['candidate_name']} - 슬롯 파싱 실패")
                            request_obj['available_slots_filtered'] = []
                            matching_requests.append(request_obj)
                            continue
                        
                        logger.info(f"📋 {request_obj['candidate_name']} - 파싱된 슬롯: {len(base_slots)}개")
                        
                        # ✅ 3단계: 실시간 예약 슬롯 제외 (강화된 필터링)
                        try:
                            from database import DatabaseManager
                            db = DatabaseManager()
                            
                            # ✅ 동일 공고의 모든 확정된 슬롯 조회
                            reserved_slot_keys = set()
                            all_requests_db = db.get_all_requests()
                            
                            for req in all_requests_db:
                                if (req.position_name == request_obj['position_name'] 
                                    and req.status == Config.Status.CONFIRMED 
                                    and req.selected_slot 
                                    and req.id != clean_id):
                                    
                                    key = f"{req.selected_slot.date}_{req.selected_slot.time}"
                                    reserved_slot_keys.add(key)
                            
                            logger.info(f"🚫 {request_obj['candidate_name']} - 예약된 슬롯: {len(reserved_slot_keys)}개")
                            
                            # ✅ 예약되지 않은 슬롯만 필터링
                            filtered_slots = []
                            for slot in base_slots:
                                slot_key = f"{slot['date']}_{slot['time']}"
                                if slot_key not in reserved_slot_keys:
                                    filtered_slots.append(slot)
                            
                            request_obj['available_slots_filtered'] = filtered_slots
                            logger.info(f"✅ {request_obj['candidate_name']} - 선택 가능한 슬롯: {len(filtered_slots)}개")
                            
                        except Exception as e:
                            # 오류 발생 시 기본 슬롯 사용
                            logger.error(f"❌ {request_obj['candidate_name']} - 필터링 오류: {e}, 기본 슬롯 사용")
                            request_obj['available_slots_filtered'] = base_slots
                    else:
                        # 상태가 "면접자_선택대기"가 아닌 경우
                        request_obj['available_slots_filtered'] = []

                    matching_requests.append(request_obj)

            except Exception as e:
                continue

        return matching_requests

    except Exception as e:
        logger.error(f"find_candidate_requests 오류: {e}")
        return []

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
                <p style="color: #1A1A1A; margin: 0;">구글 시트 연결이 없습니다.</p>
            </div>
            """, unsafe_allow_html=True)
            return False
        
        if 'row_number' not in request:
            st.markdown("""
            <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="color: #1A1A1A; margin: 0;">행 번호 정보가 없습니다.</p>
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
                <p style="color: #1A1A1A; margin: 0;">필요한 컬럼을 찾을 수 없습니다: {e}</p>
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
                    <p style="color: #1A1A1A; margin: 0;">선택된 슬롯 정보가 없습니다.</p>
                </div>
                """, unsafe_allow_html=True)
                return False
        
        time.sleep(1)
        
        return True
        
    except Exception as e:
        st.markdown(f"""
        <div style="background-color: #f7ddd4; border-left: 5px solid #e0752e; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <p style="color: #1A1A1A; margin: 0;">시트 업데이트 실패: {e}</p>
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
            <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 15px 0;">
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

def prepare_slot_selectbox(available_slots, index):
    """
    면접 시간 슬롯 리스트에서 라디오 버튼으로 선택
    """
    from datetime import datetime

    def generate_slot_label(slot, idx):
        """옵션 라벨 생성: 옵션 1: 11월 3일 (월) 14:00 (30분)"""
        date_kr = format_date_korean(slot.date)
        return f"옵션 {idx + 1}: {date_kr} {slot.time} ({slot.duration}분)"

    # 라벨 -> 객체 매핑
    slot_label_to_obj = {
        generate_slot_label(slot, i): slot
        for i, slot in enumerate(available_slots)
    }

    # "다른 일정 요청" 항목 추가
    alternative_label = "💬 다른 일정 요청"
    slot_labels = list(slot_label_to_obj.keys()) + [alternative_label]

    # 세션 상태 키
    select_key = f"radio_selection_{index}"

    # ✅ 라디오 버튼 렌더링
    selected_label = st.radio(
        "일정 선택",
        options=slot_labels,
        key=select_key,
        label_visibility="collapsed"
    )

    return selected_label, slot_label_to_obj, alternative_label

def show_request_detail(request, index):
    from models import InterviewSlot

    # 면접 정보 표시 (기존 코드)
    st.markdown(f"""
    <div style="background: white; padding: 30px; border-radius: 12px; border-left: 5px solid #EF3340; margin: 25px 0; box-shadow: 0 2px 10px rgba(239, 51, 64, 0.08);">
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 12px 0; font-weight: 500; color: #737272; width: 120px;">포지션</td>
                <td style="padding: 12px 0; color: #1A1A1A; font-size: 1.15rem; font-weight: 500;">{request['position_name']}</td>
            </tr>
            <tr style="border-top: 1px solid #efeff1;">
                <td style="padding: 12px 0; font-weight: 500; color: #737272;">신청일</td>
                <td style="padding: 12px 0; color: #1A1A1A;">{request['created_at']}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

    if request.get('status') == '확정완료' and request.get('confirmed_datetime'):
        show_confirmed_schedule(request)
        return

    # ✅ 전화번호 입력 필드
    st.markdown("---")
    st.markdown("**📞 연락처 입력**")
    
    phone_number = st.text_input(
        "전화번호",
        placeholder="01012345678 (하이픈 없이 11자리)",
        help="숫자만 11자리 입력해주세요",
        key=f"phone_number_{index}",
        max_chars=11
    )

    # 하이픈 자동 제거
    phone_number_clean = ""
    phone_valid = False
    
    if phone_number:
        phone_number_clean = phone_number.replace('-', '').replace(' ', '')
        
        # 유효성 검사
        if not phone_number_clean.isdigit():
            st.markdown("""
            <div style="background-color: #f8d7da; border-left: 5px solid #EF3340; padding: 12px; border-radius: 8px; margin: 10px 0;">
                <p style="color: #721c24; margin: 0; font-size: 14px;">❌ 숫자만 입력해주세요.</p>
            </div>
            """, unsafe_allow_html=True)
        elif len(phone_number_clean) != 11:
            st.markdown("""
            <div style="background-color: #f8d7da; border-left: 5px solid #EF3340; padding: 12px; border-radius: 8px; margin: 10px 0;">
                <p style="color: #721c24; margin: 0; font-size: 14px;">❌ 11자리 전화번호를 입력해주세요.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            phone_valid = True
            st.markdown("""
            <div style="background-color: #d4edda; border-left: 5px solid #28a745; padding: 12px; border-radius: 8px; margin: 10px 0;">
                <p style="color: #155724; margin: 0; font-size: 14px;">✅ 올바른 전화번호 형식입니다.</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # 일정 선택 섹션
    available_slots_data = request.get('available_slots_filtered', [])
    available_slots = [
        InterviewSlot(
            date=slot['date'],
            time=slot['time'],
            duration=slot['duration']
        ) for slot in available_slots_data
    ]

    if not available_slots:
        st.warning("⚠️ 선택 가능한 일정이 없습니다. 면접관이 일정을 입력했는지 확인해주세요.")
        if st.button(f"🔄 상태 새로고침", key=f"refresh_{index}"):
            info = st.session_state.authenticated_candidate
            st.session_state.candidate_requests = force_refresh_candidate_data(info['name'], info['email'])
            st.rerun()
        return

    selected_label, slot_label_to_obj, alternative_label = prepare_slot_selectbox(available_slots, index)

    if selected_label == alternative_label:
        st.info("⚠️ 다른 일정 요청을 남겨주세요.")
        candidate_note = st.text_area(
            "요청사항",
            placeholder="월/수 전체 불가능, 오전 선호 등",
            height=180,
            key=f"candidate_note_{index}",
            label_visibility="collapsed"
        )
    else:
        selected_slot_info = slot_label_to_obj[selected_label]
        candidate_note = ""

        st.success(f"✅ 선택하신 일정: {format_date_korean(selected_slot_info.date)} {selected_slot_info.time} ({selected_slot_info.duration}분)")

    # ✅ 제출 버튼 (전화번호 유효성 체크 포함)
    if st.button("✅ 면접 일정 선택 완료", key=f"submit_{index}", use_container_width=True, type="primary"):
        # ✅ 전화번호 유효성 체크
        if not phone_number or not phone_valid:
            # ✅ 세션 상태에 경고 메시지 저장
            st.session_state.warning_message = "올바른 전화번호를 입력해주세요. (숫자 11자리)"
            st.rerun()
            return
        
        if 'row_number' not in request:
            st.error("❌ 요청 데이터에 문제가 있습니다.")
            return

        if selected_label == alternative_label:
            if not candidate_note.strip():
                st.error("❌ 가능한 일정을 입력해주세요.")
            else:
                with st.spinner("📝 요청 중..."):
                    success = update_sheet_selection(request, None, candidate_note, True)
                    if success:
                        show_alternative_request_success(candidate_note)
        else:
            from database import DatabaseManager
            db = DatabaseManager()

            # 요청 ID 매칭
            search_id = request.get('id', '').replace('...', '')
            
            req_obj = db.get_interview_request(search_id)
            
            if not req_obj:
                all_requests = db.get_all_requests()
                for r in all_requests:
                    from utils import normalize_request_id
                    if normalize_request_id(r.id) == normalize_request_id(search_id):
                        req_obj = r
                        break
                    if search_id in r.id or r.id.startswith(search_id):
                        req_obj = r
                        break

            if not req_obj:
                st.error(f"❌ 요청 ID를 찾을 수 없습니다. (검색한 ID: {search_id})")
                
                with st.expander("🔍 디버깅 정보"):
                    st.write(f"**구글시트 ID:** {request.get('id', 'N/A')}")
                    st.write(f"**정규화된 검색 ID:** {search_id}")
                    
                    all_requests = db.get_all_requests()
                    st.write(f"**DB의 모든 요청 ID ({len(all_requests)}개):**")
                    for r in all_requests[:5]:
                        st.write(f"  - {r.id}")
                return

            # ✅ 전화번호를 request 객체에 저장
            req_obj.candidate_phone = phone_number_clean

            # 슬롯 예약 시도
            if db.reserve_slot_for_candidate(req_obj, selected_slot_info):
                update_sheet_selection(request, selected_slot_info.to_dict(), "")
                st.success("🎉 일정이 확정되었습니다!")
                updated = force_refresh_candidate_data(
                    st.session_state.authenticated_candidate['name'],
                    st.session_state.authenticated_candidate['email']
                )
                st.session_state.candidate_requests = updated
                st.rerun()
            else:
                # ✅ 세션 상태에 경고 메시지 저장
                st.session_state.warning_message = "해당 일정이 이미 선택되었습니다. 다른 일정을 선택해주세요."
                
                # 데이터 새로고침
                st.session_state.candidate_requests = force_refresh_candidate_data(
                    st.session_state.authenticated_candidate['name'],
                    st.session_state.authenticated_candidate['email']
                )
                st.rerun()

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

    # ✅ 경고 메시지 표시 (최상단)
    if 'warning_message' in st.session_state and st.session_state.warning_message:
        col1, col2 = st.columns([10, 1])
        
        with col1:
            st.markdown(f"""
            <div style="background-color: #f8d7da; border-left: 5px solid #EF3340; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="color: #721c24; margin: 0; font-weight: bold; font-size: 16px;">
                    ⚠️ {st.session_state.warning_message}
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            if st.button("✖", key="close_warning", help="닫기"):
                st.session_state.warning_message = None
                st.rerun()

    # DB 동기화 (최초 1회만)
    if 'db_synced' not in st.session_state:
        with st.spinner("📊 데이터 동기화 중..."):
            from database import DatabaseManager
            db = DatabaseManager()
            db.sync_from_google_sheet_to_db()
            st.session_state.db_synced = True

    # 이미지 헤더
    st.markdown("""
    <div style="text-align: center; margin: 30px 0 40px 0;">
        <img src="https://i.imgur.com/JxtMWx3.png" 
            alt="AJ네트웍스"
            style="max-width: 280px; height: auto; margin-bottom: 15px;">
        <h2 style="color: #1A1A1A; margin: 0; font-weight: 500;">면접 일정 확인</h2>
    </div>
    """, unsafe_allow_html=True)

    if 'authenticated_candidate' not in st.session_state:
        show_candidate_login()
    else:
        show_candidate_dashboard()

if __name__ == "__main__":

    main()
