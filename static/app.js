/**
 * Sakhi Application Frontend
 * Handles UI interactions, audio recording, and API communication.
 */

const UI_CONFIG = {
  "te": {
      "welcome_text": "నమస్కారం అమ్మా, నేను సఖిని. మీకు సహాయం చేస్తాను. ముందుగా చెప్పండి, మీ భర్త చనిపోయారా?",
      "ui_strings": {
          "idle": "నమస్కారం",
          "repeat": "🔁 మళ్ళీ వినండి",
          "didnt_hear": "మీరు చెప్పింది వినపడలేదు.",
          "error": "ఏదో తప్పు జరిగింది."
      },
      "doc_labels": {
          "aadhaar": { emoji: '🪪', label: 'ఆధార్ కార్డు' },
          "deathcert": { emoji: '📜', label: 'మరణ ధృవీకరణ పత్రం' },
          "ration": { emoji: '🍚', label: 'రేషన్ కార్డు' },
          "passbook": { emoji: '🏦', label: 'బ్యాంకు పాస్ బుక్' },
          "photo": { emoji: '📷', label: 'పాస్ పోర్ట్ ఫోటో' }
      }
  },
  "ta": {
      "welcome_text": "வணக்கம் அம்மா, நான் சகி. உங்களுக்கு உதவுகிறேன். முதலில் சொல்லுங்கள், உங்கள் கணவர் இறந்துவிட்டாரா?",
      "ui_strings": {
          "idle": "வணக்கம்",
          "repeat": "🔁 மீண்டும் சொல்லுங்கள்",
          "didnt_hear": "நீங்கள் சொல்வது கேட்கவில்லை.",
          "error": "ஏதோ தவறு நடந்துவிட்டது."
      },
      "doc_labels": {
          "aadhaar": { emoji: '🪪', label: 'ஆதார் அட்டை' },
          "deathcert": { emoji: '📜', label: 'இறப்பு சான்றிதழ்' },
          "ration": { emoji: '🍚', label: 'ரேஷன் அட்டை' },
          "passbook": { emoji: '🏦', label: 'வங்கி புத்தகம்' },
          "photo": { emoji: '📷', label: 'பாஸ்போர்ட் புகைப்படம்' }
      }
  }
};

class SakhiApp {
  constructor() {
    this.body = document.body;
    this.micBtn = document.getElementById('mic-btn');
    this.replayBtn = document.getElementById('replay-btn');
    this.resetBtn = document.getElementById('reset-btn');
    this.captionEl = document.getElementById('caption');
    this.docsContainer = document.getElementById('docs-container');
    this.placeBox = document.getElementById('place-box');
    this.langButtonsBox = document.getElementById('lang-buttons');
    this.appTitleEl = document.getElementById('app-title-el');

    this.conversationHistory = [];
    this.currentState = 'idle'; // idle | listening | thinking | speaking
    this.lastSpokenText = '';
    
    this.currentAudio = null;
    this.currentAudioUrl = null;

    this.currentLang = null; // null | 'te' | 'ta'
    this.detectRetries = 0;

    this.mediaStream = null;
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.audioContext = null;
    this.analyser = null;
    this.animationFrameId = null;
    this.maxRecordingTimeout = null;
    this.hasDetectedSpeech = false;
    this.silenceStartTime = null;

    this.recordingStartTime = 0;
    this.ambientNoiseBaseline = 10;
    this.ambientSamples = [];

    this.init();
  }

  init() {
    this.micBtn.addEventListener('click', () => this.handleMicClick());
    this.micBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.handleMicClick();
      }
    });

    this.replayBtn.addEventListener('click', () => this.handleReplayClick());
    this.resetBtn.addEventListener('click', () => this.resetApp());

    document.querySelectorAll('.lang-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const lang = e.currentTarget.getAttribute('data-lang');
        this.lockLanguage(lang);
      });
    });
  }

  /**
   * Updates application state and body class.
   * @param {string} newState 
   */
  setState(newState) {
    this.currentState = newState;
    this.body.className = newState;
    this.micBtn.setAttribute('aria-pressed', newState === 'listening');
  }

  /**
   * Sets the caption text in the aria-live region.
   * @param {string} text 
   */
  setCaption(text) {
    this.captionEl.textContent = text;
  }

  stopCurrentAudio() {
    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
      } catch (e) {}
      this.currentAudio = null;
    }
    if (this.currentAudioUrl) {
      URL.revokeObjectURL(this.currentAudioUrl);
      this.currentAudioUrl = null;
    }
  }

  /**
   * Fetches TTS and plays audio.
   * @param {string} text 
   * @param {Function} [onEndedCallback] 
   * @param {string} [langOverride] 
   */
  async speakText(text, onEndedCallback, langOverride) {
    this.stopCurrentAudio();
    this.setState('speaking');

    try {
      const langToUse = langOverride || this.currentLang || 'te';
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, lang: langToUse })
      });

      if (!res.ok) throw new Error(`TTS network error: ${res.status}`);

      const blob = await res.blob();
      this.currentAudioUrl = URL.createObjectURL(blob);
      const audio = new Audio(this.currentAudioUrl);
      this.currentAudio = audio;

      audio.onended = () => {
        this.currentAudio = null;
        if (this.currentAudioUrl) {
          URL.revokeObjectURL(this.currentAudioUrl);
          this.currentAudioUrl = null;
        }
        if (onEndedCallback) {
          onEndedCallback();
        } else {
          this.setState('idle');
        }
      };

      audio.onerror = () => {
        this.currentAudio = null;
        this.setState('idle');
        if (onEndedCallback) onEndedCallback();
      };

      await audio.play();
    } catch (err) {
      console.error('TTS playback error:', err);
      this.setState('idle');
      if (onEndedCallback) onEndedCallback();
    }
  }

  speakBilingualPrompt(onEndedCallback) {
    this.speakText("తెలుగు కోసం నమస్కారం అనండి.", () => {
      this.speakText("தமிழுக்கு வணக்கம் என்று சொல்லுங்கள்.", () => {
        if (onEndedCallback) onEndedCallback();
      }, "ta");
    }, "te");
  }

  /**
   * Renders the required documents.
   * @param {string[]} docsList 
   */
  renderDocs(docsList) {
    this.docsContainer.innerHTML = '';
    if (!Array.isArray(docsList) || docsList.length === 0 || !this.currentLang) {
      this.docsContainer.classList.add('hidden');
      return;
    }

    const map = UI_CONFIG[this.currentLang].doc_labels;
    let addedCount = 0;
    
    docsList.forEach((docKey) => {
      const key = String(docKey).toLowerCase().trim();
      if (map[key]) {
        addedCount++;
        const card = document.createElement('div');
        card.className = 'doc-card';
        card.innerHTML = `
          <span class="doc-emoji" aria-hidden="true">${map[key].emoji}</span>
          <span class="doc-label">${map[key].label}</span>
        `;
        this.docsContainer.appendChild(card);
      }
    });

    if (addedCount > 0) this.docsContainer.classList.remove('hidden');
    else this.docsContainer.classList.add('hidden');
  }

  /**
   * Renders the location information box.
   * @param {string} placeText 
   */
  renderPlace(placeText) {
    if (placeText && placeText.trim().length > 0) {
      this.placeBox.textContent = placeText.trim();
      this.placeBox.classList.remove('hidden');
    } else {
      this.placeBox.textContent = '';
      this.placeBox.classList.add('hidden');
    }
  }

  /**
   * Locks the app into a specific language.
   * @param {string} lang 
   */
  lockLanguage(lang) {
    this.currentLang = lang;
    document.documentElement.lang = lang; // Accessibility: Update HTML lang
    
    this.langButtonsBox.classList.add('hidden');
    const config = UI_CONFIG[lang];
    this.appTitleEl.textContent = lang === 'te' ? 'సఖి' : 'சகி';
    this.replayBtn.textContent = config.ui_strings.repeat;
    this.setCaption(config.welcome_text);
    this.lastSpokenText = config.welcome_text;
    this.replayBtn.classList.remove('hidden');
    
    this.speakText(config.welcome_text, () => {
        this.startListening();
    });
  }

  resetApp() {
    this.stopCurrentAudio();
    this.stopListening();
    this.currentLang = null;
    document.documentElement.lang = "en";
    this.detectRetries = 0;
    this.conversationHistory = [];
    this.lastSpokenText = '';
    this.setCaption("నమస్కారం / வணக்கம்");
    this.appTitleEl.textContent = "సఖి / சகி";
    this.docsContainer.classList.add('hidden');
    this.placeBox.classList.add('hidden');
    this.replayBtn.classList.add('hidden');
    this.langButtonsBox.classList.add('hidden');
    this.setState('idle');
  }

  async startListening() {
    this.stopCurrentAudio();
    this.setState('listening');
    this.audioChunks = [];
    this.hasDetectedSpeech = false;
    this.silenceStartTime = null;

    this.recordingStartTime = Date.now();
    this.ambientNoiseBaseline = 10;
    this.ambientSamples = [];

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });

      let mimeType = 'audio/webm';
      if (typeof MediaRecorder.isTypeSupported === 'function') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) mimeType = 'audio/webm;codecs=opus';
        else if (MediaRecorder.isTypeSupported('audio/mp4')) mimeType = 'audio/mp4';
        else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) mimeType = 'audio/ogg;codecs=opus';
      }

      this.mediaRecorder = new MediaRecorder(this.mediaStream, { mimeType: mimeType });

      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        this.audioContext = new AudioContextClass();
        if (this.audioContext.state === 'suspended') await this.audioContext.resume();
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.smoothingTimeConstant = 0.4;
        source.connect(this.analyser);

        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        const ring1 = document.querySelector('.ring-1');
        const ring2 = document.querySelector('.ring-2');

        const analyzeAudio = () => {
          if (this.currentState !== 'listening') return;
          this.analyser.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < bufferLength; i++) sum += dataArray[i];
          const averageVolume = sum / bufferLength;
          const elapsedMs = Date.now() - this.recordingStartTime;

          if (elapsedMs < 400) {
            this.ambientSamples.push(averageVolume);
            if (this.ambientSamples.length > 3) {
              const ambSum = this.ambientSamples.reduce((a, b) => a + b, 0);
              this.ambientNoiseBaseline = Math.max(8, ambSum / this.ambientSamples.length);
            }
          } else {
            const speechTrigger = Math.max(14, this.ambientNoiseBaseline + 6);
            const silenceTrigger = Math.max(10, this.ambientNoiseBaseline + 2);

            if (ring1 && ring2) {
              const voiceScale = Math.min(1.22, 1 + (averageVolume / 180));
              ring1.style.transform = `scale(${voiceScale})`;
            }

            if (averageVolume > speechTrigger) {
              this.hasDetectedSpeech = true;
              this.silenceStartTime = null;
            } else if (this.hasDetectedSpeech && averageVolume < silenceTrigger) {
              if (elapsedMs > 1200) {
                const now = Date.now();
                if (!this.silenceStartTime) this.silenceStartTime = now;
                else if (now - this.silenceStartTime > 1400) {
                  this.stopListening();
                  return;
                }
              }
            } else if (this.hasDetectedSpeech && averageVolume >= silenceTrigger) {
              this.silenceStartTime = null;
            }
          }
          this.animationFrameId = requestAnimationFrame(analyzeAudio);
        };
        
        this.animationFrameId = requestAnimationFrame(analyzeAudio);
      }

      this.maxRecordingTimeout = setTimeout(() => {
        if (this.currentState === 'listening') this.stopListening();
      }, 15000);

      this.mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) this.audioChunks.push(e.data);
      };

      this.mediaRecorder.onstop = async () => {
        this.cleanupAudioNodes();
        const audioBlob = new Blob(this.audioChunks, { type: mimeType });
        await this.processAudioRecording(audioBlob);
      };

      this.mediaRecorder.start(200);
    } catch (err) {
      console.error('Mic access error:', err);
      this.cleanupAudioNodes();
      const errText = this.currentLang ? UI_CONFIG[this.currentLang].ui_strings.error : "Error";
      this.setCaption(errText);
      this.speakText(errText);
    }
  }

  cleanupAudioNodes() {
    if (this.animationFrameId) { 
        cancelAnimationFrame(this.animationFrameId); 
        this.animationFrameId = null; 
    }
    if (this.maxRecordingTimeout) { 
        clearTimeout(this.maxRecordingTimeout); 
        this.maxRecordingTimeout = null; 
    }
    if (this.audioContext) { 
        try { this.audioContext.close(); } catch (e) {} 
        this.audioContext = null; 
        this.analyser = null; 
    }
    if (this.mediaStream) { 
        this.mediaStream.getTracks().forEach(track => track.stop()); 
        this.mediaStream = null; 
    }
  }

  stopListening() {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
        this.mediaRecorder.stop();
    }
  }

  /**
   * Processes the recorded audio blob.
   * @param {Blob} audioBlob 
   */
  async processAudioRecording(audioBlob) {
    this.setState('thinking');

    try {
      const formData = new FormData();
      const fileExtension = audioBlob.type.includes('mp4') ? 'm4a' : 'webm';
      formData.append('audio', audioBlob, 'speech.' + fileExtension);

      if (!this.currentLang) {
        const detectRes = await fetch('/api/detect', { method: 'POST', body: formData });
        if (!detectRes.ok) throw new Error('Detect API error');
        const detectData = await detectRes.json();
        
        if (detectData.lang) {
          this.lockLanguage(detectData.lang);
          return;
        } else {
          this.detectRetries++;
          if (this.detectRetries <= 2) {
              this.setCaption("నమస్కారం / வணக்கம்");
              this.speakBilingualPrompt(() => {
                  this.startListening();
              });
              this.langButtonsBox.classList.remove('hidden');
          } else {
              this.setCaption("నమస్కారం / வணக்கம்");
              this.langButtonsBox.classList.remove('hidden');
              this.setState('idle');
          }
          return;
        }
      }

      formData.append('lang', this.currentLang);
      const sttRes = await fetch('/api/stt', { method: 'POST', body: formData });

      if (!sttRes.ok) throw new Error(`STT error: ${sttRes.status}`);
      const sttData = await sttRes.json();
      const userTranscript = (sttData.text || '').trim();

      const strings = UI_CONFIG[this.currentLang].ui_strings;

      if (!userTranscript) {
        this.setCaption(strings.didnt_hear);
        this.lastSpokenText = strings.didnt_hear;
        this.replayBtn.classList.remove('hidden');
        this.speakText(strings.didnt_hear);
        return;
      }

      this.conversationHistory.push({ role: 'user', content: userTranscript });

      const chatRes = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: this.conversationHistory, lang: this.currentLang })
      });

      if (!chatRes.ok) throw new Error(`Chat error: ${chatRes.status}`);

      const chatData = await chatRes.json();
      const reply = (chatData.reply || '').trim();
      const docs = chatData.docs || [];
      const place = (chatData.place || '').trim();

      this.setCaption(reply);
      this.renderDocs(docs);
      this.renderPlace(place);

      this.conversationHistory.push({ role: 'assistant', content: reply });

      let textToSpeak = reply;
      if (place) textToSpeak += ' ' + place;

      this.lastSpokenText = textToSpeak;
      this.replayBtn.classList.remove('hidden');

      this.speakText(textToSpeak);
    } catch (err) {
      console.error('Processing error:', err);
      const errStr = this.currentLang ? UI_CONFIG[this.currentLang].ui_strings.error : "Error";
      this.setCaption(errStr);
      this.lastSpokenText = errStr;
      this.replayBtn.classList.remove('hidden');
      this.speakText(errStr);
    }
  }

  handleMicClick() {
    if (this.currentState === 'thinking') return;
    if (this.currentState === 'listening') { this.stopListening(); return; }
    if (this.currentState === 'speaking') { this.stopCurrentAudio(); this.startListening(); return; }

    if (!this.currentLang && this.detectRetries === 0) {
      this.speakBilingualPrompt(() => {
        this.startListening();
      });
      this.detectRetries = 1;
    } else {
      this.startListening();
    }
  }

  handleReplayClick() {
    if (this.currentState === 'thinking') return;
    if (this.lastSpokenText) this.speakText(this.lastSpokenText);
  }
}

// Initialize the app without polluting window
document.addEventListener('DOMContentLoaded', () => {
  new SakhiApp();
});
