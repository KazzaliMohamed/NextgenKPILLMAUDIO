# ---------- MIC ----------
st.markdown("---")
st.markdown("🎤 **Speak your question:**")

voice_text = speech_to_text(
    language="en",
    start_prompt="🎤 Click to speak",
    stop_prompt="⏹ Click to stop",
    just_once=True,
    use_container_width=False,
    key="stt"
)

if voice_text:
    if voice_text != st.session_state.get("last_voice_text"):
        st.session_state.last_voice_text = voice_text
        st.success(f"✅ Heard: {voice_text}")
        st.session_state.messages.append({
            "role": "user",
            "content": f"🎤 {voice_text}"
        })
        with st.spinner("Thinking..."):
            response = process_query(voice_text, is_voice=True)
        st.session_state.messages.append(response)
        st.session_state.last_voice_index = len(st.session_state.messages) - 1
        st.rerun()
