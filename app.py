import streamlit as st
import os
import re
from dotenv import load_dotenv
from google import genai
from PIL import Image

# --- 1. 환경 설정 ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# [최종 확정] 선생님이 제공해주신 리스트 중 최상위 모델
# 우회 없음. 오직 이 모델만 사용함.
TARGET_MODEL = "models/gemini-3-pro-preview"

if not api_key:
    st.error("❌ API 키가 없습니다. .env 파일을 확인해주세요.")
    st.stop()

@st.cache_resource
def get_client():
    return genai.Client(api_key=api_key)

client = get_client()

# --- 2. 디자인 설정 (Pastel Mongle UI) ---
st.set_page_config(
    page_title="KMLE AI Tutor - Gemini 3 Pro",
    page_icon="🌸",
    layout="wide"
)

st.markdown("""
<style>
    /* 전체 배경: 크림 화이트 */
    .stApp { background-color: #FFFDF9; }
    
    /* 사이드바: 연한 라벤더 */
    section[data-testid="stSidebar"] {
        background-color: #F3E5F5;
        border-right: 3px solid #E1BEE7;
    }

    /* 헤더 폰트 */
    h1 {
        color: #6A1B9A;
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 800;
        text-shadow: 1px 1px 0px #E1BEE7;
    }

    /* 채팅창 스타일 */
    .stChatInputContainer textarea {
        background-color: #FFFFFF;
        border-radius: 30px;
        border: 2px solid #CE93D8;
        color: #4A148C;
    }

    /* 유저 메시지 (우측) */
    div[data-testid="stChatMessage"]:nth-child(odd) {
        background-color: #E0F7FA;
        border: 2px solid #B2EBF2;
        border-radius: 25px 25px 5px 25px;
        padding: 18px;
        color: #006064;
        box-shadow: 2px 2px 8px rgba(0,0,0,0.05);
    }

    /* AI 메시지 (좌측) */
    div[data-testid="stChatMessage"]:nth-child(even) {
        background-color: #FCE4EC;
        border: 2px solid #F8BBD0;
        border-radius: 25px 25px 25px 5px;
        padding: 18px;
        color: #880E4F;
        box-shadow: 2px 2px 8px rgba(0,0,0,0.05);
    }

    /* 버튼 스타일 */
    div.stButton > button {
        background-color: #BA68C8;
        color: white;
        border-radius: 20px;
        border: none;
        font-weight: bold;
    }
    div.stButton > button:hover {
        background-color: #AB47BC;
        transform: scale(1.02);
    }
    
    /* 이미지 링크 버튼 스타일 */
    .img-link-btn {
        display: inline-block;
        background-color: #FFF59D;
        color: #5D4037;
        padding: 8px 15px;
        border-radius: 20px;
        border: 2px solid #FFF176;
        text-decoration: none;
        font-weight: bold;
        margin-top: 8px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    .img-link-btn:hover { background-color: #FFEE58; }
</style>
""", unsafe_allow_html=True)

# --- 3. 사이드바 ---
with st.sidebar:
    st.title("🌸 KMLE Premium")
    
    # 모델 정보 표시
    st.markdown(f"""
    <div style='background-color: #EDE7F6; padding: 15px; border-radius: 15px; border: 2px solid #D1C4E9;'>
        <small>🧠 Main Brain</small><br>
        <strong style='color: #673AB7; font-size: 1.0em;'>{TARGET_MODEL}</strong><br>
        <small style='color: green;'>● Status: Active</small>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    subjects = {
        "순환기 (Cardiology)": "💖",
        "호흡기 (Pulmonology)": "🌬️",
        "소화기 (Gastroenterology)": "🍩",
        "간담췌 (Hepatobiliary)": "🍺",
        "신장 (Nephrology)": "💧",
        "내분비 (Endocrinology)": "🍬",
        "혈액종양 (Hemato-Oncology)": "🩸",
        "감염 (Infectious Diseases)": "🦠",
        "류마티스/알레르기": "🦴",
        "소아청소년과 (Pediatrics)": "🧸",
        "산과 (Obstetrics)": "🤰",
        "부인과 (Gynecology)": "🎀",
        "정신건강의학과 (Psychiatry)": "🧩",
        "예방의학 (Preventive Med)": "🛡️",
        "외과 (General Surgery)": "🔪",
        "마이너 (안과/이비인후/피부)": "👁️",
        "의료법규 (Medical Law)": "⚖️"
    }
    
    selected_subject = st.selectbox("오늘의 과목 📝", list(subjects.keys()))
    current_icon = subjects[selected_subject]
    
    st.markdown("---")
    uploaded_file = st.file_uploader("📸 자료/사진 업로드", type=["jpg", "png", "jpeg"])
    
    if st.button("✨ 대화 초기화"):
        st.session_state.messages = []
        st.rerun()

# --- 4. 메인 화면 ---
st.title(f"{current_icon} {selected_subject}")
st.caption(f"🚀 Powered by Gemini 3 Pro Preview")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_subject" not in st.session_state:
    st.session_state.current_subject = selected_subject

if st.session_state.current_subject != selected_subject:
    st.session_state.messages = []
    st.session_state.current_subject = selected_subject

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "image" in message:
            st.image(message["image"], width=300)
        st.markdown(message["content"], unsafe_allow_html=True)

# --- 5. 채팅 로직 ---
prompt = st.chat_input("질문하세요!")

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
        image = None
        if uploaded_file:
            image = Image.open(uploaded_file)
            st.image(image, width=300)
    
    user_msg = {"role": "user", "content": prompt}
    if image: user_msg["image"] = image
    st.session_state.messages.append(user_msg)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown(f"💫 *Gemini 3 Pro가 분석 중입니다...*")
        
        system_instruction = f"""
        당신은 'KMLE 튜터'입니다.
        사용 모델: {TARGET_MODEL}
        
        [지침]
        1. **Deep Reasoning**: 최신 의학 지식(Harrison, Cecil) 기반의 심층 분석.
        2. **Tone**: 다정한 파스텔톤 말투 ("~해요").
        3. **Format**: 진단 -> 검사 -> 치료 (구조화).
        4. **Visuals**:  태그 필수.
        """
        
        inputs = [system_instruction, prompt]
        if image: inputs.append(image)

        try:
            # [직접 연결] 선생님이 지정하신 리스트의 최강 모델
            # 대체 로직(try-except failover) 없음. 오직 이것만 호출.
            response = client.models.generate_content(
                model=TARGET_MODEL,
                contents=inputs
            )
            full_text = response.text
            
            # 링크 변환
            def link_replacer(match):
                keyword = match.group(1)
                url = f"https://www.google.com/search?tbm=isch&q={keyword.replace(' ', '+')}"
                return f'<br><a href="{url}" target="_blank" class="img-link-btn">🖼️ {keyword} 도해 보기</a><br>'
            
            final_text = re.sub(r'\[이미지 검색:\s*(.*?)\]', link_replacer, full_text)
            
            placeholder.markdown(final_text, unsafe_allow_html=True)
            st.session_state.messages.append({"role": "assistant", "content": final_text})

        except Exception as e:
            st.error(f"⚠️ 모델 호출 오류: {e}")
            st.warning("제공해주신 모델 리스트의 ID가 정확한지, 혹은 API 키 권한을 확인해주세요.")