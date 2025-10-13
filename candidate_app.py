import streamlit as st
import os
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# 🔧 면접자 앱임을 명시
os.environ["APP_TYPE"] = "candidate"

# 페이지 설정을 맨 처음에 실행
st.set_page_config(
    page_title="면접 일정 선택 - AI 면접 시스템",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="collapsed"  # 사이드바 기본 숨김
)

# 구글 시트 연결 함수
@st.cache_resource
def init_google_sheet():
    """구글 시트 직접 연결"""
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Streamlit Secrets에서 인증 정보 가져오기
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
        
        # 구글 시트 연결
        sheet_id = st.secrets["GOOGLE_SHEET_ID"]
        sheet = gc.open_by_key(sheet_id).sheet1
        
        return sheet
        
    except Exception as e:
        st.error(f"구글 시트 연결 실패: {e}")
        return None

# 전역 객체 초기화
@st.cache_resource
def init_services():
    try:
        from database import DatabaseManager
        from email_service import EmailService
        db = DatabaseManager()
        email_service = EmailService()
        return db, email_service
    except Exception as e:
        st.error(f"서비스 초기화 실패: {e}")
        return None, None

# 전역 변수
google_sheet = init_google_sheet()
db, email_service = init_services()

def get_candidates_from_sheet():
    """🔍 구글 시트에서 면접자 정보 조회 (디버깅 강화)"""
    try:
        if not google_sheet:
            st.error("구글 시트 연결이 없습니다.")
            return []
        
        # 🔍 원시 데이터 확인
        st.write("🔍 **디버깅: 구글 시트 원시 데이터**")
        all_values = google_sheet.get_all_values()
        st.write(f"전체 행 수: {len(all_values)}")
        
        if all_values:
            st.write("첫 번째 행 (헤더):", all_values[0])
            if len(all_values) > 1:
                st.write("두 번째 행 (첫 데이터):", all_values[1])
        
        # 헤더 확인
        headers = all_values[0] if all_values else []
        st.write("헤더 목록:", headers)
        
        # 면접자명과 면접자이메일 컬럼 인덱스 찾기
        name_col_idx = None
        email_col_idx = None
        
        for i, header in enumerate(headers):
            if '면접자명' in str(header):
                name_col_idx = i
            if '면접자이메일' in str(header):
                email_col_idx = i
        
        st.write(f"면접자명 컬럼 인덱스: {name_col_idx}")
        st.write(f"면접자이메일 컬럼 인덱스: {email_col_idx}")
        
        if name_col_idx is None or email_col_idx is None:
            st.error("면접자명 또는 면접자이메일 컬럼을 찾을 수 없습니다.")
            return []
        
        # 데이터 처리
        candidates = []
        for i, row in enumerate(all_values[1:], 1):  # 헤더 제외
            if len(row) > max(name_col_idx, email_col_idx):
                name = str(row[name_col_idx]).strip() if name_col_idx < len(row) else ""
                email = str(row[email_col_idx]).strip() if email_col_idx < len(row) else ""
                
                st.write(f"행 {i}: 이름='{name}', 이메일='{email}'")
                
                if name and email:
                    candidates.append({
                        'name': name,
                        'email': email,
                        'row_number': i + 1,
                        'raw_data': row
                    })
        
        st.write(f"추출된 면접자 수: {len(candidates)}")
        return candidates
        
    except Exception as e:
        st.error(f"면접자 정보 조회 실패: {e}")
        import traceback
        st.error(traceback.format_exc())
        return []

def normalize_text(text: str) -> str:
    """텍스트 정규화"""
    if not text:
        return ""
    return str(text).strip().lower().replace(" ", "")

def find_candidate_in_sheet(name: str, email: str):
    """🔍 구글 시트에서 특정 면접자 찾기 (디버깅 강화)"""
    try:
        st.write("🔍 **디버깅: 면접자 검색 과정**")
        
        candidates = get_candidates_from_sheet()
        
        # 정규화된 검색
        normalized_name = normalize_text(name)
        normalized_email = normalize_text(email)
        
        st.write(f"검색할 정규화된 이름: '{normalized_name}'")
        st.write(f"검색할 정규화된 이메일: '{normalized_email}'")
        
        matching_candidates = []
        
        for candidate in candidates:
            cand_name = normalize_text(candidate['name'])
            cand_email = normalize_text(candidate['email'])
            
            st.write(f"비교 중 - DB이름: '{cand_name}', DB이메일: '{cand_email}'")
            
            # 이름과 이메일이 모두 일치하는 경우
            name_match = normalized_name == cand_name
            email_match = normalized_email == cand_email
            
            st.write(f"  이름 일치: {name_match}, 이메일 일치: {email_match}")
            
            if name_match and email_match:
                st.success(f"✅ 매칭 성공! 행 {candidate['row_number']}")
                matching_candidates.append(candidate)
        
        st.write(f"최종 매칭된 면접자 수: {len(matching_candidates)}")
        return matching_candidates
        
    except Exception as e:
        st.error(f"면접자 검색 실패: {e}")
        import traceback
        st.error(traceback.format_exc())
        return []

def find_full_request_id(short_id: str):
    """축약된 요청ID로 전체 ID 찾기"""
    try:
        if not db:
            return None
            
        # "..." 제거
        clean_id = short_id.replace('...', '')
        
        all_requests = db.get_all_requests()
        for request in all_requests:
            if request.id.startswith(clean_id):
                return request.id
        
        return None
        
    except Exception as e:
        return None

def find_candidate_requests(name: str, email: str):
    """🔧 구글 시트 기반 면접자 요청 찾기"""
    try:
        st.write("🔍 **디버깅: 요청 찾기 과정**")
        
        if not db:
            st.error("데이터베이스 연결이 없습니다.")
            return []
            
        # 1. 구글 시트에서 먼저 확인
        sheet_candidates = find_candidate_in_sheet(name, email)
        
        if not sheet_candidates:
            st.warning("구글 시트에서 매칭되는 면접자를 찾지 못했습니다.")
            return []
        
        st.success(f"구글 시트에서 {len(sheet_candidates)}명의 면접자를 찾았습니다.")
        
        # 2. 데이터베이스에서 모든 요청 가져와서 매칭
        all_requests = db.get_all_requests()
        st.write(f"데이터베이스 전체 요청 수: {len(all_requests)}")
        
        matching_requests = []
        
        # 이름과 이메일로 직접 검색
        for request in all_requests:
            req_name = normalize_text(request.candidate_name)
            req_email = normalize_text(request.candidate_email)
            search_name = normalize_text(name)
            search_email = normalize_text(email)
            
            st.write(f"DB 요청 비교: '{req_name}' vs '{search_name}', '{req_email}' vs '{search_email}'")
            
            if req_name == search_name and req_email == search_email:
                st.success(f"✅ 요청 매칭 성공: {request.id[:8]}...")
                matching_requests.append(request)
        
        st.write(f"최종 매칭된 요청 수: {len(matching_requests)}")
        return matching_requests
        
    except Exception as e:
        st.error(f"요청 조회 중 오류: {e}")
        import traceback
        st.error(traceback.format_exc())
        return []

# 면접자 앱에서는 pages 폴더 숨기기
def hide_pages():
    """면접자 앱에서 불필요한 페이지 숨기기"""
    hide_streamlit_style = """
    <style>
    .css-1d391kg {display: none}  /* 사이드바 페이지 링크 숨기기 */
    section[data-testid="stSidebar"] > div:first-child {display: none}  /* 사이드바 네비게이션 숨기기 */
    </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def show_candidate_login():
    """🔧 구글 시트 연동 면접자 인증 페이지"""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 40px; border-radius: 15px; text-align: center; margin: 30px 0; box-shadow: 0 10px 30px rgba(40,167,69,0.3);">
        <div style="font-size: 3rem; margin-bottom: 20px;">🔐</div>
        <h1 style="margin: 0 0 15px 0; font-size: 2rem; font-weight: 300;">면접자 인증</h1>
        <p style="font-size: 1.1rem; opacity: 0.9; margin: 0;">이름과 이메일 주소를 입력하여 면접 일정을 확인하세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 🔧 구글 시트 연결 상태 확인
    if not google_sheet:
        st.error("❌ 구글 시트에 연결할 수 없습니다. 관리자에게 문의해주세요.")
        return
    
    # 🔍 디버깅 모드 토글
    debug_mode = st.checkbox("🔍 디버깅 모드 (개발자용)", value=False)
    
    if debug_mode:
        st.write("### 🔍 디버깅 정보")
        
        # 구글 시트 연결 상태
        st.write(f"**구글 시트 연결 상태:** {'✅ 연결됨' if google_sheet else '❌ 연결 안됨'}")
        st.write(f"**데이터베이스 연결 상태:** {'✅ 연결됨' if db else '❌ 연결 안됨'}")
        
        # 구글 시트 데이터 미리보기
        if st.button("🔄 구글 시트 데이터 새로고침"):
            st.cache_resource.clear()
            st.rerun()
        
        with st.expander("📋 구글 시트 원시 데이터 확인", expanded=False):
            try:
                if google_sheet:
                    all_values = google_sheet.get_all_values()
                    if all_values:
                        df = pd.DataFrame(all_values[1:], columns=all_values[0])
                        st.dataframe(df, width='stretch')
                        st.write(f"총 {len(all_values)-1}행의 데이터")
                    else:
                        st.warning("구글 시트가 비어있습니다.")
            except Exception as e:
                st.error(f"데이터 로드 실패: {e}")
    
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
            
            submitted = st.form_submit_button("🔍 면접 일정 확인", width='stretch', type="primary")
            
            if submitted:
                if not candidate_name.strip():
                    st.error("❌ 이름을 입력해주세요.")
                elif not candidate_email.strip():
                    st.error("❌ 이메일 주소를 입력해주세요.")
                else:
                    # 🔧 구글 시트에서 면접자 정보 확인
                    with st.spinner("🔍 면접자 정보를 확인하고 있습니다..."):
                        
                        if debug_mode:
                            st.write("### 🔍 실시간 검색 과정")
                        
                        matching_requests = find_candidate_requests(candidate_name.strip(), candidate_email.strip())
                    
                    if matching_requests:
                        st.session_state.authenticated_candidate = {
                            'name': candidate_name.strip(),
                            'email': candidate_email.strip()
                        }
                        st.session_state.candidate_requests = matching_requests
                        st.success(f"✅ {len(matching_requests)}건의 면접 요청을 찾았습니다!")
                        
                        if not debug_mode:  # 디버깅 모드가 아닐 때만 자동 이동
                            st.rerun()
                    else:
                        st.error("❌ 입력하신 정보와 일치하는 면접 요청을 찾을 수 없습니다.")
                        
                        # 🔧 상세 디버깅 정보 항상 표시
                        with st.expander("🔍 상세 확인", expanded=True):
                            st.write("**입력하신 정보:**")
                            st.write(f"- 이름: `{candidate_name.strip()}`")
                            st.write(f"- 이메일: `{candidate_email.strip()}`")
                            st.write(f"- 정규화된 이름: `{normalize_text(candidate_name.strip())}`")
                            st.write(f"- 정규화된 이메일: `{normalize_text(candidate_email.strip())}`")
                        
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
        if st.button("🚪 로그아웃", width='stretch'):
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
            st.write("요청 상세 정보가 여기에 표시됩니다.")
            # show_request_detail(request, i) 함수는 나머지 코드와 함께 추가

def main():
    # 불필요한 페이지 숨기기
    hide_pages()
    
    st.title("👤 면접 일정 선택")
    st.caption("면접자 전용 독립 페이지")
    
    # 🔧 새로운 인증 방식: 이름 + 이메일
    if 'authenticated_candidate' not in st.session_state:
        show_candidate_login()
    else:
        show_candidate_dashboard()

if __name__ == "__main__":
    main()
