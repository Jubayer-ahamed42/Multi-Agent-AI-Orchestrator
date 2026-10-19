import os
import io
import base64
import hashlib
from datetime import datetime
import streamlit as st
from config import SUPPORTED_MODELS, get_active_model, get_api_key_for_model
from database.memory import MemoryManager
from agents.orchestrator import MasterOrchestrator
from tools.audio_tools import transcribe_audio_to_text
from tools.tts_tools import text_to_speech_bengali

# Page configuration - ChatGPT Clean Full-Width Aesthetic
st.set_page_config(
    page_title="SMART AI ASSISTANT",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)


# High-End ChatGPT CSS Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"], .stMarkdown, .stText {
        font-family: 'Hind Siliguri', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Remove default Streamlit padding */
    .block-container {
        max-width: 860px;
        padding-top: 1rem;
        padding-bottom: 6rem;
        margin: 0 auto;
    }

    /* Top Navigation Pill Container */
    .top-nav-wrapper {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 4px 0 16px 0;
        margin-bottom: 12px;
        border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    }

    /* Center Segmented Pill Controller */
    div[data-testid="stRadio"] > div {
        background-color: #f1f3f5;
        border-radius: 9999px;
        padding: 3px 5px;
        display: inline-flex;
        border: 1px solid #e2e8f0;
        box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.04);
        margin: 0 auto;
    }

    div[data-testid="stRadio"] label {
        border-radius: 9999px !important;
        padding: 6px 20px !important;
        margin: 0 2px !important;
        font-weight: 600 !important;
        cursor: pointer !important;
        font-size: 0.92rem !important;
        transition: all 0.2s ease !important;
    }

    /* Top Badges */
    .plan-badge {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 9999px;
        padding: 5px 14px;
        font-size: 0.82rem;
        font-weight: 600;
        color: #475569;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    /* Centered Home State */
    .home-hero {
        text-align: center;
        margin-top: 5rem;
        margin-bottom: 2.5rem;
    }

    .home-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1e293b;
        letter-spacing: -0.02em;
        margin-bottom: 8px;
    }

    .home-subtitle {
        font-size: 1.05rem;
        color: #64748b;
        font-weight: 400;
    }

    /* ChatGPT Suggestion Action Rows */
    .action-pill {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 12px 18px;
        color: #334155;
        font-size: 0.95rem;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 10px;
        transition: all 0.2s ease;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }

    .action-pill:hover {
        border-color: #cbd5e1;
        background: #f8fafc;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.06);
    }

    /* Live GUI Agent Activity Box */
    .gui-activity-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 18px 22px;
        margin: 16px 0 20px 0;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.02);
    }

    .gui-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
        padding-bottom: 10px;
        border-bottom: 1px solid #f1f5f9;
    }

    .gui-title {
        font-size: 1rem;
        font-weight: 700;
        color: #0f172a;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .gui-steps-container {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
        margin-bottom: 14px;
    }

    .gui-step {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 10px 8px;
        text-align: center;
        font-size: 0.78rem;
        font-weight: 600;
        color: #64748b;
        transition: all 0.3s ease;
    }

    .gui-step.active {
        background: #eff6ff;
        border-color: #60a5fa;
        color: #1d4ed8;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }

    .gui-step.completed {
        background: #f0fdf4;
        border-color: #86efac;
        color: #15803d;
    }

    /* Live terminal box inside GUI activity */
    .gui-terminal {
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 12px;
        padding: 12px 16px;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 0.84rem;
        max-height: 160px;
        overflow-y: auto;
        line-height: 1.5;
        border: 1px solid #1e293b;
    }

    /* Audio Replay In-Bubble */
    .audio-player-wrapper {
        margin-top: 12px;
        padding: 10px 14px;
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 12px;
    }

    .audio-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #166534;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* Sidebar User Profile */
    .user-profile-badge {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        border-radius: 12px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        margin-top: 16px;
    }

    .user-avatar-circle {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: #3b82f6;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.95rem;
    }

    /* Floating Capsule Voice / Input area */
    .input-capsule-container {
        position: relative;
        background: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 26px;
        padding: 8px 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        margin-top: 16px;
    }

    /* Dark Mode Adaptations */
    @media (prefers-color-scheme: dark) {
        .home-title {
            color: #f8fafc;
        }
        .home-subtitle {
            color: #94a3b8;
        }
        div[data-testid="stRadio"] > div {
            background-color: #1e293b;
            border-color: #334155;
        }
        .plan-badge {
            background: #1e293b;
            border-color: #334155;
            color: #cbd5e1;
        }
        .action-pill {
            background: #1e293b;
            border-color: #334155;
            color: #e2e8f0;
        }
        .action-pill:hover {
            background: #334155;
        }
        .gui-activity-card {
            background: #1e293b;
            border-color: #334155;
        }
        .gui-title {
            color: #f8fafc;
        }
        .gui-header {
            border-bottom-color: #334155;
        }
        .gui-step {
            background: #0f172a;
            border-color: #334155;
            color: #94a3b8;
        }
        .audio-player-wrapper {
            background: #064e3b;
            border-color: #047857;
        }
        .audio-title {
            color: #a7f3d0;
        }
        .user-profile-badge {
            background: #1e293b;
            border-color: #334155;
            color: #f8fafc;
        }
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# State Initialization
# -------------------------------------------------------------
if "memory" not in st.session_state:
    st.session_state.memory = MemoryManager()

if "session_id" not in st.session_state:
    sessions = st.session_state.memory.list_sessions()
    if sessions:
        st.session_state.session_id = sessions[0]["id"]
    else:
        st.session_state.session_id = st.session_state.memory.create_session("New Chat")

if "processed_audio_hashes" not in st.session_state:
    st.session_state.processed_audio_hashes = set()

if "current_mode" not in st.session_state:
    st.session_state.current_mode = "Chat"

if "active_activity" not in st.session_state:
    st.session_state.active_activity = None

# -------------------------------------------------------------
# Sidebar: ChatGPT Style History & Profile
# -------------------------------------------------------------
with st.sidebar:
    # Top Brand + New Chat button
    col_logo, col_btn = st.columns([1, 2])
    with col_logo:
        st.markdown("### 🧠 SMART AI")
    with col_btn:
        if st.button("➕ নতুন চ্যাট", use_container_width=True):

            new_id = st.session_state.memory.create_session(f"চ্যাট {len(st.session_state.memory.list_sessions()) + 1}")
            st.session_state.session_id = new_id
            st.rerun()

    st.markdown("---")
    st.markdown("##### 💬 পূর্ববর্তী কথোপকথন (History)")

    sessions = st.session_state.memory.list_sessions()
    if sessions:
        for s in sessions[:15]:
            is_active = s["id"] == st.session_state.session_id
            btn_label = f"{'🟢 ' if is_active else '💬 '}{s['title'][:24]}"
            if st.button(btn_label, key=f"sess_{s['id']}", use_container_width=True):
                if s["id"] != st.session_state.session_id:
                    st.session_state.session_id = s["id"]
                    st.rerun()

    st.markdown("---")
    with st.expander("⚙️ সেটিংস ও নির্দেশিকা"):
        provider = st.selectbox("মডেল প্রোভাইডার", list(SUPPORTED_MODELS.keys()), index=0)
        models = SUPPORTED_MODELS[provider]
        selected_model = st.selectbox("সক্রিয় মডেল", models, index=0)
        os.environ["ACTIVE_MODEL"] = selected_model

        api_key_var = "GEMINI_API_KEY" if "Gemini" in provider else ("OPENAI_API_KEY" if "OpenAI" in provider else "ANTHROPIC_API_KEY")
        current_key = os.getenv(api_key_var, "")
        user_key = st.text_input(f"{provider} Key", value=current_key, type="password")
        if user_key and user_key.strip() != current_key:
            os.environ[api_key_var] = user_key.strip()
            st.success("Key আপডেট হয়েছে!")

        saved_rules = st.session_state.memory.get_preference("assistant_rules", "")
        new_rules = st.text_area("এজেন্টকে দেওয়া নির্দেশিকা:", value=saved_rules, height=100)
        if st.button("নির্দেশিকা সেভ করুন", use_container_width=True):
            st.session_state.memory.set_preference("assistant_rules", new_rules)
            st.success("সেভ হয়েছে!")

    # User Profile (Matching Screenshot JA Circle)
    st.markdown("""
    <div class="user-profile-badge">
        <div class="user-avatar-circle">JA</div>
        <div>
            <div style="font-weight: 600; font-size: 0.9rem;">Jubayer Ahamed</div>
            <div style="font-size: 0.78rem; color: #10b981;">● প্রো একাউন্ট • সার্বক্ষণিক সক্রিয়</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# -------------------------------------------------------------
# Top Navigation Bar: [ Chat ] | [ ✦ Work ] Segmented Pill
# -------------------------------------------------------------
col_top_left, col_top_center, col_top_right = st.columns([1, 2, 1])

with col_top_center:
    mode_selection = st.radio(
        "Mode Selection",
        options=["Chat", "✦ Work"],
        index=0 if st.session_state.current_mode == "Chat" else 1,
        horizontal=True,
        label_visibility="collapsed"
    )
    st.session_state.current_mode = "Chat" if "Chat" in mode_selection else "Work"

with col_top_right:
    active_m = get_active_model().replace("gemini/", "")
    st.markdown(f"<div style='text-align: right;'><span class='plan-badge'>⚡ {active_m}</span></div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# Main Chat Area
# -------------------------------------------------------------
chat_messages = st.session_state.memory.get_messages(st.session_state.session_id)
user_command = None

# If conversation is empty, display ChatGPT Centered Hero View
if not chat_messages:
    st.markdown("""
    <div class="home-hero">
        <h1 class="home-title">What’s on your mind today?</h1>
        <div class="home-subtitle">আসসালামু আলাইকুম স্যার! আমি আপনার SMART AI ASSISTANT। বিনম্র শ্রদ্ধার সাথে আজকে আপনাকে কীভাবে সাহায্য করতে পারি? যেকোনো নির্দেশ বা কথোপকথন শুরু করুন, স্যার।</div>
    </div>

    """, unsafe_allow_html=True)

    # 6 Quick Action Rows (All 5 Specialist Sub-Agents + Chat)
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🏆 Hackathon scout & mentor (হ্যাকাথন সন্ধান ও উইনিং রোডম্যাপ)", use_container_width=True):
            user_command = "চলমান সেরা এআই হ্যাকাথনগুলো খুঁজে বের করো এবং উইনিং প্রজেক্ট আইডিয়া ও ৪৮ ঘণ্টার রোডম্যাপ দাও"
        if st.button("🔍 Search the web (ইন্টারনেটে তথ্য অনুসন্ধান)", use_container_width=True):
            user_command = "২০২৬ সালের শীর্ষ ৩টি এআই ট্রেন্ড নিয়ে গভীর তথ্য অনুসন্ধান ও সারসংক্ষেপ দাও"
        if st.button("💻 Write or edit code (পাইথনে কোডিং ও স্যান্ডবক্স টেস্ট)", use_container_width=True):
            user_command = "পাইথনে ফিবোনাচ্চি অ্যালগরিদম লিখে স্যান্ডবক্সে টেস্ট করে নির্ভুল ফলাফল দেখাও"
    with col_b:
        if st.button("🎯 ClientHunter & Business X-Ray (বিজনেস অডিট ও প্রপোজাল)", use_container_width=True):
            user_command = "একটি রিয়েল টার্গেট কোম্পানির ১০-পয়েন্ট বিজনেস এক্স-রে অডিট, প্রাইসিং ও রেডিমেড প্রপোজাল লেটার তৈরি করো"
        if st.button("📊 Analyze data (ডাটা এনালাইসিস ও পরিসংখ্যান টেবিল)", use_container_width=True):
            user_command = "১ থেকে ৫০ পর্যন্ত জোড় সংখ্যার পরিসংখ্যানগত বিশ্লেষণ ও একটি তথ্য টেবিল তৈরি করো"
        if st.button("💬 Ask anything (যেকোনো মুক্ত আলোচনা বা সাধারণ প্রশ্ন)", use_container_width=True):
            user_command = "তুমি কি আমার বাংলা কথা বুঝতে পারো? তোমার সাব-এজেন্টদের কাজ ব্যাখ্যা করো"

else:
    # Render Chat History
    for msg in chat_messages:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(msg["content"])

                # Metadata tag
                meta = msg.get("metadata", {})
                if meta.get("type") == "conversation":
                    st.caption("⚡ সরাসরি চ্যাট মোড (১-২ সেকেন্ডে প্রস্তুত)")
                elif meta.get("iterations"):
                    st.caption(f"✨ ওয়ার্ক মোড • মান যাচাইকৃত • সেলফ-কারেকশন: {meta['iterations']} বার")

                # In-bubble Voice Output Player
                audio_b64 = meta.get("audio_b64")
                if audio_b64:
                    try:
                        audio_data = base64.b64decode(audio_b64)
                        st.markdown("""
                        <div class="audio-player-wrapper">
                            <div class="audio-title">🔊 বাংলা অডিও রিপ্লাই শুনুন:</div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.audio(audio_data, format="audio/mp3")
                    except Exception:
                        pass

                # Download button
                st.download_button(
                    label="📥 রিপোর্ট ডাউনলোড (.md)",
                    data=msg["content"],
                    file_name=f"chat_{msg['id'][:8]}.md",
                    mime="text/markdown",
                    key=f"dl_{msg['id']}"
                )

# -------------------------------------------------------------
# Bottom Input Bar (Floating Capsule with Voice & Text)
# -------------------------------------------------------------
# Voice recorder widget (Integrated with microphone)
with st.container():
    col_mic, col_txt = st.columns([1, 4])
    with col_mic:
        st.markdown("<div style='padding-top: 10px; font-weight: 600; font-size: 0.9rem;'>🎙️ ভয়েস ইনপুট:</div>", unsafe_allow_html=True)
    with col_txt:
        audio_val = st.audio_input("মাইক্রোফোনে বাংলায় কথা বলুন", label_visibility="collapsed")
        if audio_val is not None:
            raw_audio = audio_val.read()
            aud_hash = hashlib.md5(raw_audio).hexdigest()
            if aud_hash not in st.session_state.processed_audio_hashes:
                with st.spinner("🎧 কণ্ঠস্বর বিশ্লেষণ করা হচ্ছে..."):
                    try:
                        spoken_text = transcribe_audio_to_text(raw_audio, mime_type=audio_val.type or "audio/wav")
                        st.session_state.processed_audio_hashes.add(aud_hash)
                        if spoken_text and spoken_text.strip():
                            user_command = spoken_text.strip()
                        else:
                            st.warning("কণ্ঠস্বর পরিষ্কার শোনা যায়নি, পুনরায় বলুন।")
                    except Exception as e:
                        st.error(f"ভয়েস ত্রুটি: {str(e)}")

# Standard Chat Input
text_prompt = st.chat_input("Ask anything... / যেকোনো প্রশ্ন বা কাজের নির্দেশ লিখুন...")
if text_prompt and text_prompt.strip():
    user_command = text_prompt.strip()

# -------------------------------------------------------------
# Execution & Live GUI Activity Progress Box
# -------------------------------------------------------------
if user_command:
    mode_tag = st.session_state.current_mode.lower()  # "chat" or "work"

    # Display user's prompt in chat
    with st.chat_message("user", avatar="👤"):
        st.write(user_command)

    # Graphical User Interface (GUI) Live Activity Box (As requested)
    gui_container = st.empty()
    logs_stream = []

    def update_gui(step_num: int, title: str, log_message: str):
        steps = [
            ("1. পরিকল্পনা", "completed" if step_num > 1 else ("active" if step_num == 1 else "")),
            ("2. স্পেশালিস্ট", "completed" if step_num > 2 else ("active" if step_num == 2 else "")),
            ("3. মান যাচাই", "completed" if step_num > 3 else ("active" if step_num == 3 else "")),
            ("4. অডিও সিন্থেসিস", "completed" if step_num > 4 else ("active" if step_num == 4 else ""))
        ]
        
        logs_stream.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log_message}")
        recent_logs = "<br>".join(logs_stream[-5:])

        gui_html = f"""
        <div class="gui-activity-card">
            <div class="gui-header">
                <div class="gui-title">
                    <span>⚡ লাইভ এজেন্ট অ্যাক্টিভিটি কনসোল</span>
                    <span style="font-size: 0.8rem; font-weight: 500; color: #3b82f6;">({st.session_state.current_mode} মোড)</span>
                </div>
                <div style="font-size: 0.82rem; color: #10b981; font-weight: 600;">● প্রসেসিং চলছে...</div>
            </div>
            <div class="gui-steps-container">
                <div class="gui-step {steps[0][1]}">{steps[0][0]}</div>
                <div class="gui-step {steps[1][1]}">{steps[1][0]}</div>
                <div class="gui-step {steps[2][1]}">{steps[2][0]}</div>
                <div class="gui-step {steps[3][1]}">{steps[3][0]}</div>
            </div>
            <div class="gui-terminal">
                {recent_logs}
            </div>
        </div>
        """
        gui_container.markdown(gui_html, unsafe_allow_html=True)

    # Initialize GUI
    update_gui(1, "পরিকল্পনা", f"ইনপুট গ্রহণ: '{user_command[:45]}...'")

    def handle_progress(event):
        e_type = event.get("type", "")
        e_msg = event.get("message", "")

        if e_type in ["plan", "status"]:
            update_gui(1, "পরিকল্পনা", e_msg)
        elif e_type in ["subagent_start", "subagent_output"]:
            update_gui(2, "স্পেশালিস্ট কর্মী", e_msg)
        elif e_type in ["evaluation_start", "evaluation_pass", "evaluation_fail"]:
            update_gui(3, "কোয়ালিটি যাচাই", e_msg)
        elif e_type in ["synthesis", "voice"]:
            update_gui(4, "ভয়েস সিন্থেসিস", e_msg)
        else:
            update_gui(2, "প্রসেসিং", e_msg)

    orchestrator = MasterOrchestrator(
        memory_manager=st.session_state.memory,
        model=get_active_model()
    )

    try:
        result = orchestrator.process_command(
            session_id=st.session_state.session_id,
            user_command=user_command,
            mode=mode_tag,
            on_progress=handle_progress
        )

        # Mark GUI as complete
        update_gui(5, "সম্পন্ন", "কাজ সফলভাবে সম্পন্ন এবং যাচাইকৃত!")

        # Render Assistant message
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(result["final_report"])

            # In-bubble audio playback
            if result.get("audio_bytes"):
                st.markdown("""
                <div class="audio-player-wrapper">
                    <div class="audio-title">🔊 বাংলা অডিও রিপ্লাই শুনুন:</div>
                </div>
                """, unsafe_allow_html=True)
                st.audio(result["audio_bytes"], format="audio/mp3")

            st.download_button(
                label="📥 সম্পূর্ণ রিপোর্ট ডাউনলোড (.md)",
                data=result["final_report"],
                file_name="assistant_response.md",
                mime="text/markdown",
                key=f"dl_live_{hashlib.md5(user_command.encode()).hexdigest()[:8]}"
            )

            if result.get("sub_agent_results"):
                with st.expander("🔍 সাব-এজেন্টদের কাজের ট্র্যাজেক্টরি ও কোয়ালিটি স্কোর দেখুন"):
                    for sub in result.get("sub_agent_results", []):
                        st.write(f"**টাস্ক:** {sub['task']['task_description']}")
                        st.write(f"**কর্মী:** {sub['task']['agent'].upper()}")
                        st.write(f"**চেষ্টা সংখ্যা:** {sub['attempts']}")
                        st.json(sub.get("eval", {}))
                        st.markdown("---")

    except Exception as e:
        gui_container.error(f"ত্রুটি ঘটেছে: {str(e)}")
