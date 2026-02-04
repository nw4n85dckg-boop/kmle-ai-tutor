import streamlit as st
import os
import re
import sqlite3
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from fpdf import FPDF
from PIL import Image
import base64
import io

# --- 1. 환경 및 기본 설정 ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# [2026.02.04 기준 최신 모델]
TARGET_MODEL = "models/gemini-3-pro-preview"

# 페이지 설정 (가장 먼저 실행되어야 함)
st.set_page_config(
    page_title="KMLE AI Tutor v8.1",
    page_icon="🌸",
    layout="wide"
)

# 커스텀 CSS (파스텔톤 UI)
st.markdown("""
<style>
    /* 전체 배경: 크림 화이트 */
    .stApp { background-color: #FFFDF9; }
    
    /* 로그인 박스 스타일 */
    .auth-container {
        background-color: white;
        padding: 40px;
        border-radius: 20px;
        box-shadow: 0px 4px 12px rgba(0,0,0,0.1);
        border: 2px solid #E1BEE7;
        text-align: center;
    }
    
    /* 사이드바 */
    section[data-testid="stSidebar"] {
        background-color: #F3E5F5;
        border-right: 3px solid #E1BEE7;
    }

    /* 채팅 메시지 스타일 */
    div[data-testid="stChatMessage"]:nth-child(odd) {
        background-color: #E0F7FA;
        border: 1px solid #B2EBF2;
    }
    div[data-testid="stChatMessage"]:nth-child(even) {
        background-color: #FCE4EC;
        border: 1px solid #F8BBD0;
    }
    
    /* 이미지 링크 버튼 */
    .img-link-btn {
        display: inline-block;
        background-color: #FFF59D;
        color: #5D4037;
        padding: 5px 12px;
        border-radius: 15px;
        border: 1px solid #FFF176;
        text-decoration: none;
        font-size: 0.9em;
        margin-top: 5px;
    }
    .img-link-btn:hover { background-color: #FFEE58; }
</style>
""", unsafe_allow_html=True)

if not api_key:
    st.error("❌ API 키가 없습니다. .env 파일을 확인해주세요.")
    st.stop()

@st.cache_resource
def get_client():
    return genai.Client(api_key=api_key)

client = get_client()

# --- 2. 데이터베이스 (SQLite) ---
def init_db():
    conn = sqlite3.connect('kmle_users.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT)''')
    # 이미지 데이터는 무거우니 DB엔 텍스트만 저장하고, 세션에서만 이미지를 보여줍니다.
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT, 
                  subject TEXT, 
                  role TEXT, 
                  content TEXT, 
                  timestamp DATETIME)''')
    conn.commit()
    return conn

conn = init_db()

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def save_message(username, subject, role, content):
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (username, subject, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
              (username, subject, role, content, datetime.now()))
    conn.commit()

def load_history(username, subject):
    c = conn.cursor()
    c.execute("SELECT role, content FROM chat_history WHERE username=? AND subject=? ORDER BY timestamp ASC", (username, subject))
    return c.fetchall()

# [추가] 메시지 삭제 함수 (DB + Session 동기화)
def delete_message(index, username, subject, content):
    # 1. DB에서 삭제
    c = conn.cursor()
    # 안전을 위해 내용, 작성자, 과목이 일치하는 가장 최근 항목 1개를 삭제
    try:
        c.execute("""
            DELETE FROM chat_history 
            WHERE id = (
                SELECT id FROM chat_history 
                WHERE username=? AND subject=? AND content=? 
                ORDER BY timestamp DESC LIMIT 1
            )
        """, (username, subject, content))
        conn.commit()
    except Exception as e:
        print(f"삭제 오류: {e}")

    # 2. 세션(화면)에서 삭제
    if index < len(st.session_state.messages):
        del st.session_state.messages[index]
    
    st.rerun()

# --- 3. PDF 출력 기능 (한글 지원) ---
def export_to_pdf(chat_history, username):
    pdf = FPDF()
    pdf.add_page()
    
    # 폰트 경로 설정 (같은 폴더에 NanumGothic.ttf 필수)
    font_name = 'NanumGothic.ttf'
    font_path = os.path.join(os.getcwd(), font_name)
    
    if not os.path.exists(font_path):
        return None
        
    try:
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', size=10)
    except Exception as e:
        return None

    # 헤더
    pdf.set_font_size(16)
    pdf.cell(0, 10, f"KMLE AI Tutor - Study Note", 0, 1, 'C')
    pdf.set_font_size(10)
    pdf.cell(0, 10, f"Dr. {username} | Date: {datetime.now().strftime('%Y-%m-%d')}", 0, 1, 'R')
    pdf.ln(5)
    pdf.line(10, 30, 200, 30)
    pdf.ln(10)
    
    # 본문
    for role, text in chat_history:
        role_str = "Tutor (AI)" if role == "assistant" else "Me"
        
        # 화자 표시
        pdf.set_text_color(100, 75, 150) # 보라색 계열
        pdf.set_font_size(11)
        pdf.cell(0, 8, f"[{role_str}]", 0, 1)
        
        # 내용 표시
        pdf.set_text_color(0, 0, 0) # 검정
        pdf.set_font_size(10)
        
        # HTML 태그 및 마크다운 제거
        clean_text = re.sub('<[^<]+?>', '', text) 
        clean_text = clean_text.replace("**", "").replace("__", "")
        
        pdf.multi_cell(0, 6, clean_text)
        pdf.ln(4)
        
    # [핵심 수정] bytearray를 bytes로 변환하여 반환
    return bytes(pdf.output(dest='S'))

# --- 4. 로그인 페이지 ---
def login_page():
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<div class='auth-container'>", unsafe_allow_html=True)
        st.title("🩺 KMLE AI Tutor")
        st.subheader("Login (v8.1)")
        
        menu = ["로그인", "회원가입"]
        choice = st.selectbox("메뉴", menu)
        
        username = st.text_input("아이디")
        password = st.text_input("비밀번호", type='password')
        
        if choice == "회원가입":
            if st.button("가입하기"):
                c = conn.cursor()
                c.execute("SELECT * FROM users WHERE username = ?", (username,))
                if c.fetchone():
                    st.warning("이미 존재하는 아이디입니다.")
                else:
                    c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                              (username, make_hashes(password)))
                    conn.commit()
                    st.success("가입 성공! 로그인 탭으로 이동하세요.")
                    
        elif choice == "로그인":
            if st.button("접속하기"):
                c = conn.cursor()
                c.execute("SELECT * FROM users WHERE username = ? AND password = ?", 
                          (username, make_hashes(password)))
                if c.fetchone():
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 틀렸습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

# --- 5. 메인 앱 (채팅) ---
def main_app():
    # 1. 초기화 (가장 먼저!)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # 2. 사이드바 설정 (수정됨)
    with st.sidebar:
        st.title(f"👨‍⚕️ Dr. {st.session_state.username}")
        
        # [복구] Gemini 연결 상태 표시
        st.markdown(f"""
        <div style='background-color: #EDE7F6; padding: 10px; border-radius: 10px; border: 1px solid #D1C4E9; margin-bottom: 10px;'>
            <small>🧠 Main Brain</small><br>
            <strong style='color: #673AB7;'>Gemini 3.0 Pro</strong><br>
            <span style='color: green;'>● System Active</span>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("로그아웃", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
            
        st.markdown("---")
        
        # [KMLE 표준 17과목 목차]
        subjects = {
            "01. 순환기 (Cardiology)": "💖",
            "02. 호흡기 (Pulmonology)": "🌬️",
            "03. 소화기 (Gastroenterology)": "🍩",
            "04. 간담췌 (Hepatobiliary)": "🍺",
            "05. 신장 (Nephrology)": "💧",
            "06. 내분비 (Endocrinology)": "🍬",
            "07. 감염 (Infectious Diseases)": "🦠",
            "08. 혈액/종양 (Hemato-Oncology)": "🩸",
            "09. 류마티스/알레르기": "🦴",
            "10. 외과 (General Surgery)": "🔪",
            "11. 산과 (Obstetrics)": "🤰",
            "12. 부인과 (Gynecology)": "🎀",
            "13. 소아청소년과 (Pediatrics)": "🧸",
            "14. 정신건강의학과 (Psychiatry)": "🧩",
            "15. 마이너 (안과/이비인후/피부/비뇨)": "👁️",
            "16. 예방의학 (Preventive Med)": "🛡️",
            "17. 의료법규 (Medical Law)": "⚖️"
        }
        
        selected_subject = st.selectbox("학습 과목 선택", list(subjects.keys()))
        current_icon = subjects[selected_subject]
        
        st.markdown("---")
        uploaded_file = st.file_uploader("📸 자료/사진 업로드", type=["jpg", "png", "jpeg"])
        st.markdown("---")
        
        # [수정] 선택적 PDF 다운로드 로직
        # session_state에 저장된 체크박스 값들을 확인하여 필터링
        if st.session_state.messages:
            selected_msgs = []
            for i, msg in enumerate(st.session_state.messages):
                # 키 이름: f"chk_{i}" (아래 채팅 렌더링 부분 참고)
                # 기본값은 True(체크됨)로 가정
                if st.session_state.get(f"chk_{i}", True): 
                    selected_msgs.append((msg['role'], msg['content']))
            
            if selected_msgs:
                pdf_result = export_to_pdf(selected_msgs, st.session_state.username)
                if pdf_result:
                    st.download_button(
                        label=f"📄 선택된 {len(selected_msgs)}개 대화 PDF 저장",
                        data=pdf_result,
                        file_name=f"KMLE_{selected_subject[:2]}_{st.session_state.username}.pdf",
                        mime="application/pdf"
                    )
            else:
                st.caption("PDF로 저장할 대화를 선택해주세요.")

    # 3. 메인 헤더
    st.title(f"{current_icon} {selected_subject}")
    st.caption(f"🚀 Powered by Gemini 3 Pro | 📅 2026-02-04 Ver.")

    # 4. 과목 변경 및 DB 로드 로직
    if "current_subject" not in st.session_state:
        st.session_state.current_subject = selected_subject

    # 과목 변경 시
    if st.session_state.current_subject != selected_subject:
        st.session_state.current_subject = selected_subject
        st.session_state.messages = [] 
        history = load_history(st.session_state.username, selected_subject)
        for role, content in history:
            st.session_state.messages.append({"role": role, "content": content})
            
    # 첫 로드 시
    if not st.session_state.messages:
        history = load_history(st.session_state.username, selected_subject)
        if history:
             for role, content in history:
                st.session_state.messages.append({"role": role, "content": content})

    # 5. 채팅 메시지 렌더링 (수정됨: 삭제 버튼 및 선택 체크박스 추가)
    # enumerate를 사용하여 인덱스(i)를 추적
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            # 이미지 표시
            if "image" in message:
                st.image(message["image"], width=300)
            
            # 텍스트 표시
            st.markdown(message["content"], unsafe_allow_html=True)
            
            # [기능 추가] 메시지 하단 컨트롤 패널 (User 메시지는 삭제만, AI는 PDF선택까지)
            # 깔끔하게 보이기 위해 expander나 작은 컬럼 사용
            col_pdf, col_del, col_space = st.columns([0.2, 0.2, 0.6])
            
            with col_pdf:
                # PDF 포함 여부 체크박스 (기본값 True)
                # key를 유니크하게 설정해야 함 (chk_인덱스)
                st.checkbox("PDF 저장", value=True, key=f"chk_{i}", label_visibility="collapsed")
                
            with col_del:
                # 삭제 버튼 (누르면 즉시 DB 및 화면에서 삭제)
                if st.button("🗑️", key=f"del_{i}", help="이 대화 삭제"):
                    delete_message(i, st.session_state.username, selected_subject, message["content"])
    # 6. 사용자 입력 처리
    prompt = st.chat_input("질문하세요! (ex: 50세 여자가 갑자기 배가 아파서...)")

    if prompt:
        # 이미지 처리
        image_obj = None
        if uploaded_file:
            image_obj = Image.open(uploaded_file)
            # 이미지가 있으면 채팅창에 미리 보여주기
            with st.chat_message("user"):
                st.image(image_obj, width=300)
        
        # User 메시지 표시 및 저장
        # (DB에는 이미지를 저장하지 않음 - 용량 문제)
        save_message(st.session_state.username, selected_subject, "user", prompt)
        
        user_msg = {"role": "user", "content": prompt}
        if image_obj: user_msg["image"] = image_obj
        st.session_state.messages.append(user_msg)
        
        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 응답
        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("💫 *Gemini 3 Pro가 분석 중...*")
            
            system_instruction = f"""
            당신은 'KMLE AI Tutor'입니다. 
            현재 과목: {selected_subject}
            
            [Role]
            친절하지만 핵심을 찌르는 족보 과외 선생님 (파스텔톤 어조 "~해요")
            
            [Response Format]
            1. **Impression (R/O)**: 가장 의심되는 진단명 1개 (필요시 DDx 1~2개).
            2. **Key Clue**: 문제 해결의 결정적 단서를 [대괄호]로 표시.
            3. **Diagnostic Plan**: 
               - Best Initial Test (가장 먼저)
               - Confirmatory Test (확진)
            4. **Treatment**: Treatment of Choice (최선 치료).
            
            [Visual Link]
            중요한 해부학 구조, 병변 사진이 필요하면 반드시 문장 끝에 [이미지 검색: 검색어] 태그를 붙이세요.
            """

            # 모델 입력 구성
            inputs = [system_instruction, prompt]
            if image_obj:
                inputs.append(image_obj)

            try:
                response = client.models.generate_content(
                    model=TARGET_MODEL,
                    contents=inputs
                )
                full_text = response.text
                
                # 이미지 검색 태그 변환
                def link_replacer(match):
                    keyword = match.group(1)
                    url = f"https://www.google.com/search?tbm=isch&q={keyword.replace(' ', '+')}"
                    return f'<br><a href="{url}" target="_blank" class="img-link-btn">🖼️ {keyword} 도해 보기</a><br>'
                
                final_text = re.sub(r'\[이미지 검색:\s*(.*?)\]', link_replacer, full_text)
                
                placeholder.markdown(final_text, unsafe_allow_html=True)
                
                save_message(st.session_state.username, selected_subject, "assistant", final_text)
                st.session_state.messages.append({"role": "assistant", "content": final_text})

            except Exception as e:
                st.error(f"⚠️ 에러 발생: {e}")

# --- 7. 실행 진입점 ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if st.session_state.logged_in:
    main_app()
else:
    login_page()