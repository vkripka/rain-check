// =========================================================================
// RAIN CHECK — LÓGICA DO APLICATIVO (GPS, Clima, UI e Web Push às 21h)
// =========================================================================

const STORAGE_KEY_LOC = "raincheck_saved_location_v1";
const STORAGE_KEY_TIME = "raincheck_notify_time_v1";

let currentState = {
  lat: -23.5505,
  lon: -46.6333,
  city: "São Paulo, SP",
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Sao_Paulo",
  notifyTime: localStorage.getItem(STORAGE_KEY_TIME) || "21:00",
  swRegistration: null,
  pushSubscription: null,
  weatherData: null
};

// Ícones SVG vetoriais nítidos estilo iOS Weather
function getWeatherSvg(iconType, size = 28) {
  const s = size;
  switch (iconType) {
    case "sun":
      return `<svg width="${s}" height="${s}" viewBox="0 0 64 64" fill="none">
        <circle cx="32" cy="32" r="14" fill="#FBBF24"/>
        <g stroke="#FBBF24" stroke-width="4" stroke-linecap="round">
          <line x1="32" y1="6" x2="32" y2="12"/><line x1="32" y1="52" x2="32" y2="58"/>
          <line x1="6" y1="32" x2="12" y2="32"/><line x1="52" y1="32" x2="58" y2="32"/>
          <line x1="13.6" y1="13.6" x2="17.8" y2="17.8"/><line x1="46.2" y1="46.2" x2="50.4" y2="50.4"/>
          <line x1="50.4" y1="13.6" x2="46.2" y2="17.8"/><line x1="17.8" y1="46.2" x2="13.6" y2="50.4"/>
        </g>
      </svg>`;
    case "sun-cloud":
    case "cloud-sun":
      return `<svg width="${s}" height="${s}" viewBox="0 0 64 64" fill="none">
        <circle cx="24" cy="24" r="11" fill="#FBBF24"/>
        <path d="M22 46H47C52.5 46 57 41.5 57 36C57 30.8 53 26.5 47.9 26.1C46.2 19.2 40 14 32.5 14C23.9 14 17 20.9 17 29.5C17 30.1 17 30.7 17.1 31.3C12.5 32.4 9 36.5 9 41.5C9 44 11 46 13.5 46H22Z" fill="#F1F5F9"/>
      </svg>`;
    case "cloud":
    case "fog":
      return `<svg width="${s}" height="${s}" viewBox="0 0 64 64" fill="none">
        <path d="M18 48H48C53.5 48 58 43.5 58 38C58 32.8 54 28.5 48.9 28.1C47.2 21.2 41 16 33.5 16C24.9 16 18 22.9 18 31.5C18 32.1 18 32.7 18.1 33.3C13.5 34.4 10 38.5 10 43.5C10 46 12 48 14.5 48H18Z" fill="#CBD5E1"/>
      </svg>`;
    case "drizzle":
    case "rain":
    case "showers":
      return `<svg width="${s}" height="${s}" viewBox="0 0 64 64" fill="none">
        <path d="M18 42H48C53.5 42 58 37.5 58 32C58 26.8 54 22.5 48.9 22.1C47.2 15.2 41 10 33.5 10C24.9 10 18 16.9 18 25.5C13.5 26.6 10 30.7 10 35.5C10 39.1 12.9 42 16.5 42H18Z" fill="#E2E8F0"/>
        <g stroke="#38BDF8" stroke-width="4" stroke-linecap="round">
          <line x1="22" y1="48" x2="19" y2="57"/>
          <line x1="33" y1="48" x2="30" y2="57"/>
          <line x1="44" y1="48" x2="41" y2="57"/>
        </g>
      </svg>`;
    case "heavy-rain":
      return `<svg width="${s}" height="${s}" viewBox="0 0 64 64" fill="none">
        <path d="M18 40H48C53.5 40 58 35.5 58 30C58 24.8 54 20.5 48.9 20.1C47.2 13.2 41 8 33.5 8C24.9 8 18 14.9 18 23.5C13.5 24.6 10 28.7 10 33.5C10 37.1 12.9 40 16.5 40H18Z" fill="#94A3B8"/>
        <g stroke="#38BDF8" stroke-width="4.2" stroke-linecap="round">
          <line x1="20" y1="45" x2="16" y2="58"/>
          <line x1="30" y1="45" x2="26" y2="58"/>
          <line x1="40" y1="45" x2="36" y2="58"/>
          <line x1="50" y1="45" x2="46" y2="58"/>
        </g>
      </svg>`;
    case "thunderstorm":
      return `<svg width="${s}" height="${s}" viewBox="0 0 64 64" fill="none">
        <path d="M18 40H48C53.5 40 58 35.5 58 30C58 24.8 54 20.5 48.9 20.1C47.2 13.2 41 8 33.5 8C24.9 8 18 14.9 18 23.5C13.5 24.6 10 28.7 10 33.5C10 37.1 12.9 40 16.5 40H18Z" fill="#94A3B8"/>
        <polygon points="33,38 23,51 32,51 29,62 43,47 34,47" fill="#FBBF24"/>
      </svg>`;
    default:
      return `<svg width="${s}" height="${s}" viewBox="0 0 64 64" fill="none">
        <circle cx="32" cy="32" r="14" fill="#FBBF24"/>
      </svg>`;
  }
}

function getVerdictHeroSvg(verdict) {
  if (verdict === "YES") {
    // Guarda-chuva com gotas de chuva
    return getWeatherSvg("heavy-rain", 66);
  }
  if (verdict === "MAYBE") {
    return getWeatherSvg("showers", 66);
  }
  return getWeatherSvg("sun", 66);
}

// =========================================================================
// DETECÇÃO DE AMBIENTE iOS E TELA DE INÍCIO
// =========================================================================
function isIOSDevice() {
  const ua = window.navigator.userAgent || "";
  const iOS = /iPad|iPhone|iPod/.test(ua);
  const iPadOS = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  return iOS || iPadOS;
}

function isRunningStandalone() {
  return (
    window.navigator.standalone === true ||
    window.matchMedia("(display-mode: standalone)").matches
  );
}

function checkIOSInstallBanner() {
  const banner = document.getElementById("ios-install-banner");
  if (!banner) return;
  if (isIOSDevice() && !isRunningStandalone()) {
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

// =========================================================================
// GEOLOCALIZAÇÃO E BUSCA DE PREVISÃO
// =========================================================================
function loadSavedLocation() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_LOC);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed.lat === "number" && typeof parsed.lon === "number") {
        currentState.lat = parsed.lat;
        currentState.lon = parsed.lon;
        currentState.city = parsed.city || "";
        return true;
      }
    }
  } catch (e) {}
  return false;
}

function saveLocation(lat, lon, city) {
  currentState.lat = lat;
  currentState.lon = lon;
  if (city) currentState.city = city;
  localStorage.setItem(
    STORAGE_KEY_LOC,
    JSON.stringify({ lat: currentState.lat, lon: currentState.lon, city: currentState.city })
  );
}

function requestDeviceGPS(showSpinner = true) {
  if (!("geolocation" in navigator)) {
    fetchWeather(currentState.lat, currentState.lon, currentState.city);
    return;
  }

  if (showSpinner) {
    document.getElementById("city-name").textContent = "Obtendo GPS...";
    document.getElementById("refresh-icon").classList.add("spin");
  }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      saveLocation(lat, lon, "");
      fetchWeather(lat, lon, "");
    },
    (err) => {
      console.warn("Permissão de GPS negada ou indisponível, usando localização salva:", err.message);
      fetchWeather(currentState.lat, currentState.lon, currentState.city);
    },
    { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
  );
}

async function fetchWeather(lat, lon, city = "") {
  const refreshIcon = document.getElementById("refresh-icon");
  refreshIcon.classList.add("spin");

  try {
    const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    if (city) params.set("city", city);

    const res = await fetch(`/api/weather?${params.toString()}`);
    if (!res.ok) throw new Error("Falha ao consultar servidor meteorológico");
    const data = await res.json();

    currentState.weatherData = data;
    currentState.timezone = data.timezone || currentState.timezone;
    saveLocation(data.location.lat, data.location.lon, data.location.city);

    renderWeatherUI(data);

    // Se o usuário já tem o Push de 21h ativo, atualiza silenciosamente as coordenadas no servidor
    if (currentState.pushSubscription) {
      syncSubscriptionWithServer(currentState.pushSubscription, true);
    }
  } catch (err) {
    console.error("Erro ao carregar previsão:", err);
    document.getElementById("verdict-headline").textContent = "Sem conexão no momento";
    document.getElementById("verdict-summary").textContent =
      "Toque no botão de atualizar no canto superior direito para tentar novamente.";
  } finally {
    refreshIcon.classList.remove("spin");
  }
}

// =========================================================================
// RENDERIZAÇÃO DA INTERFACE
// =========================================================================
function renderWeatherUI(data) {
  // 1. Topbar
  document.getElementById("city-name").textContent = data.location.city;
  document.getElementById("updated-time").textContent = `• ${data.updated_at}`;

  // 2. Tema visual e Card Principal (Vai Chover Amanhã?)
  const tom = data.tomorrow;
  const heroCard = document.getElementById("tomorrow-hero");
  heroCard.classList.remove("verdict-loading", "verdict-yes", "verdict-maybe", "verdict-no");
  document.body.classList.remove("theme-default", "theme-rain", "theme-maybe", "theme-clear");

  if (tom.verdict === "YES") {
    heroCard.classList.add("verdict-yes");
    document.body.classList.add("theme-rain");
  } else if (tom.verdict === "MAYBE") {
    heroCard.classList.add("verdict-maybe");
    document.body.classList.add("theme-maybe");
  } else {
    heroCard.classList.add("verdict-no");
    document.body.classList.add("theme-clear");
  }

  const [yyyy, mm, dd] = tom.date.split("-");
  document.getElementById("tomorrow-date-label").textContent = `Amanhã • ${dd}/${mm}`;
  document.getElementById("verdict-badge").textContent = tom.badge_text;
  document.getElementById("verdict-icon-wrap").innerHTML = getVerdictHeroSvg(tom.verdict);
  document.getElementById("verdict-headline").textContent = tom.headline;
  document.getElementById("verdict-summary").textContent = tom.summary;

  document.getElementById("tom-prob").textContent = `${tom.max_prob}%`;
  document.getElementById("tom-mm").textContent = `${tom.total_mm} mm`;
  document.getElementById("tom-peak").textContent = tom.peak_hour;
  document.getElementById("tom-temps").textContent = `${tom.temp_min}° / ${tom.temp_max}°`;

  // 3. Momento Atual ("AGORA")
  const curr = data.current;
  document.getElementById("current-icon").innerHTML = getWeatherSvg(curr.icon, 40);
  document.getElementById("current-desc").textContent = curr.description;
  document.getElementById("current-feels").textContent = `${curr.feels_like}°`;
  document.getElementById("current-humidity").textContent = `${curr.humidity}%`;
  document.getElementById("current-wind").textContent = `${curr.wind_kmh}`;
  document.getElementById("current-temp").textContent = `${curr.temp}°`;
  document.getElementById("current-hilo").textContent = `Máx:${curr.temp_max}° Mín:${curr.temp_min}°`;

  // 4. Próximas 24 Horas
  const n12 = data.next_12h_summary;
  const subEl = document.getElementById("next12-subtitle");
  if (n12.max_prob >= 40 || n12.total_mm >= 0.3) {
    subEl.textContent = `Atenção: até ${n12.max_prob}% de chance de chuva (${n12.total_mm} mm) nas próximas 12h`;
  } else {
    subEl.textContent = `Sem chuva relevante nas próximas 12h (máx ${n12.max_prob}%)`;
  }

  const hourlyScroll = document.getElementById("hourly-scroll");
  hourlyScroll.innerHTML = data.next_24h
    .map((h, idx) => {
      const isRainy = h.rain_prob >= 40 || h.rain_mm >= 0.2;
      const label = idx === 0 ? "Agora" : h.hour_label;
      return `
        <div class="hour-item ${isRainy ? "is-rainy" : ""}">
          <span class="hour-label">${label}</span>
          <div class="hour-icon">${getWeatherSvg(h.icon, 26)}</div>
          <span class="hour-prob">${h.rain_prob >= 10 ? h.rain_prob + "%" : "—"}</span>
          <span class="hour-temp">${h.temp}°</span>
          <span class="hour-mm">${h.rain_mm > 0 ? h.rain_mm + "mm" : ""}</span>
        </div>
      `;
    })
    .join("");

  // 5. Turnos de Amanhã (Madrugada, Manhã, Tarde, Noite)
  const periodsGrid = document.getElementById("tomorrow-periods-grid");
  periodsGrid.innerHTML = tom.periods
    .map((p) => {
      const alertClass = p.rain_prob >= 45 || p.rain_mm >= 0.4 ? "period-rain-alert" : "";
      return `
        <div class="period-card ${alertClass}">
          <div class="period-top">
            <span class="period-name">${p.label}</span>
            <span class="period-hours">${p.hours_label}</span>
          </div>
          <div class="period-mid">
            <div class="period-icon">${getWeatherSvg(p.icon, 34)}</div>
            <div>
              <div class="period-temps">${p.temp_min}° a ${p.temp_max}°</div>
              <div class="period-desc">${p.description}</div>
            </div>
          </div>
          <div class="period-bar-wrap">
            <div class="period-rain-row">
              <span class="period-prob-label">💧 ${p.rain_prob}% chance</span>
              <span class="period-mm-label">${p.rain_mm} mm</span>
            </div>
            <div class="prob-bar-bg">
              <div class="prob-bar-fill" style="width: ${Math.min(100, p.rain_prob)}%"></div>
            </div>
          </div>
        </div>
      `;
    })
    .join("");

  // Gaveta Hora a Hora de Amanhã (00h - 23h)
  const tomHourlyScroll = document.getElementById("tomorrow-hourly-scroll");
  tomHourlyScroll.innerHTML = tom.hours
    .map((h) => {
      const isRainy = h.rain_prob >= 40 || h.rain_mm >= 0.2;
      return `
        <div class="hour-item ${isRainy ? "is-rainy" : ""}">
          <span class="hour-label">${h.hour_label}</span>
          <div class="hour-icon">${getWeatherSvg(h.icon, 26)}</div>
          <span class="hour-prob">${h.rain_prob}%</span>
          <span class="hour-temp">${h.temp}°</span>
          <span class="hour-mm">${h.rain_mm > 0 ? h.rain_mm + "mm" : ""}</span>
        </div>
      `;
    })
    .join("");

  // 6. Prévia da Notificação das 21h
  if (tom.notification_preview) {
    document.getElementById("preview-notif-title").textContent = tom.notification_preview.title;
    document.getElementById("preview-notif-body").textContent = tom.notification_preview.body;
  }

  // 7. Lista de 7 Dias
  const dailyList = document.getElementById("daily-list");
  dailyList.innerHTML = data.daily_7d
    .map((d) => {
      const isTom = d.label === "Amanhã";
      return `
        <div class="day-row ${isTom ? "is-tomorrow" : ""}">
          <span class="day-name">${d.label}</span>
          <div class="day-icon">${getWeatherSvg(d.icon, 26)}</div>
          <span class="day-rain">${d.rain_prob >= 15 ? "💧 " + d.rain_prob + "%" : "—"}</span>
          <div class="day-temps">
            <span class="day-temp-min">${d.temp_min}°</span>
            <span>${d.temp_max}°</span>
          </div>
        </div>
      `;
    })
    .join("");
}

// =========================================================================
// NOTIFICAÇÕES WEB PUSH (iOS 16.4+ & Geral)
// =========================================================================
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function showPushFeedback(msg, isError = false) {
  const el = document.getElementById("push-feedback-msg");
  el.textContent = msg;
  el.style.color = isError ? "#fca5a5" : "#6ee7b7";
  el.classList.remove("hidden");
}

async function initServiceWorkerAndPush() {
  if (!("serviceWorker" in navigator)) {
    document.getElementById("notif-status-text").textContent =
      "Adicione à Tela de Início do iPhone para habilitar notificações Push.";
    return;
  }

  try {
    const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    currentState.swRegistration = reg;

    if ("pushManager" in reg) {
      const existingSub = await reg.pushManager.getSubscription();
      if (existingSub) {
        currentState.pushSubscription = existingSub;
        document.getElementById("toggle-push").checked = true;
        document.getElementById("notif-status-text").textContent =
          `Ativo! Alerta agendado todos os dias às ${currentState.notifyTime}`;
        syncSubscriptionWithServer(existingSub, true);
      }
    }
  } catch (err) {
    console.warn("Erro ao registrar Service Worker:", err);
  }
}

async function subscribeUserToPush() {
  const toggle = document.getElementById("toggle-push");

  if (isIOSDevice() && !isRunningStandalone()) {
    toggle.checked = false;
    showPushFeedback(
      "No iPhone, toque em Compartilhar > Adicionar à Tela de Início e abra o app pelo ícone para ativar notificações!",
      true
    );
    document.getElementById("ios-install-banner").classList.remove("hidden");
    return;
  }

  if (!("Notification" in window) || !currentState.swRegistration || !("pushManager" in currentState.swRegistration)) {
    toggle.checked = false;
    showPushFeedback(
      "Seu navegador atual não expõe a API Push. No iPhone (iOS 16.4+), abra pelo ícone da Tela de Início.",
      true
    );
    return;
  }

  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      toggle.checked = false;
      showPushFeedback("Permissão de notificação negada nos Ajustes do aparelho.", true);
      return;
    }

    const keyRes = await fetch("/api/vapid-public-key");
    const { publicKey } = await keyRes.json();
    const convertedKey = urlBase64ToUint8Array(publicKey);

    const subscription = await currentState.swRegistration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: convertedKey
    });

    currentState.pushSubscription = subscription;
    await syncSubscriptionWithServer(subscription, false);
    toggle.checked = true;
    document.getElementById("notif-status-text").textContent =
      `Ativo! Alerta agendado todos os dias às ${currentState.notifyTime}`;
    showPushFeedback(`✅ Alerta diário ativado para ${currentState.notifyTime} em ${currentState.city}!`);
  } catch (err) {
    console.error("Erro ao assinar Web Push:", err);
    toggle.checked = false;
    showPushFeedback(`Não foi possível ativar: ${err.message}`, true);
  }
}

async function syncSubscriptionWithServer(subscription, silent = false) {
  const res = await fetch("/api/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      subscription: subscription.toJSON ? subscription.toJSON() : subscription,
      lat: currentState.lat,
      lon: currentState.lon,
      city: currentState.city,
      timezone: currentState.timezone,
      notify_time: currentState.notifyTime,
      enabled: true
    })
  });
  if (!res.ok && !silent) {
    throw new Error("Erro ao salvar inscrição no servidor");
  }
}

async function unsubscribeUserFromPush() {
  try {
    if (currentState.pushSubscription) {
      const endpoint = currentState.pushSubscription.endpoint;
      await currentState.pushSubscription.unsubscribe();
      currentState.pushSubscription = null;
      await fetch("/api/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint })
      });
    }
    document.getElementById("notif-status-text").textContent =
      "Alerta desativado. Ative para receber a previsão às 21h.";
    showPushFeedback("Alerta diário desativado.");
  } catch (e) {
    console.warn("Erro ao cancelar push:", e);
  }
}

async function triggerTestNotification() {
  if (!currentState.pushSubscription) {
    await subscribeUserToPush();
    if (!currentState.pushSubscription) return;
  }

  showPushFeedback("Enviando notificação de teste para o seu aparelho...");
  try {
    const res = await fetch("/api/test-notification", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subscription: currentState.pushSubscription.toJSON
          ? currentState.pushSubscription.toJSON()
          : currentState.pushSubscription,
        lat: currentState.lat,
        lon: currentState.lon,
        city: currentState.city
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Falha ao enviar teste");
    showPushFeedback("🔔 Notificação enviada! Confira o topo da tela ou bloqueie o iPhone para ver.");
  } catch (err) {
    showPushFeedback(`Erro no teste: ${err.message}`, true);
  }
}

// =========================================================================
// INICIALIZAÇÃO E EVENTOS DE UI
// =========================================================================
document.addEventListener("DOMContentLoaded", () => {
  checkIOSInstallBanner();

  const timeInput = document.getElementById("input-notify-time");
  timeInput.value = currentState.notifyTime;
  document.querySelector(".preview-time").textContent = currentState.notifyTime;

  // Carrega localização salva imediatamente para resposta instantânea, e em seguida atualiza via GPS
  const hadSaved = loadSavedLocation();
  if (hadSaved) {
    fetchWeather(currentState.lat, currentState.lon, currentState.city);
    requestDeviceGPS(false);
  } else {
    requestDeviceGPS(true);
  }

  initServiceWorkerAndPush();

  // Botões da barra superior
  document.getElementById("btn-gps").addEventListener("click", () => requestDeviceGPS(true));
  document.getElementById("btn-refresh").addEventListener("click", () =>
    fetchWeather(currentState.lat, currentState.lon, currentState.city)
  );

  // Gaveta de 24h completas de amanhã
  const btnToggleTom = document.getElementById("btn-toggle-tomorrow-hours");
  const drawerTom = document.getElementById("tomorrow-all-hours-wrap");
  btnToggleTom.addEventListener("click", () => {
    const isHidden = drawerTom.classList.toggle("hidden");
    btnToggleTom.textContent = isHidden ? "Ver 24h de amanhã" : "Ocultar 24h";
  });

  // Controles de Notificação Push
  document.getElementById("toggle-push").addEventListener("change", (e) => {
    if (e.target.checked) {
      subscribeUserToPush();
    } else {
      unsubscribeUserFromPush();
    }
  });

  timeInput.addEventListener("change", (e) => {
    currentState.notifyTime = e.target.value || "21:00";
    localStorage.setItem(STORAGE_KEY_TIME, currentState.notifyTime);
    document.querySelector(".preview-time").textContent = currentState.notifyTime;
    if (currentState.pushSubscription) {
      syncSubscriptionWithServer(currentState.pushSubscription, false).then(() => {
        document.getElementById("notif-status-text").textContent =
          `Ativo! Alerta agendado todos os dias às ${currentState.notifyTime}`;
        showPushFeedback(`Horário atualizado para ${currentState.notifyTime}!`);
      });
    }
  });

  document.getElementById("btn-test-push").addEventListener("click", triggerTestNotification);

  // Modal de busca de cidade
  const searchModal = document.getElementById("search-modal");
  const searchInput = document.getElementById("city-search-input");
  const searchResults = document.getElementById("city-search-results");

  document.getElementById("btn-open-search").addEventListener("click", () => {
    searchModal.classList.remove("hidden");
    searchInput.value = "";
    searchResults.innerHTML = "";
    setTimeout(() => searchInput.focus(), 100);
  });

  document.getElementById("btn-close-search").addEventListener("click", () => {
    searchModal.classList.add("hidden");
  });

  document.getElementById("btn-use-current-gps").addEventListener("click", () => {
    searchModal.classList.add("hidden");
    requestDeviceGPS(true);
  });

  let searchDebounce = null;
  searchInput.addEventListener("input", (e) => {
    clearTimeout(searchDebounce);
    const q = e.target.value.trim();
    if (q.length < 2) {
      searchResults.innerHTML = "";
      return;
    }
    searchDebounce = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search-city?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        searchResults.innerHTML = (data.results || [])
          .map(
            (item) => `
            <div class="search-result-item" data-lat="${item.lat}" data-lon="${item.lon}" data-name="${item.display_name}">
              <span>📍 ${item.display_name}</span>
              <span style="opacity:0.5">→</span>
            </div>
          `
          )
          .join("");

        searchResults.querySelectorAll(".search-result-item").forEach((el) => {
          el.addEventListener("click", () => {
            const lat = parseFloat(el.getAttribute("data-lat"));
            const lon = parseFloat(el.getAttribute("data-lon"));
            const name = el.getAttribute("data-name");
            searchModal.classList.add("hidden");
            saveLocation(lat, lon, name);
            fetchWeather(lat, lon, name);
          });
        });
      } catch (err) {}
    }, 280);
  });

  // Atualiza automaticamente quando o usuário volta para o app no iPhone
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      fetchWeather(currentState.lat, currentState.lon, currentState.city);
    }
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", (event) => {
      if (event.data && event.data.type === "REFRESH_WEATHER_FROM_PUSH") {
        fetchWeather(currentState.lat, currentState.lon, currentState.city);
      }
    });
  }
});
