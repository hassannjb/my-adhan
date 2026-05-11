/* Adhan Clock — web frontend
 *
 * Prayer times + scheduling : Adhan.js (client-side, no server needed)
 * Hijri date                : Intl.DateTimeFormat Islamic calendar
 * Location                  : browser Geolocation API → ipapi.co fallback
 * Voice input               : Web Speech API (SpeechRecognition)
 * TTS                       : Web Speech API (SpeechSynthesis)
 * Audio playback            : HTML5 Audio (files served from /audio/)
 * RAG chatbot               : GET /api/chat  (SSE stream from FastAPI backend)
 */

const PRAYER_NAMES = ['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'];

const LANG_SPEECH = {
  English: 'en-US',
  Urdu:    'ur-PK',
  Hindi:   'hi-IN',
  Turkish: 'tr-TR',
  Arabic:  'ar-SA',
};

const PLACEHOLDERS = {
  English: 'e.g. When is Fajr in Toronto tomorrow?',
  Urdu:    'مثلاً: کل فجر کا وقت کیا ہے؟',
  Hindi:   'उदा.: कल फजर का समय क्या है?',
  Turkish: 'Örn.: Yarın İstanbul\'da Fajr vakti ne zaman?',
  Arabic:  'مثال: ما وقت صلاة الفجر في القاهرة غدًا؟',
};

function adhanApp() {
  return {
    // ── clock ────────────────────────────────────────────────────────
    currentTime:   '--:--:--',
    currentDate:   '',
    hijriDate:     '',
    locationInfo:  'Detecting location…',
    countdownText: '',

    // ── prayer times ─────────────────────────────────────────────────
    prayers:       PRAYER_NAMES.map(n => ({ name: n, time: '--:--' })),
    nextPrayerName: '',
    prayerTimesObj: null,
    coordinates:   null,

    // ── adhan audio ──────────────────────────────────────────────────
    adhanTimeout:      null,
    scheduledFor:      null,
    suppressRestore:   null,   // timeout to restore volume after suppress

    // ── settings ─────────────────────────────────────────────────────
    showSettings: false,
    settings: {
      method:    'NorthAmerica',
      fajrAngle: 15.0,
      ishaAngle: 15.0,
      audioFile: 'makkah',
    },

    // ── chat ─────────────────────────────────────────────────────────
    ragReady:         false,
    ragError:         null,
    chatLang:         'English',
    inputPlaceholder: PLACEHOLDERS.English,
    question:         '',
    answer:           '',
    chatLoading:      false,
    recognizing:      false,
    _recognition:     null,

    // ── init ─────────────────────────────────────────────────────────
    init() {
      this.loadSettings();
      this.detectLocation();
      setInterval(() => this.tick(), 1000);
      this.checkRagStatus();
    },

    // ── settings persistence ─────────────────────────────────────────
    loadSettings() {
      const s = localStorage.getItem('adhan_settings');
      if (s) Object.assign(this.settings, JSON.parse(s));
    },
    saveSettings() {
      localStorage.setItem('adhan_settings', JSON.stringify(this.settings));
    },
    recalculate() {
      this.saveSettings();
      if (this.coordinates) this.calcPrayerTimes(this.coordinates.latitude, this.coordinates.longitude);
    },

    // ── location ─────────────────────────────────────────────────────
    async detectLocation() {
      // 1. Try browser Geolocation (most accurate, no API key needed)
      if (navigator.geolocation) {
        try {
          const pos = await new Promise((res, rej) =>
            navigator.geolocation.getCurrentPosition(res, rej, { timeout: 8000 })
          );
          const { latitude, longitude } = pos.coords;
          this.locationInfo = `${latitude.toFixed(2)}°, ${longitude.toFixed(2)}°`;
          this.calcPrayerTimes(latitude, longitude);
          // Try to get city name from reverse geocode (best-effort, no crash if it fails)
          fetch(`https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json`)
            .then(r => r.json())
            .then(d => { this.locationInfo = d.address?.city || d.address?.town || this.locationInfo; })
            .catch(() => {});
          return;
        } catch (_) { /* fall through to IP-based */ }
      }
      // 2. Fallback: IP-based geolocation (same as existing webapp)
      try {
        const cached = localStorage.getItem('adhan_location');
        const loc = cached ? JSON.parse(cached) : await fetch('https://ipapi.co/json/').then(r => r.json());
        if (!cached) localStorage.setItem('adhan_location', JSON.stringify(loc));
        this.locationInfo = `${loc.city}, ${loc.country_name}`;
        this.calcPrayerTimes(loc.latitude, loc.longitude);
      } catch (e) {
        this.locationInfo = 'Location unavailable';
      }
    },

    // ── prayer time calculation (Adhan.js — runs entirely in browser) ─
    calcPrayerTimes(lat, lng) {
      if (typeof adhan === 'undefined') return;
      this.coordinates = new adhan.Coordinates(lat, lng);
      this._refreshTimes(new Date());
    },

    _getParams() {
      const methods = {
        NorthAmerica: adhan.CalculationMethod.NorthAmerica,
        MuslimWorldLeague: adhan.CalculationMethod.MuslimWorldLeague,
        Egyptian: adhan.CalculationMethod.Egyptian,
        Karachi: adhan.CalculationMethod.Karachi,
        UmmAlQura: adhan.CalculationMethod.UmmAlQura,
        Dubai: adhan.CalculationMethod.Dubai,
        Qatar: adhan.CalculationMethod.Qatar,
        Kuwait: adhan.CalculationMethod.Kuwait,
        MoonsightingCommittee: adhan.CalculationMethod.MoonsightingCommittee,
        Singapore: adhan.CalculationMethod.Singapore,
        Tehran: adhan.CalculationMethod.Tehran,
        Turkey: adhan.CalculationMethod.Turkey,
      };
      const params = (methods[this.settings.method] || adhan.CalculationMethod.NorthAmerica)();
      params.fajrAngle = parseFloat(this.settings.fajrAngle);
      params.ishaAngle = parseFloat(this.settings.ishaAngle);
      return params;
    },

    _refreshTimes(date) {
      const pt = new adhan.PrayerTimes(this.coordinates, date, this._getParams());
      this.prayerTimesObj = pt;
      this.prayers = PRAYER_NAMES.map(n => ({
        name: n,
        time: pt[n.toLowerCase()].toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }));
      this._scheduleNextAdhan(new Date());
    },

    // ── 1-second tick ────────────────────────────────────────────────
    tick() {
      const now = new Date();

      // Clock labels
      this.currentTime = now.toLocaleTimeString();
      this.currentDate = now.toLocaleDateString(undefined, {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
      });
      this.hijriDate = new Intl.DateTimeFormat('en-TN-u-ca-islamic', {
        day: 'numeric', month: 'long', year: 'numeric',
      }).format(now);

      if (!this.prayerTimesObj || !this.coordinates) return;

      // Refresh prayer times at midnight
      const pt = this.prayerTimesObj;
      if (pt.date.toDateString() !== now.toDateString()) {
        this._refreshTimes(now);
        return;
      }

      // Next prayer + countdown
      let next = pt.nextPrayer();
      let nextTime = pt.timeForPrayer(next);
      let nextName = '';

      if (next === adhan.Prayer.None) {
        // Past Isha — show Fajr tomorrow
        const tomorrow = new Date(now);
        tomorrow.setDate(tomorrow.getDate() + 1);
        const tomorrowPt = new adhan.PrayerTimes(this.coordinates, tomorrow, this._getParams());
        nextTime = tomorrowPt.fajr;
        nextName = 'Fajr';
      } else {
        nextName = next.charAt(0).toUpperCase() + next.slice(1);
      }

      this.nextPrayerName = nextName;

      const diff = nextTime - now;
      if (diff > 0) {
        const h = Math.floor(diff / 3_600_000);
        const m = Math.floor((diff % 3_600_000) / 60_000);
        const s = Math.floor((diff % 60_000) / 1000);
        this.countdownText = h > 0
          ? `${nextName} in ${h}h ${m}m ${s}s`
          : `${nextName} in ${m}m ${s}s`;
      } else {
        this.countdownText = 'All prayers done for today.';
      }
    },

    // ── adhan scheduling ─────────────────────────────────────────────
    _scheduleNextAdhan(now) {
      if (!this.prayerTimesObj) return;
      clearTimeout(this.adhanTimeout);

      const prayable = ['fajr', 'dhuhr', 'asr', 'maghrib', 'isha'];
      let nearest = null;
      for (const name of prayable) {
        const t = this.prayerTimesObj[name];
        if (t > now && (!nearest || t < nearest.time)) {
          nearest = { name, time: t };
        }
      }
      if (!nearest) return;

      const delay = nearest.time - now;
      this.adhanTimeout = setTimeout(() => {
        this._playPrayerAudio(nearest.name);
        setTimeout(() => this._scheduleNextAdhan(new Date()), 60_000);
      }, delay);
    },

    _playPrayerAudio(prayerName) {
      const id = prayerName === 'fajr' ? 'fajrAudio' : 'makkahAudio';
      document.getElementById(id)?.play().catch(() => {});
    },

    // ── manual adhan controls ─────────────────────────────────────────
    playAdhan() {
      const id = this.settings.audioFile === 'fajr' ? 'fajrAudio' : 'makkahAudio';
      document.getElementById(id)?.play().catch(() => {});
    },

    stopAdhan() {
      ['makkahAudio', 'fajrAudio'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.pause(); el.currentTime = 0; }
      });
      clearTimeout(this.suppressRestore);
    },

    suppressAdhan() {
      // Drop to 5% for the current playback then auto-restore when audio ends
      ['makkahAudio', 'fajrAudio'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.volume = 0.05;
        const restore = () => { el.volume = 1; el.removeEventListener('ended', restore); };
        el.addEventListener('ended', restore);
      });
    },

    // ── RAG status ───────────────────────────────────────────────────
    async checkRagStatus() {
      try {
        const data = await fetch('/api/status').then(r => r.json());
        this.ragReady = data.ready;
        this.ragError = data.error || null;
      } catch (_) {
        this.ragReady = false;
        this.ragError = 'Cannot reach the API server (is uvicorn running?)';
      }
      // Re-check every 30 s so the badge updates if the server restarts
      setTimeout(() => this.checkRagStatus(), 30_000);
    },

    // ── chat ─────────────────────────────────────────────────────────
    updatePlaceholder() {
      this.inputPlaceholder = PLACEHOLDERS[this.chatLang] || PLACEHOLDERS.English;
    },

    async askQuestion() {
      if (!this.question.trim() || this.chatLoading) return;
      if (!this.ragReady) {
        this.answer = `Chat unavailable: ${this.ragError || 'RAG index not loaded. Run: python rag/ingest.py'}`;
        return;
      }
      const q = this.question.trim();
      this.question = '';
      this.answer = '';
      this.chatLoading = true;

      try {
        const url = `/api/chat?q=${encodeURIComponent(q)}&language=${encodeURIComponent(this.chatLang)}`;
        const resp = await fetch(url);
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          this.answer = err.error || 'Server error.';
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });

          // Parse SSE lines; keep last incomplete line in buffer
          const lines = buf.split('\n');
          buf = lines.pop();
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (raw === '[DONE]') break;
            try { this.answer += JSON.parse(raw); } catch (_) {}
          }
        }
      } catch (e) {
        this.answer = `Error: ${e.message}`;
      } finally {
        this.chatLoading = false;
      }
    },

    // ── voice input (Web Speech API) ─────────────────────────────────
    toggleVoice() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) {
        alert('Voice input requires Chrome or Edge.');
        return;
      }

      if (this.recognizing) {
        this._recognition?.stop();
        this.recognizing = false;
        return;
      }

      const r = new SR();
      r.lang = LANG_SPEECH[this.chatLang] || 'en-US';
      r.continuous = false;
      r.interimResults = false;

      r.onresult = (e) => {
        this.question = e.results[0][0].transcript;
        this.recognizing = false;
        this.askQuestion();
      };
      r.onerror = () => { this.recognizing = false; };
      r.onend   = () => { this.recognizing = false; };

      r.start();
      this.recognizing = true;
      this._recognition = r;
    },

    // ── TTS (Web Speech API) ─────────────────────────────────────────
    speakAnswer() {
      if (!this.answer || !window.speechSynthesis) return;
      speechSynthesis.cancel();
      const utt = new SpeechSynthesisUtterance(this.answer);
      utt.lang = LANG_SPEECH[this.chatLang] || 'en-US';
      speechSynthesis.speak(utt);
    },
  };
}
