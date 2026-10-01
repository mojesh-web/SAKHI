# Sakhi (సఖి) - Voice-First Telugu Widow Pension Assistant

> **A voice-first web application designed for first-time rural women with zero digital literacy, no English knowledge, and no tech background to independently learn about and apply for government widow pension schemes in spoken Telugu.**

---

## 🚀 3-Step Quickstart

### 1. Install Dependencies
Ensure you have Python 3.10+ installed:
```bash
pip install -r requirements.txt
```

### 2. Configure Your Groq API Key
Copy `.env.example` to `.env` (or set environment variables):
```bash
cp .env.example .env
```
Open `.env` and set your Groq API key(s):
```env
# Single key:
GROQ_API_KEY=gsk_your_groq_api_key_here

# Or multiple comma-separated keys for automatic rate-limit (429/401/403) rotation:
GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3
```

### 3. Run the Server
```bash
python app.py
```
Open [http://localhost:5000](http://localhost:5000) in your web browser.

---

## 📱 Mobile Testing & Microphone Access (HTTPS Tip)
Mobile browsers (Chrome / Safari / Firefox on Android & iOS) require a secure context (**HTTPS** or `localhost`) to grant microphone access (`navigator.mediaDevices.getUserMedia`).

To test on your mobile phone:
1. Run `ngrok http 5000` or `localtunnel --port 5000`.
2. Open the generated HTTPS URL on your phone:
   ```bash
   ngrok http 5000
   ```
3. Tap the big marigold mic button. Grant microphone permission when prompted.

---

## 🎤 Demo Script & Tips for Evaluators / Judges

Sakhi has zero English, no forms, no login, and no menus. All interaction happens via one large central button and clear spoken Telugu.

| Turn | Persona / Spoken Input | Expected Sakhi Response | Screen Changes |
| :--- | :--- | :--- | :--- |
| **0. Initial Tap** | Tap the marigold circular mic button. | Sakhi speaks: *"నమస్కారం అమ్మా, నేను సఖిని. మీకు సహాయం చేస్తాను. ముందు చెప్పండి, మీరు ఆంధ్రప్రదేశ్లో ఉంటారా, తెలంగాణలో ఉంటారా?"* | Title + Caption appears. Kolam rings pulse in white while speaking, then turn rose for recording. |
| **1. State** | *"నేను తెలంగాణలో ఉంటానమ్మా"* (I live in Telangana) | Sakhi asks: *"మీ భర్త గారు చనిపోయారా అమ్మా?"* (Did your husband pass away?) | Audio speaks the question. |
| **2. Marital Status** | *"అవునమ్మా, నా భర్త చనిపోయారు"* (Yes, my husband passed away) | Sakhi asks: *"మీ దగ్గర రేషన్ కార్డు మరియు బ్యాంకు ఖాతా ఉన్నాయా అమ్మా?"* (Do you have a ration card and bank account?) | Audio speaks the question. |
| **3. Documents** | *"అన్నీ ఉన్నాయమ్మా"* (I have all of them) | Sakhi confirms eligibility for **తెలంగాణ ఆసరా వితంతు పెన్షన్** (~₹2,016/నెల) and tells her where to go. | 5 Document cards appear (🪪 ఆధార్, 📜 భర్త మరణ పత్రం, 🍚 రేషన్ కార్డు, 🏦 బ్యాంకు పుస్తకం, 📷 ఫోటో) + Gold office box (Mee Seva / MPDO). |
| **Replay** | Tap `🔁 మళ్ళీ చెప్పు` | Replays the last spoken answer without re-triggering the LLM. | Audio plays smoothly. |

### Edge Cases Handled:
- **Husband is alive**: Kindly explains she cannot receive widow pension, and gently advises asking at the Secretariat/MPDO for other schemes (e.g., Old Age, Disability, Single Woman).
- **No death certificate**: Guides her on how to obtain one first from the Panchayat/Municipality/Sachivalayam.
- **Unclear / Silence**: Speaks *"అమ్మా, నాకు వినిపించలేదు. మళ్ళీ చెప్పండి."* and allows re-tapping.
- **Safety**: Never asks for Aadhaar number, OTP, bank account numbers, or money; warns that application is 100% free.

---

## 🛠️ Architecture & Tech Stack

- **Backend**: Single-file Python Flask (`app.py`), zero heavy frameworks, zero database, zero auth.
- **Speech-to-Text (STT)**: Groq REST API (`POST /audio/transcriptions`) with `whisper-large-v3`, `language="te"`, `temperature=0`.
- **Reasoning**: Groq REST API (`POST /chat/completions`) with `llama-3.3-70b-versatile`, `response_format={"type": "json_object"}`.
- **Text-to-Speech (TTS)**: `gTTS` streaming pure Telugu audio (`audio/mpeg`) directly from backend memory.
- **API Key Failover**: Automated round-robin rotation across `GROQ_API_KEYS` on HTTP 401, 403, and 429.
- **Frontend**: Vanilla HTML/CSS/JS (`index.html`) with Web Audio API (`AnalyserNode`) for 0.75s silence detection.

---

## 🌐 How to Swap In Another Language or Scheme

Sakhi is designed for modular adaptation to other Indian regional languages (e.g., Hindi, Tamil, Kannada, Marathi) or other welfare schemes (e.g., Rythu Bharosa, Kalyana Lakshmi, Old Age Pension):

1. **Update the Knowledge Base (`scheme_info.txt`)**:
   - Replace the pension facts with details for the target state/scheme (eligibility criteria, monthly benefit, required documents, application office).
2. **Update the System Prompt (`app.py` -> `get_system_prompt()`)**:
   - Change the persona language and cultural honorifics (e.g., "Reply ONLY in simple spoken Hindi, warm and respectful using 'माताजी'").
   - Update the expected doc tokens and scheme flow.
3. **Change Audio Language Codes**:
   - In `app.py`:
     - In `/api/stt`: change `language: "te"` to your ISO language code (e.g. `"hi"`, `"ta"`, `"kn"`).
     - In `/api/tts`: change `gTTS(text=text, lang="te")` to `lang="hi"`, etc.
   - In `index.html`:
     - Update UI labels, document emoji mappings, and greeting text to the new language.

---

## 📞 Phase 2: Toll-Free IVR Phone Hotline (No Smartphone Required)

Many rural women in the target demographic do not own smartphones or computers. 

In Phase 2, the exact same backend (`app.py`) can be connected directly to a toll-free 1800 telephone number using telephony webhooks (**Twilio / Exotel / Plivo**):
1. **Inbound Call**: A woman calls the toll-free number from any basic feature phone (Nokia, JioPhone, landline).
2. **Voice Streaming**: Telephony provider streams user audio to `POST /api/stt`.
3. **Reasoning & Voice Output**: Flask runs `/api/chat` and returns synthesized speech via `/api/tts` into the phone call.
4. **Automated Follow-Up SMS / Voice Broadcast**: After the call, an automated SMS or outbound reminder call in Telugu sends the checklist of required documents and the nearest office address to her family.
