/* Adhan Clock — web frontend
 *
 * Prayer times + scheduling : Adhan.js (client-side, no server needed)
 * Hijri date                : Intl.DateTimeFormat Islamic calendar
 * Location                  : browser Geolocation API → ipapi.co fallback
 * Voice input               : Web Speech API (SpeechRecognition)
 * TTS                       : Web Speech API (SpeechSynthesis)
 * Audio playback            : HTML5 Audio (files served from /audio/)
 * Chat assistant            : GET /api/chat  (JSON; curated answers, no LLM).
 *                             Prayer times in chat are calculated here with the
 *                             same _getParams() as the clock, so they always agree.
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
};

const METHOD_LABELS = {
  NorthAmerica: 'North America (ISNA)', MuslimWorldLeague: 'Muslim World League',
  Egyptian: 'Egyptian', Karachi: 'Karachi', UmmAlQura: 'Umm al-Qura',
  Dubai: 'Dubai', Qatar: 'Qatar', Kuwait: 'Kuwait',
  MoonsightingCommittee: 'Moonsighting Committee', Singapore: 'Singapore',
  Tehran: 'Tehran', Turkey: 'Turkey',
};

const STARTER_QUESTIONS = [
  'How many daily prayers are there?',
  'When does Asr start and end?',
  'When is Isha tomorrow?',
  'Fajr in Makkah on 1 Ramadan 1448',
];

// sunnah.com slugs for the collections cited in assistant/faq.md
const HADITH_SLUGS = { 'Bukhari': 'bukhari', 'Muslim': 'muslim', 'Abu Dawud': 'abudawud', 'Tirmidhi': 'tirmidhi' };

// Anonymous id per browser tab for the question log (no IP or user agent is stored).
const SESSION_ID = (() => {
  const make = () => (crypto.randomUUID?.() || (Date.now().toString(36) + Math.random().toString(36).slice(2)));
  try {
    let s = sessionStorage.getItem('adhan_session');
    if (!s) { s = make(); sessionStorage.setItem('adhan_session', s); }
    return s;
  } catch (_) { return make(); }
})();

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// The small markdown subset faq.md uses: paragraphs, - and 1. lists, **bold**.
function mdToHtml(md) {
  const out = [];
  let para = [], list = null;
  const inline = t => t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join(' '))}</p>`); para = []; } };
  const flushList = () => { if (list) { out.push(`<${list.tag}>${list.items.map(i => `<li>${inline(i)}</li>`).join('')}</${list.tag}>`); list = null; } };
  for (const line of escapeHtml(md).split('\n')) {
    const ul = line.match(/^\s*-\s+(.*)$/), ol = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ul || ol) {
      flushPara();
      const tag = ul ? 'ul' : 'ol';
      if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
      list.items.push((ul || ol)[1]);
    } else if (!line.trim()) {
      flushPara(); flushList();
    } else {
      flushList(); para.push(line.trim());
    }
  }
  flushPara(); flushList();
  return out.join('');
}

function sourcesHtml(sources) {
  if (!sources) return '';
  const parts = sources.split(';').map(x => x.trim()).filter(Boolean).map(ref => {
    const m = ref.match(/^(Bukhari|Muslim|Abu Dawud|Tirmidhi) (\d+)$/);
    return m ? `<a href="https://sunnah.com/${HADITH_SLUGS[m[1]]}:${m[2]}" target="_blank" rel="noopener">${escapeHtml(ref)}</a>`
             : escapeHtml(ref);
  });
  return `<div class="msg-sources">Sources: ${parts.join('; ')}</div>`;
}

function chipsHtml(questions) {
  return `<div class="chat-chips">${questions.map(q =>
    `<button type="button" class="chat-chip" data-ask="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join('')}</div>`;
}

function htmlToText(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('.chat-chips, .msg-sources').forEach(el => el.remove());
  doc.querySelectorAll('p, li, div').forEach(el => el.append('\n'));
  return doc.body.textContent.replace(/\n{2,}/g, '\n').trim();
}

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
    extras:        [],      // voluntary prayer windows (Duha, Awwabin, Midnight, Tahajjud)
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
    messages:         [],    // [{role, html, text}]
    chatLoading:      false,
    lastTimes:        null,  // previous times reply, sent back so "and tomorrow?" works
    starterChips:     chipsHtml(STARTER_QUESTIONS),
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
      this._refreshExtras(new Date());
    },

    // Voluntary prayer windows shown under the grid. The day follows the grid
    // (it moves to tomorrow after Isha); the night is the one you're in, so
    // between midnight and Fajr it is still last night.
    _refreshExtras(now) {
      if (!this.coordinates) return;
      const params = this._getParams();
      const at = offsetDays => {
        const d = new Date(now);
        d.setDate(d.getDate() + offsetDays);
        return new adhan.PrayerTimes(this.coordinates, d, params);
      };
      const today = at(0);
      const fmt = t => t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const range = (a, b) => `${fmt(a)} to ${fmt(b)}`;
      const minutes = (t, m) => new Date(t.getTime() + m * 60_000);

      const day = now > today.isha ? at(1) : today;
      const nightStart = now < today.fajr ? at(-1) : today;
      const night = new adhan.SunnahTimes(nightStart);
      const nightEnd = now < today.fajr ? today.fajr : at(1).fajr;

      this.extras = [
        { name: 'Duha', time: range(minutes(day.sunrise, 20), minutes(day.dhuhr, -10)),
          note: 'From about 20 minutes after sunrise until shortly before Dhuhr (zawal). Best once the day has become hot (Muslim 748).' },
        { name: 'Awwabin', time: range(day.maghrib, day.isha),
          note: "Voluntary prayer between Maghrib and Isha. In Muslim 748 the Prophet also called Duha \"the prayer of the awwabin\"." },
        { name: 'Midnight', time: fmt(night.middleOfTheNight),
          note: "Halfway between Maghrib and Fajr. Isha's preferred time ends here (Muslim 612)." },
        { name: 'Tahajjud', time: range(night.lastThirdOfTheNight, nightEnd),
          note: 'The last third of the night, the best time for night prayer (Bukhari 1145). Night prayer can be offered any time after Isha.' },
      ];
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
      if (now.getSeconds() === 0) this._refreshExtras(now);

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
        // Past Isha — switch grid to tomorrow and count down to Fajr
        const tomorrow = new Date(now);
        tomorrow.setDate(tomorrow.getDate() + 1);
        const tomorrowPt = new adhan.PrayerTimes(this.coordinates, tomorrow, this._getParams());
        nextTime = tomorrowPt.fajr;
        nextName = 'Fajr';
        this.prayers = PRAYER_NAMES.map(n => ({
          name: n,
          time: tomorrowPt[n.toLowerCase()].toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }));
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
      this.inputPlaceholder = PLACEHOLDERS.English;
    },

    _pushAssistant(html) {
      this.messages.push({ role: 'assistant', html, text: htmlToText(html) });
    },

    onChatClick(e) {
      const chip = e.target.closest('[data-ask]');
      if (!chip || this.chatLoading) return;
      this.question = chip.dataset.ask;
      this.askQuestion();
    },

    async askQuestion() {
      if (!this.question.trim() || this.chatLoading) return;
      const q = this.question.trim();
      this.question = '';
      this.messages.push({ role: 'user', html: escapeHtml(q), text: q });
      if (!this.ragReady) {
        this._pushAssistant(`<p>Chat unavailable: ${escapeHtml(this.ragError || 'the assistant is not loaded.')}</p>`);
        return;
      }
      this.chatLoading = true;
      try {
        const params = new URLSearchParams({ q });
        if (this.lastTimes) params.set('prev', JSON.stringify(this.lastTimes));
        const resp = await fetch(`/api/chat?${params}`, { headers: { 'X-Session': SESSION_ID } });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          this._pushAssistant(`<p>${escapeHtml(data.error || 'Server error.')}</p>`);
          return;
        }
        this._pushAssistant(this._renderReply(data));
      } catch (e) {
        this._pushAssistant(`<p>Error: ${escapeHtml(e.message)}</p>`);
      } finally {
        this.chatLoading = false;
        this.$nextTick(() => {
          const box = document.querySelector('.answer-box');
          if (box) box.scrollTop = box.scrollHeight;
        });
      }
    },

    _renderReply(r) {
      if (r.kind === 'times') {
        this.lastTimes = { targets: r.targets, date: r.date, date_label: r.date_label, place: r.place };
        return this._timesHtml(r);
      }
      if (r.kind === 'faq') {
        const times = r.times ? `<div class="msg-times">${this._timesHtml(r.times)}</div>` : '';
        return `<p><strong>${escapeHtml(r.title)}</strong></p>${mdToHtml(r.answer)}${times}${sourcesHtml(r.sources)}`;
      }
      if (r.kind === 'fallback') {
        return `<p>${escapeHtml(r.text)}</p>${chipsHtml(r.suggestions || [])}`;
      }
      return `<p>${escapeHtml(r.text || 'Sorry, I could not answer that.')}</p>`;
    },

    // Prayer times for a chat reply, calculated exactly like the clock.
    _timesHtml(spec) {
      if (typeof adhan === 'undefined') return '<p>Prayer time library failed to load.</p>';
      const coords = spec.place ? new adhan.Coordinates(spec.place.lat, spec.place.lng) : this.coordinates;
      if (!coords) {
        return '<p>I don\'t know your location yet. Allow location access, or ask with a city, for example "Asr in Toronto".</p>';
      }
      const tz = spec.place ? spec.place.tz : Intl.DateTimeFormat().resolvedOptions().timeZone;
      const [y, m, d] = spec.date.split('-').map(Number);
      const params = this._getParams();
      // adhan.js reads only the calendar date from these
      const pt = new adhan.PrayerTimes(coords, new Date(y, m - 1, d), params);
      const nextPt = new adhan.PrayerTimes(coords, new Date(y, m - 1, d + 1), params);
      const night = new adhan.SunnahTimes(pt);
      const fmt = t => t.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: tz });

      const isToday = !spec.place && spec.date === new Date().toLocaleDateString('en-CA');
      const rel = t => {
        if (!isToday) return '';
        const mins = Math.round((t - new Date()) / 60000);
        const span = Math.abs(mins) >= 60 ? `${Math.floor(Math.abs(mins) / 60)} h ${Math.abs(mins) % 60} min` : `${Math.abs(mins)} min`;
        return mins >= 0 ? ` <span class="msg-rel">(in ${span})</span>` : ` <span class="msg-rel">(${span} ago)</span>`;
      };
      const rows = {
        fajr:       () => `<strong>Fajr</strong>: ${fmt(pt.fajr)}${rel(pt.fajr)}, until sunrise at ${fmt(pt.sunrise)}`,
        sunrise:    () => `<strong>Sunrise</strong>: ${fmt(pt.sunrise)}${rel(pt.sunrise)}`,
        dhuhr:      () => `<strong>Dhuhr</strong>: ${fmt(pt.dhuhr)}${rel(pt.dhuhr)}, until Asr at ${fmt(pt.asr)}`,
        asr:        () => `<strong>Asr</strong>: ${fmt(pt.asr)}${rel(pt.asr)}, until Maghrib (sunset) at ${fmt(pt.maghrib)}`,
        maghrib:    () => `<strong>Maghrib</strong>: ${fmt(pt.maghrib)}${rel(pt.maghrib)}, until Isha at ${fmt(pt.isha)}`,
        isha:       () => `<strong>Isha</strong>: ${fmt(pt.isha)}${rel(pt.isha)}, until Fajr at ${fmt(nextPt.fajr)} the next morning`,
        midnight:   () => `<strong>Middle of the night</strong>: ${fmt(night.middleOfTheNight)}${rel(night.middleOfTheNight)}`,
        last_third: () => `<strong>Last third of the night</strong>: from ${fmt(night.lastThirdOfTheNight)}${rel(night.lastThirdOfTheNight)} until Fajr at ${fmt(nextPt.fajr)}`,
      };
      const all = ['fajr', 'sunrise', 'dhuhr', 'asr', 'maghrib', 'isha'];
      const targets = spec.targets.includes('all') ? all : spec.targets.filter(t => rows[t]);
      const lines = targets.map(t => `<li>${rows[t]()}</li>`).join('');

      const dateText = new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
      let label = (spec.date_label || '').trim();
      // Midnight and the last third belong to the coming night.
      if (label === 'today' && spec.targets.every(t => t === 'midnight' || t === 'last_third')) label = 'tonight';
      const head = ['today', 'tonight', 'tomorrow', 'yesterday'].includes(label.toLowerCase())
        ? `${label.charAt(0).toUpperCase()}${label.slice(1)}, ${dateText}`
        : (label && label.includes('AH') ? `${label} (${dateText})` : dateText);
      const where = spec.place ? spec.place.name : (this.locationInfo || 'your location');
      const notes = (spec.notes || []).map(n => `<div class="msg-note">${escapeHtml(n)}</div>`).join('');
      const method = METHOD_LABELS[this.settings.method] || this.settings.method;
      const tzNote = spec.place ? ` Times are local to ${escapeHtml(spec.place.name)} (${escapeHtml(tz)}).` : '';
      return `<p><strong>${escapeHtml(head)}</strong> in ${escapeHtml(where)}</p><ul class="msg-time-list">${lines}</ul>${notes}`
           + `<div class="msg-note">Calculated with your settings: ${escapeHtml(method)}, Fajr ${escapeHtml(this.settings.fajrAngle)}°, Isha ${escapeHtml(this.settings.ishaAngle)}°.${tzNote}</div>`;
    },

    newChat() {
      this.messages = [];
      this.lastTimes = null;
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
      const last = [...this.messages].reverse().find(m => m.role === 'assistant');
      if (!last?.text || !window.speechSynthesis) return;
      speechSynthesis.cancel();
      const utt = new SpeechSynthesisUtterance(last.text);
      utt.lang = LANG_SPEECH[this.chatLang] || 'en-US';
      speechSynthesis.speak(utt);
    },
  };
}
