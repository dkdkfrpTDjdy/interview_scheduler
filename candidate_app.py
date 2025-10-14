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

# 구글 시트 연결 함수
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
    # 모든 공백 제거, 소문자 변환
    return str(text).strip().lower().replace(" ", "").replace("\n", "").replace("\t", "")

def find_candidate_requests(name: str, email: str):
    """구글 시트에서 직접 면접자 요청 찾기 - 개선된 버전"""
    try:
        if not google_sheet:
            return []
        
        # 구글 시트에서 모든 데이터 가져오기
        all_values = google_sheet.get_all_values()
        if not all_values or len(all_values) < 2:  # 헤더 + 최소 1개 데이터
            return []
        
        headers = all_values[0]  # 첫 번째 행이 헤더
        
        # 🔧 컬럼 인덱스 찾기 - 정확한 컬럼명으로 매칭
        try:
            name_col_idx = None
            email_col_idx = None
            
            # 가능한 컬럼명들 체크
            for i, header in enumerate(headers):
                header_normalized = normalize_text(header)
                if header_normalized in ['면접자명', '면접자이름', '이름', 'name', 'candidate_name']:
                    name_col_idx = i
                elif header_normalized in ['면접자이메일', '면접자메일', '이메일', 'email', 'candidate_email']:
                    email_col_idx = i
            
            if name_col_idx is None or email_col_idx is None:
                # 컬럼을 찾지 못한 경우, 전체 헤더 출력하여 디버깅
                st.error(f"❌ 필요한 컬럼을 찾을 수 없습니다. 현재 컬럼: {headers}")
                return []
                
        except Exception as e:
            st.error(f"❌ 헤더 분석 실패: {e}")
            return []
        
        # 정규화된 검색어
        normalized_search_name = normalize_text(name)
        normalized_search_email = normalize_text(email)
        
        matching_requests = []
        
        # 데이터 행들 순회 (헤더 제외)
        for row_idx, row in enumerate(all_values[1:], start=2):  # 2부터 시작 (1-based, 헤더 제외)
            try:
                # 안전하게 데이터 추출
                row_name = row[name_col_idx] if name_col_idx < len(row) else ""
                row_email = row[email_col_idx] if email_col_idx < len(row) else ""
                
                # 정규화하여 비교
                normalized_row_name = normalize_text(row_name)
                normalized_row_email = normalize_text(row_email)
                
                # 매칭 확인
                if (normalized_row_name == normalized_search_name and 
                    normalized_row_email == normalized_search_email):
                    
                    # 매칭된 경우 전체 행 데이터를 딕셔너리로 변환
                    request_obj = {'_row_number': row_idx}  # 행 번호 저장
                    
                    for col_idx, header in enumerate(headers):
                        value = row[col_idx] if col_idx < len(row) else ""
                        request_obj[header] = value
                    
                    # 추가 필드 매핑 (하위 호환성)
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
                # 개별 행 처리 실패는 넘어감
                continue
        
        return matching_requests
        
    except Exception as e:
        st.error(f"❌ 데이터 조회 중 오류: {e}")
        return []

def parse_proposed_slots(slots_str: str):
    """제안일시목록 문자열을 파싱"""
    if not slots_str:
        return []
    
    slots = []
    parts = slots_str.split(' | ')
    
    for part in parts:
        try:
            # "2025-10-16 09:00(60분)" 형식 파싱
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
            st.error("❌ 구글 시트 연결이 없습니다.")
            return False
        
        if 'row_number' not in request:
            st.error("❌ 행 번호 정보가 없습니다.")
            return False
        
        row_number = request['row_number']
        
        # 현재 시트 구조 확인
        headers = google_sheet.row_values(1)
        
        # 컬럼 인덱스 찾기 (0-based에서 1-based로 변환)
        try:
            confirmed_col = headers.index('확정일시') + 1
            status_col = headers.index('상태') + 1  
            note_col = headers.index('면접자요청사항') + 1
            update_col = headers.index('마지막업데이트') + 1
        except ValueError as e:
            st.error(f"❌ 필요한 컬럼을 찾을 수 없습니다: {e}")
            return False
        
        # 업데이트 실행
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        # 개별 셀 업데이트
        if is_alternative_request:
            # 다른 일정 요청인 경우
            google_sheet.update_cell(row_number, confirmed_col, "")  # 확정일시 비움
            google_sheet.update_cell(row_number, status_col, "일정재조율요청")  # 상태 변경
            google_sheet.update_cell(row_number, note_col, f"[다른 일정 요청] {candidate_note}")  # 요청사항
            google_sheet.update_cell(row_number, update_col, current_time)  # 업데이트 시간
            
        else:
            # 정규 일정 선택인 경우
            if selected_slot:
                confirmed_datetime = f"{selected_slot['date']} {selected_slot['time']}({selected_slot['duration']}분)"
                note_text = f"[확정시 요청사항] {candidate_note}" if candidate_note.strip() else ""
                
                google_sheet.update_cell(row_number, confirmed_col, confirmed_datetime)  # 확정일시
                google_sheet.update_cell(row_number, status_col, "확정완료")  # 상태 변경
                google_sheet.update_cell(row_number, note_col, note_text)  # 요청사항
                google_sheet.update_cell(row_number, update_col, current_time)  # 업데이트 시간
            else:
                st.error("❌ 선택된 슬롯 정보가 없습니다.")
                return False
        
        # 업데이트 확인을 위한 잠시 대기
        time.sleep(1)
        
        return True
        
    except Exception as e:
        st.error(f"❌ 시트 업데이트 실패: {e}")
        return False

def force_refresh_candidate_data(name, email):
    """면접자 데이터 강제 새로고침"""
    try:
        # Streamlit 캐시 클리어
        try:
            st.cache_resource.clear()
        except:
            try:
                st.experimental_memo.clear()
                st.experimental_singleton.clear()
            except:
                pass
        
        # 구글 시트 재연결
        global google_sheet
        google_sheet = init_google_sheet()
        
        if not google_sheet:
            return []
        
        # 데이터 다시 조회
        return find_candidate_requests(name, email)
        
    except Exception as e:
        return []

# 면접자 앱에서는 pages 폴더 숨기기
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
    """면접자 인증 페이지"""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 40px; border-radius: 15px; text-align: center; margin: 30px 0; box-shadow: 0 10px 30px rgba(40,167,69,0.3);">
        <div style="font-size: 3rem; margin-bottom: 20px;">🔐</div>
        <h1 style="margin: 0 0 15px 0; font-size: 2rem; font-weight: 300;">면접자 인증</h1>
        <p style="font-size: 1.1rem; opacity: 0.9; margin: 0;">이름과 이메일 주소를 입력하여 면접 일정을 확인하세요</p>
    </div>
    """, unsafe_allow_html=True)
    
    if not google_sheet:
        st.error("❌ 구글 시트에 연결할 수 없습니다. 관리자에게 문의해주세요.")
        return
    
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
                placeholder="example@naver.com",
                help="면접 신청 시 입력한 이메일 주소를 정확히 입력해주세요"
            )
            
            submitted = st.form_submit_button("🔍 면접 일정 확인", use_container_width=True, type="primary")
            
            if submitted:
                if not candidate_name.strip():
                    st.error("❌ 이름을 입력해주세요.")
                elif not candidate_email.strip():
                    st.error("❌ 이메일 주소를 입력해주세요.")
                else:
                    with st.spinner("🔍 면접자 정보를 확인하고 있습니다..."):
                        matching_requests = find_candidate_requests(candidate_name.strip(), candidate_email.strip())
                    
                    if matching_requests:
                        st.session_state.authenticated_candidate = {
                            'name': candidate_name.strip(),
                            'email': candidate_email.strip()
                        }
                        st.session_state.candidate_requests = matching_requests
                        st.success(f"✅ {len(matching_requests)}건의 면접 요청을 찾았습니다!")
                        st.rerun()
                    else:
                        st.error("❌ 입력하신 정보와 일치하는 면접 요청을 찾을 수 없습니다.")
                        
                        # 🔧 디버깅을 위한 추가 정보 (임시)
                        if google_sheet:
                            try:
                                headers = google_sheet.row_values(1)
                                st.info(f"💡 구글 시트 연결됨. 컬럼: {headers}")
                                
                                # 첫 번째 데이터 행 확인
                                if len(google_sheet.get_all_values()) > 1:
                                    first_data_row = google_sheet.row_values(2)
                                    st.info(f"💡 첫 번째 데이터: {first_data_row}")
                                else:
                                    st.warning("⚠️ 구글 시트에 데이터가 없습니다.")
                            except Exception as e:
                                st.error(f"시트 확인 중 오류: {e}")

    # 도움말
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="background-color: #f8f9fa; padding: 25px; border-radius: 12px; text-align: center; border: 1px solid #dee2e6;">
            <h4 style="color: #495057; margin-top: 0;">💡 이용 안내</h4>
            <div style="text-align: left; margin: 15px 0;">
                <p style="margin: 8px 0; color: #6c757d;">• 면접 신청 시 입력한 <strong>정확한 이름과 이메일</strong>을 입력해주세요</p>
                <p style="margin: 8px 0; color: #6c757d;">• 대소문자와 띄어쓰기는 <strong>자동으로 처리</strong>됩니다</p>
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
        if st.button("🚪 로그아웃", use_container_width=True):
            for key in ['authenticated_candidate', 'candidate_requests']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    if not candidate_requests:
        st.info("면접 요청을 찾을 수 없습니다.")
        return
    
    st.subheader(f"📋 나의 면접 일정 ({len(candidate_requests)}건)")
    
    # 각 요청 처리
    for i, request in enumerate(candidate_requests):
        with st.expander(f"📅 {request['position_name']} - {request['created_at']} 신청", expanded=len(candidate_requests)==1):
            show_request_detail(request, i)

def show_request_detail(request, index):
    # ✅ 폼 제출 후 상태 초기화 로직 추가
    form_key = f"candidate_selection_{index}"
    
    # 폼 제출 감지를 위한 상태 관리
    if f"submitted_{form_key}" not in st.session_state:
        st.session_state[f"submitted_{form_key}"] = False
    
    with st.form(form_key):
        # 라디오 버튼의 기본값을 동적으로 설정
        default_index = 0 if not st.session_state[f"submitted_{form_key}"] else None
        
        selected_option = st.radio(
            "원하는 면접 일정을 선택해주세요:",
            options=range(len(slot_options)),
            format_func=lambda x: slot_options[x],
            index=default_index,  # ← 상태에 따른 기본값 설정
            key=f"radio_{form_key}"
        )
        
        submitted = st.form_submit_button("✅ 면접 일정 선택 완료", use_container_width=True, type="primary")
        
        if submitted:
            # 제출 상태 업데이트
            st.session_state[f"submitted_{form_key}"] = True
            
            # 처리 로직...
            if success:
                # ✅ 성공 시 관련 세션 상태 모두 초기화
                keys_to_clear = [k for k in st.session_state.keys() if f"_{index}" in k]
                for key in keys_to_clear:
                    del st.session_state[key]
                
                st.rerun()
    
    # 면접 정보 표시
    st.markdown(f"""
    <div style="background-color: white; padding: 25px; border-radius: 10px; border-left: 5px solid #28a745; margin: 20px 0; box-shadow: 0 2px 10px rgba(40,167,69,0.1);">
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #28a745; width: 120px;">포지션</td>
                <td style="padding: 10px 0; color: #333; font-size: 1.1rem; font-weight: bold;">{request['position_name']}</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #28a745;">면접관</td>
                <td style="padding: 10px 0; color: #333;">{request['interviewer_name']} (ID: {request['interviewer_id']})</td>
            </tr>
            <tr>
                <td style="padding: 10px 0; font-weight: bold; color: #28a745;">신청일</td>
                <td style="padding: 10px 0; color: #333;">{request['created_at']}</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)
    
    # 제안된 일정 파싱
    proposed_slots = parse_proposed_slots(request['proposed_slots'])
    
    if not proposed_slots:
        st.warning("⚠️ 면접관이 아직 가능한 일정을 입력하지 않았습니다.")
        
        # 새로고침 버튼 추가
        if st.button(f"🔄 상태 새로고침", key=f"refresh_{index}"):
            candidate_info = st.session_state.authenticated_candidate
            updated_requests = force_refresh_candidate_data(candidate_info['name'], candidate_info['email'])
            st.session_state.candidate_requests = updated_requests
            st.rerun()
        return
    
    st.write("**🗓️ 제안된 면접 일정 중 선택해주세요**")
    

    
    # 제안된 일정을 테이블로 표시
    table_html = """
    <table style="width: 100%; border-collapse: collapse; border: 2px solid #28a745; border-radius: 8px; overflow: hidden; margin: 15px 0;">
        <thead>
            <tr style="background-color: #28a745; color: white;">
                <th style="padding: 15px; text-align: center; font-weight: bold;">옵션</th>
                <th style="padding: 15px; text-align: center; font-weight: bold;">날짜</th>
                <th style="padding: 15px; text-align: center; font-weight: bold;">시간</th>
                <th style="padding: 15px; text-align: center; font-weight: bold;">소요시간</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for i, slot in enumerate(proposed_slots, 1):
        bg_color = "#f8f9fa" if i % 2 == 0 else "white"
        table_html += f"""
            <tr style="background-color: {bg_color};">
                <td style="padding: 15px; text-align: center; font-weight: bold;">옵션 {i}</td>
                <td style="padding: 15px; text-align: center; font-weight: bold;">{format_date_korean(slot['date'])}</td>
                <td style="padding: 15px; text-align: center; color: #007bff; font-weight: bold;">{slot['time']}</td>
                <td style="padding: 15px; text-align: center;">{slot['duration']}분</td>
            </tr>
        """
    
    st.markdown(table_html, unsafe_allow_html=True)
    
    # 선택 폼
    with st.form(f"candidate_selection_{index}"):
        slot_options = []
        for i, slot in enumerate(proposed_slots):
            slot_text = f"옵션 {i+1}: {format_date_korean(slot['date'])} {slot['time']} ({slot['duration']}분)"
            slot_options.append(slot_text)
        
        slot_options.append("❌ 제안된 일정으로는 불가능 (다른 일정 요청)")
        
        selected_option = st.radio(
            "원하는 면접 일정을 선택해주세요:",
            options=range(len(slot_options)),
            format_func=lambda x: slot_options[x]
        )
        
        candidate_note = ""
        if selected_option == len(slot_options) - 1:
            st.markdown("""
            <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); padding: 25px; border-radius: 12px; border-left: 6px solid #ffc107; margin: 25px 0;">
                <h4 style="color: #856404; margin-top: 0; font-size: 1.3rem;">📝 다른 일정 요청</h4>
                <p style="color: #856404; margin-bottom: 15px;">제안된 일정이 맞지 않으시나요? 가능한 일정을 구체적으로 알려주세요.</p>
            </div>
            """, unsafe_allow_html=True)
            
            candidate_note = st.text_area(
                "가능한 면접 일정이나 요청사항을 입력해주세요:",
                placeholder="예시:\n• 다음 주 화요일 오후 2시 이후 가능합니다\n• 월요일과 수요일은 전체 불가능합니다\n• 오전 시간대를 선호합니다\n• 온라인 면접을 희망합니다",
                height=150,
                help="구체적으로 작성해주시면 더 빠른 조율이 가능합니다"
            )
        
        submitted = st.form_submit_button("✅ 면접 일정 선택 완료", use_container_width=True, type="primary")
        
        if submitted:
            if 'row_number' not in request:
                st.error("❌ 요청 데이터에 문제가 있습니다. 페이지를 새로고침해주세요.")
                return
            
            if selected_option < len(proposed_slots):
                # 정규 일정 선택
                selected_slot = proposed_slots[selected_option]
                
                with st.spinner("📝 일정을 확정하고 있습니다..."):
                    success = update_sheet_selection(
                        request, 
                        selected_slot=selected_slot, 
                        candidate_note=candidate_note, 
                        is_alternative_request=False
                    )
                    
                    if success:
                        st.success("🎉 면접 일정이 확정되었습니다!")
                        st.info("📧 관련자 모두에게 확정 알림이 전송됩니다.")
                        
                        # 확정 정보 표시
                        st.markdown(f"""
                        <div style="background-color: #d4edda; padding: 20px; border-radius: 10px; margin: 20px 0; border-left: 5px solid #28a745;">
                            <h4 style="color: #155724; margin-top: 0;">📅 확정된 면접 일정</h4>
                            <p style="color: #155724; margin: 0;"><strong>{format_date_korean(selected_slot['date'])} {selected_slot['time']} ({selected_slot['duration']}분)</strong></p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.balloons()
                        
                        # 세션 데이터 강제 업데이트
                        time.sleep(2)
                        candidate_info = st.session_state.authenticated_candidate
                        updated_requests = force_refresh_candidate_data(candidate_info['name'], candidate_info['email'])
                        if updated_requests:
                            st.session_state.candidate_requests = updated_requests
                        
                        st.rerun()
                    else:
                        st.error("❌ 일정 확정 중 오류가 발생했습니다.")
            else:
                # 다른 일정 요청
                if not candidate_note.strip():
                    st.error("❌ 가능한 일정을 구체적으로 입력해주세요.")
                else:
                    with st.spinner("📝 일정 재조율 요청을 전송하고 있습니다..."):
                        success = update_sheet_selection(
                            request, 
                            selected_slot=None, 
                            candidate_note=candidate_note, 
                            is_alternative_request=True
                        )
                        
                        if success:
                            st.success("📧 일정 재조율 요청이 인사팀에 전달되었습니다!")
                            st.info("인사팀에서 검토 후 별도 연락드리겠습니다.")
                            
                            # 요청사항 표시
                            st.markdown(f"""
                            <div style="background-color: #d1ecf1; padding: 20px; border-radius: 10px; margin: 20px 0; border-left: 5px solid #17a2b8;">
                                <h4 style="color: #0c5460; margin-top: 0;">📝 전달된 요청사항</h4>
                                <p style="color: #0c5460; margin: 0; white-space: pre-line;">{candidate_note}</p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # 세션 업데이트를 위한 새로고침
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("❌ 일정 재조율 요청 전송 중 오류가 발생했습니다.")

def show_confirmed_schedule(request):
    """확정된 일정 표시"""
    st.markdown("""
    <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); padding: 30px; border-radius: 15px; border-left: 8px solid #28a745; margin: 20px 0; text-align: center;">
        <div style="font-size: 3rem; margin-bottom: 15px;">🎉</div>
        <h3 style="color: #155724; margin: 0 0 10px 0;">면접 일정이 확정되었습니다!</h3>
    </div>
    """, unsafe_allow_html=True)
    
    if request['confirmed_datetime']:
        st.markdown(f"""
        <div style="background-color: #d4edda; padding: 25px; border-radius: 10px; margin: 20px 0; text-align: center;">
            <h4 style="color: #155724; margin: 0;">📅 확정된 면접 일정</h4>
            <p style="color: #155724; font-size: 1.3rem; font-weight: bold; margin: 10px 0;">{request['confirmed_datetime']}</p>
            <p style="color: #155724; margin: 0;">면접관: {request['interviewer_name']}</p>
        </div>
        """, unsafe_allow_html=True)
    
    # 면접 준비 안내
    st.markdown("""
    <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 25px; border-radius: 12px; border-left: 6px solid #2196f3; margin: 25px 0;">
        <h4 style="color: #1565c0; margin-top: 0;">📝 면접 준비 안내</h4>
        <ul style="color: #1565c0; line-height: 1.8;">
            <li>⏰ 면접 당일 <strong>10분 전까지 도착</strong>해주세요</li>
            <li>📞 일정 변경이 필요한 경우 <strong>최소 24시간 전</strong>에 인사팀에 연락해주세요</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

def main():
    hide_pages()
    
    st.title("👤 면접 일정 선택")
    st.caption("면접자 전용 독립 페이지")
    
    if 'authenticated_candidate' not in st.session_state:
        show_candidate_login()
    else:
        show_candidate_dashboard()

if __name__ == "__main__":
    main()
