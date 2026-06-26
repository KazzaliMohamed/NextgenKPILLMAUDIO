import streamlit as st
import pandas as pd
from rapidfuzz import fuzz
from groq import Groq
from gtts import gTTS
import base64
import io

st.set_page_config(
    page_title="NextGen KPI Assistant",
    page_icon="📊",
    layout="wide"
)

# ---------- GROQ CLIENT ----------
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# ---------- HEADER ----------
st.markdown("""
    <h1 style='text-align: center; font-size: 36px;'>📊 NextGen KPI Assistant</h1>
    <p style='text-align: center; color: gray; font-size: 16px;'>Created by Kazzali Mohamed</p>
    <br>
""", unsafe_allow_html=True)

# ---------- LOAD DATA ----------
excel_file = "NextGen Metrics Library.xlsm"
df = pd.read_excel(excel_file, sheet_name="NextGen")
df.columns = df.columns.str.strip()
df = df[df["Metric title"].notna()]

# ---------- SESSION STATE ----------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_voice_index" not in st.session_state:
    st.session_state.last_voice_index = -1

# ---------- HELPER ----------
def clean(text):
    return text.lower().strip().lstrip("#").strip()

def text_to_speech(text):
    clean_text = text.replace("**", "").replace("*", "").replace("#", "").replace("_", "").replace("-", "")
    tts = gTTS(text=clean_text, lang="en", slow=False)
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    audio_data = base64.b64encode(audio_buffer.read()).decode()
    return f"""
    <audio id="kpiAudio" controls autoplay style="width:100%; margin-top:8px;">
        <source src="data:audio/mp3;base64,{audio_data}" type="audio/mp3">
    </audio>
    """

def find_match(query):
    metric_titles = df["Metric title"].astype(str).tolist()
    query_cleaned = clean(query)
    cleaned_titles = [clean(t) for t in metric_titles]
    best_score = 0
    best_index = None
    for i, title in enumerate(cleaned_titles):
        score = max(
            fuzz.ratio(query_cleaned, title),
            fuzz.partial_ratio(query_cleaned, title),
            fuzz.token_sort_ratio(query_cleaned, title),
            fuzz.token_set_ratio(query_cleaned, title)
        )
        if score > best_score:
            best_score = score
            best_index = i
    if best_index is not None and best_score >= 60:
        return metric_titles[best_index]
    return None

def find_multiple_matches(query, top_n=3):
    metric_titles = df["Metric title"].astype(str).tolist()
    query_cleaned = clean(query)
    cleaned_titles = [clean(t) for t in metric_titles]
    scores = []
    for i, title in enumerate(cleaned_titles):
        score = max(
            fuzz.ratio(query_cleaned, title),
            fuzz.partial_ratio(query_cleaned, title),
            fuzz.token_sort_ratio(query_cleaned, title),
            fuzz.token_set_ratio(query_cleaned, title)
        )
        scores.append((i, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    results = []
    for i, score in scores[:top_n]:
        if score >= 50:
            results.append(metric_titles[i])
    return results

def get_kpi_context(title):
    row = df[df["Metric title"] == title].iloc[0]
    exclude = {"ID"}
    lines = []
    for col, val in row.items():
        if col in exclude:
            continue
        if pd.isna(val) or not str(val).strip():
            continue
        lines.append(f"{col}: {val}")
    return "\n".join(lines)

def build_full_context():
    context = ""
    for _, row in df.iterrows():
        title = row.get("Metric title", "")
        if pd.isna(title):
            continue
        context += f"\n--- KPI: {title} ---\n"
        for col, val in row.items():
            if col == "ID":
                continue
            if pd.isna(val) or not str(val).strip():
                continue
            context += f"{col}: {val}\n"
    return context

def detect_intent(query):
    query_lower = query.lower()
    comparison_keywords = ["difference", "compare", "vs", "versus", "between", "differ", "contrast"]
    general_keywords = ["what is", "explain", "tell me", "how many", "which", "list", "all", "best"]
    for kw in comparison_keywords:
        if kw in query_lower:
            return "comparison"
    matched = find_match(query)
    if matched:
        score_check = max(
            fuzz.ratio(clean(query), clean(matched)),
            fuzz.token_sort_ratio(clean(query), clean(matched))
        )
        if score_check >= 65:
            return "single"
    for kw in general_keywords:
        if kw in query_lower:
            return "general"
    return "general"

def ask_llm(user_query, context, intent):
    if intent == "single":
        system_prompt = """You are a friendly KPI analyst assistant for a pharmaceutical company.
You will be given KPI data. Your job is to explain it in a natural, conversational way.
Follow these rules:
- Write in plain English like you are explaining to a colleague
- Always include Description and Calculation in your answer
- Only include Business Logic section if Additional Business Logic data is present in the KPI data
- If Business Logic is present format each channel as a bullet point
- Do not copy paste raw data - summarise it naturally
- Do not add any information that is not in the KPI data
- Keep it concise and clear
- Do not use technical jargon

Use this structure:
[One sentence explaining what this KPI measures]

**How it is calculated:**
[One clear sentence summarising the calculation]

**Business Logic:** (only include this section if Additional Business Logic exists in the data)
- [Channel 1]
- [Channel 2]
- [Channel 3]"""

    elif intent == "comparison":
        system_prompt = """You are a friendly KPI analyst assistant for a pharmaceutical company.
Compare the KPIs using ONLY the data provided.
Write in plain English like explaining to a colleague.
For each KPI explain what it measures and how it differs from the others.
Do not add any information not in the data."""

    else:
        system_prompt = """You are a friendly KPI analyst assistant for a pharmaceutical company.
Answer the question using ONLY the KPI data provided.
Write in plain English like explaining to a colleague.
If the answer is not in the data say: I don't have that information in the KPI library.
Do not make up any information."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"KPI Data:\n{context}\n\nUser Question: {user_query}"}
            ],
            max_tokens=1024,
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ AI response unavailable. Error: {str(e)}"

def process_query(query, is_voice=False):
    intent = detect_intent(query)
    if intent == "single":
        matched_title = find_match(query)
        if not matched_title:
            intent = "general"
        else:
            context = get_kpi_context(matched_title)
            summary = ask_llm(query, context, intent)
            row = df[df["Metric title"] == matched_title].iloc[0]
            return {
                "role": "assistant",
                "content": "single",
                "matched_title": matched_title,
                "row": row.to_dict(),
                "summary": summary,
                "is_voice": is_voice
            }
    if intent == "comparison":
        matches = find_multiple_matches(query, top_n=3)
        if not matches:
            intent = "general"
        else:
            context = ""
            for title in matches:
                context += f"\n{get_kpi_context(title)}\n"
            summary = ask_llm(query, context, intent)
            return {
                "role": "assistant",
                "content": "comparison",
                "summary": summary,
                "is_voice": is_voice
            }
    context = build_full_context()
    summary = ask_llm(query, context, "general")
    return {
        "role": "assistant",
        "content": "general",
        "summary": summary,
        "is_voice": is_voice
    }

# ---------- SUGGESTIONS ----------
st.markdown("#### 💡 Suggested Searches")
suggestions = [
    "Total KM Communications",
    "Unique HCP Communicated",
    "HCP Engaged",
    "HCP Consumed",
    "HCPs Communicated",
    "HCPs Engaged",
]
cols = st.columns(len(suggestions))
for i, label in enumerate(suggestions):
    with cols[i]:
        if st.button(label, key=f"chip_{i}", use_container_width=True):
            st.session_state.last_voice_index = -1
            st.session_state.messages.append({
                "role": "user",
                "content": label
            })
            with st.spinner("Thinking..."):
                response = process_query(label, is_voice=False)
            st.session_state.messages.append(response)
            st.rerun()

st.divider()

# ---------- CHAT HISTORY ----------
for i, message in enumerate(st.session_state.messages):
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["content"])

    elif message["role"] == "assistant":
        is_last = i == len(st.session_state.messages) - 1
        with st.chat_message("assistant"):
            if message["content"] == "single":
                st.markdown(f"### 📊 {message['matched_title']}")
                st.divider()
                st.markdown(message["summary"])
                if message.get("is_voice") and is_last and i == st.session_state.last_voice_index:
                    try:
                        audio_html = text_to_speech(message["summary"])
                        st.markdown(audio_html, unsafe_allow_html=True)
                    except Exception as e:
                        st.warning(f"Audio unavailable: {str(e)}")
                st.divider()
                with st.expander("📋 View full KPI details"):
                    row = message["row"]
                    exclude = {"ID", "Metric title"}
                    wide_fields = {
                        "Definition",
                        "Description",
                        "Metric description",
                        "Metric Calculation",
                        "Calculation",
                        "Formula",
                        "Notes"
                    }
                    for col, val in row.items():
                        if col in exclude:
                            continue
                        if pd.isna(val) or not str(val).strip():
                            continue
                        if col in wide_fields:
                            st.markdown(f"**{col}**")
                            st.info(str(val))

            elif message["content"] in ("comparison", "general"):
                st.markdown(message["summary"])
                if message.get("is_voice") and is_last and i == st.session_state.last_voice_index:
                    try:
                        audio_html = text_to_speech(message["summary"])
                        st.markdown(audio_html, unsafe_allow_html=True)
                    except Exception as e:
                        st.warning(f"Audio unavailable: {str(e)}")

# ---------- TEXT INPUT ----------
typed = st.chat_input("Ask me anything about NextGen KPIs...")

if typed:
    st.session_state.last_voice_index = -1
    st.session_state.messages.append({
        "role": "user",
        "content": typed
    })
    with st.spinner("Thinking..."):
        response = process_query(typed, is_voice=False)
    st.session_state.messages.append(response)
    st.rerun()
