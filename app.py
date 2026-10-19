import os
import json
import base64
import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import Flask, request, jsonify, send_from_directory
from pywebpush import webpush, WebPushException
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from PIL import Image, ImageDraw

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RainCheck")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
ICONS_DIR = os.path.join(STATIC_DIR, "icons")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ICONS_DIR, exist_ok=True)

VAPID_FILE = os.path.join(DATA_DIR, "vapid.json")
SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, "subscriptions.json")
SUB_LOCK = threading.Lock()

app = Flask(__name__, static_folder="static", static_url_path="/static")


# =====================================================================
# 1. GERADOR DE ÍCONES NATIVOS iOS (Apple Touch Icon & PWA Icons)
# =====================================================================
def ensure_app_icons():
    """Gera ícones PNG de alta resolução com visual nativo do iOS caso não existam."""
    sizes = {
        "icon-180.png": 180,
        "icon-192.png": 192,
        "icon-512.png": 512,
        "badge-72.png": 72,
    }
    if all(os.path.exists(os.path.join(ICONS_DIR, fname)) for fname in sizes):
        return

    logger.info("Gerando ícones do aplicativo iOS (Apple Touch Icons)...")
    for fname, size in sizes.items():
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fundo gradiente estilo iOS Weather (azul profundo -> azul celeste)
        for y in range(size):
            ratio = y / float(size)
            r = int(13 + (28 - 13) * ratio)
            g = int(27 + (78 - 27) * ratio)
            b = int(62 + (148 - 62) * ratio)
            draw.line([(0, y), (size, y)], fill=(r, g, b, 255))

        # Sol dourado parcialmente atrás da nuvem
        sun_cx = int(size * 0.36)
        sun_cy = int(size * 0.34)
        sun_r = int(size * 0.17)
        draw.ellipse(
            [sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r],
            fill=(255, 204, 51, 255),
        )

        # Nuvem branca macia
        c_y = int(size * 0.46)
        # Base da nuvem
        draw.rounded_rectangle(
            [int(size * 0.20), int(size * 0.40), int(size * 0.82), int(size * 0.62)],
            radius=int(size * 0.11),
            fill=(248, 251, 255, 255),
        )
        # Bolhas superiores da nuvem
        draw.ellipse(
            [int(size * 0.27), int(size * 0.28), int(size * 0.57), int(size * 0.56)],
            fill=(255, 255, 255, 255),
        )
        draw.ellipse(
            [int(size * 0.46), int(size * 0.24), int(size * 0.76), int(size * 0.54)],
            fill=(245, 249, 255, 255),
        )

        # Gotas de chuva azul-ciano brilhantes abaixo da nuvem
        drop_color = (56, 189, 248, 255)
        drop_positions = [
            (0.33, 0.70),
            (0.50, 0.74),
            (0.67, 0.70),
        ]
        drop_w = max(2, int(size * 0.045))
        drop_h = max(4, int(size * 0.11))
        for dx_ratio, dy_ratio in drop_positions:
            dx = int(size * dx_ratio)
            dy = int(size * dy_ratio)
            draw.rounded_rectangle(
                [dx - drop_w, dy, dx + drop_w, dy + drop_h],
                radius=drop_w,
                fill=drop_color,
            )

        img.save(os.path.join(ICONS_DIR, fname), "PNG")


# =====================================================================
# 2. CHAVES VAPID PARA WEB PUSH (Compatível com Apple APNs Web Push)
# =====================================================================
def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def get_or_create_vapid_keys():
    """Retorna ou cria par de chaves ECDSA P-256 para notificações Web Push."""
    env_pub = os.environ.get("VAPID_PUBLIC_KEY")
    env_priv = os.environ.get("VAPID_PRIVATE_KEY")
    if env_pub and env_priv:
        return {
            "public_key": env_pub,
            "private_key": env_priv,
            "subject": os.environ.get("VAPID_SUBJECT", "mailto:alerta@raincheck.app"),
        }

    if os.path.exists(VAPID_FILE):
        with open(VAPID_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    logger.info("Gerando novas chaves VAPID ECDSA P-256 para Web Push...")
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Raw 32-byte private value in base64url (aceito nativamente pelo pywebpush/py_vapid)
    priv_num = private_key.private_numbers().private_value
    priv_bytes = priv_num.to_bytes(32, byteorder="big")
    priv_b64 = b64url_encode(priv_bytes)

    # Uncompressed 65-byte EC point (0x04 || X || Y) para applicationServerKey do navegador
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    pub_b64 = b64url_encode(pub_bytes)

    vapid_data = {
        "public_key": pub_b64,
        "private_key": priv_b64,
        "subject": "mailto:alerta@raincheck.app",
    }
    with open(VAPID_FILE, "w", encoding="utf-8") as f:
        json.dump(vapid_data, f, indent=2)
    return vapid_data


VAPID_KEYS = get_or_create_vapid_keys()
ensure_app_icons()


# =====================================================================
# 3. ARMAZENAMENTO DE INSCRIÇÕES PUSH E LOCALIZAÇÃO
# =====================================================================
def load_subscriptions():
    with SUB_LOCK:
        if not os.path.exists(SUBSCRIPTIONS_FILE):
            return {}
        try:
            with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler inscrições: {e}")
            return {}


def save_subscriptions(subs):
    with SUB_LOCK:
        with open(SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(subs, f, indent=2, ensure_ascii=False)


# =====================================================================
# 4. MOTOR METEOROLÓGICO (Open-Meteo + Interpretação Clara de Chuva)
# =====================================================================
WMO_DESCRIPTIONS = {
    0: ("Céu limpo", "sun"),
    1: ("Predominantemente limpo", "sun-cloud"),
    2: ("Parcialmente nublado", "cloud-sun"),
    3: ("Encoberto", "cloud"),
    45: ("Nevoeiro", "fog"),
    48: ("Nevoeiro com geada", "fog"),
    51: ("Garoa leve", "drizzle"),
    53: ("Garoa moderada", "drizzle"),
    55: ("Garoa intensa", "drizzle"),
    56: ("Garoa gelada", "drizzle"),
    57: ("Garoa gelada densa", "drizzle"),
    61: ("Chuva fraca", "rain"),
    63: ("Chuva moderada", "rain"),
    65: ("Chuva forte", "heavy-rain"),
    66: ("Chuva congelante leve", "rain"),
    67: ("Chuva congelante forte", "heavy-rain"),
    71: ("Neve fraca", "snow"),
    73: ("Neve moderada", "snow"),
    75: ("Neve forte", "snow"),
    77: ("Grãos de neve", "snow"),
    80: ("Pancadas de chuva leves", "showers"),
    81: ("Pancadas de chuva moderadas", "showers"),
    82: ("Pancadas de chuva fortes", "heavy-rain"),
    85: ("Pancadas de neve", "snow"),
    86: ("Pancadas de neve fortes", "snow"),
    95: ("Tempestade com raios", "thunderstorm"),
    96: ("Tempestade com granizo leve", "thunderstorm"),
    99: ("Tempestade severa com granizo", "thunderstorm"),
}

RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def wmo_info(code):
    code_int = int(code) if code is not None else 0
    desc, icon = WMO_DESCRIPTIONS.get(code_int, ("Parcialmente nublado", "cloud-sun"))
    return {"code": code_int, "description": desc, "icon": icon}


def format_rain_windows(rainy_hours):
    """Agrupa horas de chuva (ex: [14, 15, 16, 17]) em texto legível ('entre 14h e 18h')."""
    if not rainy_hours:
        return None
    rainy_hours = sorted(set(rainy_hours))
    ranges = []
    start = rainy_hours[0]
    prev = rainy_hours[0]
    for h in rainy_hours[1:]:
        if h == prev + 1:
            prev = h
        else:
            ranges.append((start, prev))
            start = h
            prev = h
    ranges.append((start, prev))

    parts = []
    for s, e in ranges:
        if s == e:
            parts.append(f"às {s:02d}h")
        else:
            end_h = (e + 1) % 24
            parts.append(f"das {s:02d}h às {end_h:02d}h")
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " e " + parts[-1]


def fetch_and_analyze_weather(lat: float, lon: float, city_name: str = None):
    """Busca dados da Open-Meteo e monta diagnóstico completo sobre hoje, próximas 24h e amanhã."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,weather_code,wind_speed_10m,uv_index,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,precipitation_hours,uv_index_max,wind_speed_10m_max,sunrise,sunset",
        "timezone": "auto",
        "forecast_days": 7,
    }
    resp = requests.get(url, params=params, timeout=12)
    resp.raise_for_status()
    raw = resp.json()

    tz_name = raw.get("timezone", "America/Sao_Paulo")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")

    now_local = datetime.now(tz)
    today_str = now_local.strftime("%Y-%m-%d")
    tomorrow_dt = now_local + timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")
    now_iso_hour = now_local.strftime("%Y-%m-%dT%H:00")

    # 1. Processa dados horários
    h_data = raw.get("hourly", {})
    h_times = h_data.get("time", [])
    h_temp = h_data.get("temperature_2m", [])
    h_feels = h_data.get("apparent_temperature", [])
    h_prob = h_data.get("precipitation_probability", [])
    h_precip = h_data.get("precipitation", [])
    h_code = h_data.get("weather_code", [])
    h_wind = h_data.get("wind_speed_10m", [])
    h_uv = h_data.get("uv_index", [])
    h_is_day = h_data.get("is_day", [])

    hourly_list = []
    for i, t_str in enumerate(h_times):
        info = wmo_info(h_code[i] if i < len(h_code) else 0)
        hourly_list.append({
            "time": t_str,
            "date": t_str[:10],
            "hour": int(t_str[11:13]),
            "hour_label": f"{t_str[11:13]}h",
            "temp": round(h_temp[i]) if i < len(h_temp) and h_temp[i] is not None else 0,
            "feels_like": round(h_feels[i]) if i < len(h_feels) and h_feels[i] is not None else 0,
            "rain_prob": int(h_prob[i]) if i < len(h_prob) and h_prob[i] is not None else 0,
            "rain_mm": round(float(h_precip[i]), 1) if i < len(h_precip) and h_precip[i] is not None else 0.0,
            "weather_code": info["code"],
            "description": info["description"],
            "icon": info["icon"],
            "wind_kmh": round(h_wind[i]) if i < len(h_wind) and h_wind[i] is not None else 0,
            "uv": round(h_uv[i], 1) if i < len(h_uv) and h_uv[i] is not None else 0,
            "is_day": bool(h_is_day[i]) if i < len(h_is_day) else True,
        })

    # Próximas 24 horas a partir da hora atual
    start_idx = 0
    for idx, item in enumerate(hourly_list):
        if item["time"] >= now_iso_hour:
            start_idx = idx
            break
    next_24h = hourly_list[start_idx : start_idx + 24]

    # Horas do dia seguinte (Amanhã: 00h às 23h)
    tomorrow_hours = [item for item in hourly_list if item["date"] == tomorrow_str]

    # 2. Análise detalhada de AMANHÃ ("Vai chover amanhã?")
    tom_max_prob = max((h["rain_prob"] for h in tomorrow_hours), default=0)
    tom_total_mm = round(sum(h["rain_mm"] for h in tomorrow_hours), 1)
    tom_min_temp = min((h["temp"] for h in tomorrow_hours), default=0)
    tom_max_temp = max((h["temp"] for h in tomorrow_hours), default=0)

    # Identifica horas com chuva relevante amanhã
    rainy_hours_objs = [
        h for h in tomorrow_hours
        if h["rain_prob"] >= 45 or h["rain_mm"] >= 0.3 or h["weather_code"] in RAIN_CODES
    ]
    rainy_hour_nums = [h["hour"] for h in rainy_hours_objs]
    rain_window_text = format_rain_windows(rainy_hour_nums)

    # Hora de pico da chuva amanhã
    peak_hour_obj = max(
        tomorrow_hours,
        key=lambda h: (h["rain_prob"], h["rain_mm"]),
        default=None,
    )

    # Classificação principal: YES / MAYBE / NO
    if tom_max_prob >= 50 or tom_total_mm >= 1.2:
        verdict = "YES"
        headline = "Sim, vai chover amanhã!"
        badge_text = "LEVE O GUARDA-CHUVA ☔"
        if tom_total_mm >= 15 or tom_max_prob >= 80:
            intensity = "Chuva forte/significativa prevista"
        elif tom_total_mm >= 5:
            intensity = "Chuva moderada prevista"
        else:
            intensity = "Pancadas de chuva ou chuva leve"

        if rain_window_text:
            summary = (
                f"{intensity} com {tom_max_prob}% de probabilidade máxima "
                f"(acumulado de {tom_total_mm} mm), concentrada {rain_window_text}."
            )
        else:
            summary = (
                f"{intensity} com {tom_max_prob}% de chance e volume estimado de {tom_total_mm} mm ao longo do dia."
            )
        notif_title = f"🌧️ Vai chover amanhã em {city_name or 'sua região'}!"
        notif_body = (
            f"Chance de {tom_max_prob}% ({tom_total_mm} mm)"
            + (f" {rain_window_text}." if rain_window_text else ".")
            + f" Temp: {tom_min_temp}°C a {tom_max_temp}°C. Prepare o guarda-chuva!"
        )
    elif tom_max_prob >= 30 or tom_total_mm >= 0.3:
        verdict = "MAYBE"
        headline = "Pode chover fraco amanhã"
        badge_text = "ATENÇÃO AO TEMPO 🌦️"
        if rain_window_text:
            summary = (
                f"Há uma chance moderada de {tom_max_prob}% ({tom_total_mm} mm), "
                f"principalmente {rain_window_text}. Vale ter um guarda-chuva por perto."
            )
        else:
            summary = (
                f"Probabilidade moderada de {tom_max_prob}% com pouca água prevista ({tom_total_mm} mm). "
                f"Temperaturas entre {tom_min_temp}°C e {tom_max_temp}°C."
            )
        notif_title = f"🌦️ Possibilidade de chuva amanhã ({tom_max_prob}%)"
        notif_body = (
            f"Previsão para {city_name or 'sua região'}: {tom_max_prob}% de chance ({tom_total_mm} mm)"
            + (f" {rain_window_text}." if rain_window_text else ".")
            + f" Mín {tom_min_temp}°C / Máx {tom_max_temp}°C."
        )
    else:
        verdict = "NO"
        headline = "Não vai chover amanhã!"
        badge_text = "TEMPO FIRME ☀️"
        summary = (
            f"Dia sem chuva previsto! Probabilidade máxima de apenas {tom_max_prob}% "
            f"e temperaturas variando entre {tom_min_temp}°C e {tom_max_temp}°C."
        )
        notif_title = f"☀️ Sem chuva amanhã em {city_name or 'sua região'}!"
        notif_body = (
            f"Tempo firme amanhã (chance de chuva de apenas {tom_max_prob}%). "
            f"Temperaturas entre {tom_min_temp}°C e {tom_max_temp}°C. Aproveite o dia!"
        )

    # 3. Divisão de Amanhã em 4 turnos (Madrugada, Manhã, Tarde, Noite)
    period_defs = [
        ("madrugada", "Madrugada", "00h – 06h", range(0, 6)),
        ("manha", "Manhã", "06h – 12h", range(6, 12)),
        ("tarde", "Tarde", "12h – 18h", range(12, 18)),
        ("noite", "Noite", "18h – 24h", range(18, 24)),
    ]
    tomorrow_periods = []
    for key, label, time_range_label, hr_range in period_defs:
        p_hours = [h for h in tomorrow_hours if h["hour"] in hr_range]
        if not p_hours:
            continue
        p_max_prob = max(h["rain_prob"] for h in p_hours)
        p_sum_mm = round(sum(h["rain_mm"] for h in p_hours), 1)
        p_min_t = min(h["temp"] for h in p_hours)
        p_max_t = max(h["temp"] for h in p_hours)
        # Escolhe o código meteorológico mais severo do período
        worst_h = max(p_hours, key=lambda h: (h["rain_prob"], h["weather_code"]))
        tomorrow_periods.append({
            "key": key,
            "label": label,
            "hours_label": time_range_label,
            "rain_prob": p_max_prob,
            "rain_mm": p_sum_mm,
            "temp_min": p_min_t,
            "temp_max": p_max_t,
            "description": worst_h["description"],
            "icon": worst_h["icon"],
        })

    # 4. Resumo das Próximas 12 Horas (Curto prazo imediato)
    next_12h = next_24h[:12]
    next12_max_prob = max((h["rain_prob"] for h in next_12h), default=0)
    next12_mm = round(sum(h["rain_mm"] for h in next_12h), 1)
    next12_rain_hours = [
        h["hour_label"] for h in next_12h if h["rain_prob"] >= 45 or h["rain_mm"] >= 0.3
    ]

    # 5. Dados Diários (7 dias)
    d_data = raw.get("daily", {})
    d_times = d_data.get("time", [])
    daily_list = []
    weekdays_pt = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    for i, d_str in enumerate(d_times):
        dt_obj = datetime.strptime(d_str, "%Y-%m-%d")
        if d_str == today_str:
            day_label = "Hoje"
        elif d_str == tomorrow_str:
            day_label = "Amanhã"
        else:
            day_label = f"{weekdays_pt[dt_obj.weekday()]}, {dt_obj.strftime('%d/%m')}"

        d_info = wmo_info(d_data.get("weather_code", [0])[i])
        daily_list.append({
            "date": d_str,
            "label": day_label,
            "temp_max": round(d_data["temperature_2m_max"][i]),
            "temp_min": round(d_data["temperature_2m_min"][i]),
            "rain_prob": int(d_data["precipitation_probability_max"][i] or 0),
            "rain_mm": round(float(d_data["precipitation_sum"][i] or 0.0), 1),
            "rain_hours": round(float(d_data.get("precipitation_hours", [0])[i] or 0.0), 1),
            "uv_max": round(float(d_data.get("uv_index_max", [0])[i] or 0.0), 1),
            "wind_max": round(float(d_data.get("wind_speed_10m_max", [0])[i] or 0.0)),
            "sunrise": d_data.get("sunrise", [""])[i][-5:] if d_data.get("sunrise") else "06:00",
            "sunset": d_data.get("sunset", [""])[i][-5:] if d_data.get("sunset") else "18:00",
            "description": d_info["description"],
            "icon": d_info["icon"],
        })

    # 6. Condições atuais
    curr = raw.get("current", {})
    curr_info = wmo_info(curr.get("weather_code", 0))
    today_daily = daily_list[0] if daily_list else {}
    tomorrow_daily = daily_list[1] if len(daily_list) > 1 else {}

    return {
        "updated_at": now_local.strftime("%H:%M"),
        "timezone": tz_name,
        "location": {
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "city": city_name or "Sua Localização",
        },
        "current": {
            "temp": round(curr.get("temperature_2m", 0)),
            "feels_like": round(curr.get("apparent_temperature", 0)),
            "humidity": int(curr.get("relative_humidity_2m", 0)),
            "wind_kmh": round(curr.get("wind_speed_10m", 0)),
            "precipitation_mm": round(float(curr.get("precipitation", 0.0)), 1),
            "is_day": bool(curr.get("is_day", 1)),
            "description": curr_info["description"],
            "icon": curr_info["icon"],
            "temp_max": today_daily.get("temp_max", round(curr.get("temperature_2m", 0))),
            "temp_min": today_daily.get("temp_min", round(curr.get("temperature_2m", 0))),
        },
        "tomorrow": {
            "date": tomorrow_str,
            "verdict": verdict,  # YES | MAYBE | NO
            "headline": headline,
            "badge_text": badge_text,
            "summary": summary,
            "max_prob": tom_max_prob,
            "total_mm": tom_total_mm,
            "temp_min": tom_min_temp,
            "temp_max": tom_max_temp,
            "rain_window": rain_window_text or "Sem horário crítico",
            "peak_hour": f"{peak_hour_obj['hour']:02d}h ({peak_hour_obj['rain_prob']}%)" if peak_hour_obj and tom_max_prob > 0 else "—",
            "sunrise": tomorrow_daily.get("sunrise", "06:00"),
            "sunset": tomorrow_daily.get("sunset", "18:00"),
            "uv_max": tomorrow_daily.get("uv_max", 0),
            "wind_max": tomorrow_daily.get("wind_max", 0),
            "periods": tomorrow_periods,
            "hours": tomorrow_hours,
            "notification_preview": {
                "title": notif_title,
                "body": notif_body,
            },
        },
        "next_12h_summary": {
            "max_prob": next12_max_prob,
            "total_mm": next12_mm,
            "rain_hours": next12_rain_hours,
        },
        "next_24h": next_24h,
        "daily_7d": daily_list,
    }


def reverse_geocode_coords(lat: float, lon: float) -> str:
    """Converte coordenadas GPS (lat, lon) em nome da cidade/bairro."""
    try:
        headers = {"User-Agent": "RainCheck-iOS-WeatherApp/1.0"}
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "accept-language": "pt-BR"},
            headers=headers,
            timeout=6,
        )
        if r.ok:
            addr = r.json().get("address", {})
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("municipality")
                or addr.get("village")
                or addr.get("suburb")
            )
            state = addr.get("ISO3166-2-lvl4", "").replace("BR-", "")
            if city and state:
                return f"{city}, {state}"
            if city:
                return city
    except Exception as e:
        logger.warning(f"Falha no reverse geocode: {e}")
    return "Sua Localização"


# =====================================================================
# 5. ENVIO DE WEB PUSH E AGENDADOR EM SEGUNDO PLANO (21:00 DIÁRIO)
# =====================================================================
def fetch_met_no_fallback(lat: float, lon: float, city_name: str = "Sua Localização"):
    """Fallback meteorológico ultra-rápido via Instituto Meteorológico da Noruega (MET Norway) caso o IP do Render sofra timeout na Open-Meteo."""
    headers = {"User-Agent": "RainCheck-iOS-App/1.0 github.com/vkripka/rain-check"}
    r = requests.get(
        "https://api.met.no/weatherapi/locationforecast/2.0/compact",
        params={"lat": round(float(lat), 4), "lon": round(float(lon), 4)},
        headers=headers,
        timeout=8,
    )
    r.raise_for_status()
    timeseries = r.json().get("properties", {}).get("timeseries", [])
    tz = ZoneInfo("America/Sao_Paulo")
    tomorrow_str = (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")

    tom_mm = 0.0
    temps = []
    rainy_hours = []
    for item in timeseries:
        dt_utc = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
        dt_loc = dt_utc.astimezone(tz)
        if dt_loc.strftime("%Y-%m-%d") == tomorrow_str:
            details = item.get("data", {}).get("instant", {}).get("details", {})
            if "air_temperature" in details:
                temps.append(round(details["air_temperature"]))
            n1 = item.get("data", {}).get("next_1_hours", {}) or item.get("data", {}).get("next_6_hours", {})
            mm = float(n1.get("details", {}).get("precipitation_amount", 0.0))
            tom_mm += mm
            if mm >= 0.2:
                rainy_hours.append(dt_loc.hour)

    tom_mm = round(tom_mm, 1)
    t_min = min(temps) if temps else 18
    t_max = max(temps) if temps else 26
    window_txt = format_rain_windows(rainy_hours)

    if tom_mm >= 1.0:
        verdict = "YES"
        title = f"🌧️ Vai chover amanhã em {city_name}!"
        body = f"Volume previsto de {tom_mm} mm" + (f" ({window_txt})." if window_txt else ".") + f" Temp: {t_min}°C a {t_max}°C. Prepare o guarda-chuva!"
    elif tom_mm >= 0.2:
        verdict = "MAYBE"
        title = f"🌦️ Possibilidade de chuva fraca amanhã"
        body = f"Previsão para {city_name}: chuva leve ({tom_mm} mm). Mín {t_min}°C / Máx {t_max}°C."
    else:
        verdict = "NO"
        title = f"☀️ Sem chuva amanhã em {city_name}!"
        body = f"Tempo firme amanhã! Temperaturas entre {t_min}°C e {t_max}°C. Aproveite o dia!"

    return {"verdict": verdict, "title": title, "body": body}


def send_push_to_subscriber(sub_entry: dict, is_test: bool = False, custom_preview: dict = None) -> tuple[bool, str]:
    """Busca o clima atualizado em background para a localização do usuário e envia o Web Push."""
    subscription_info = sub_entry.get("subscription")
    if not subscription_info or not subscription_info.get("endpoint"):
        return False, "Inscrição Push inválida."

    lat = sub_entry.get("lat", -23.208)
    lon = sub_entry.get("lon", -45.9031)
    city = sub_entry.get("city", "Sua Localização")

    try:
        if custom_preview and custom_preview.get("title") and custom_preview.get("body"):
            title = custom_preview["title"]
            body = custom_preview["body"]
            verdict = custom_preview.get("verdict", "NO")
        else:
            try:
                weather = fetch_and_analyze_weather(lat, lon, city)
                preview = weather["tomorrow"]["notification_preview"]
                title = preview["title"]
                body = preview["body"]
                verdict = weather["tomorrow"]["verdict"]
            except Exception as wm_err:
                logger.warning(f"Open-Meteo lenta no servidor ({wm_err}), usando fallback MET Norway...")
                fb = fetch_met_no_fallback(lat, lon, city)
                title = fb["title"]
                body = fb["body"]
                verdict = fb["verdict"]

        if is_test:
            title = f"🔔 [Teste] {title}"

        payload = json.dumps({
            "title": title,
            "body": body,
            "verdict": verdict,
            "icon": "/static/icons/icon-192.png",
            "badge": "/static/icons/badge-72.png",
            "url": "/?from=push",
            "timestamp": int(time.time() * 1000),
        })

        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=VAPID_KEYS["private_key"],
            vapid_claims={"sub": VAPID_KEYS["subject"]},
            ttl=43200,
        )
        return True, "Notificação enviada com sucesso!"
    except WebPushException as ex:
        status_code = ex.response.status_code if ex.response is not None else 0
        logger.error(f"Erro WebPush (HTTP {status_code}): {ex}")
        if status_code in (404, 410):
            return False, "EXPIRED"
        return False, f"Erro no servidor Push ({status_code})"
    except Exception as e:
        logger.error(f"Erro ao processar push: {e}")
        return False, str(e)


def run_scheduled_notifications_check(force_all: bool = False):
    """Verifica todas as inscrições ativas e dispara a notificação às 21h (ou horário escolhido)."""
    subs = load_subscriptions()
    if not subs:
        return {"checked": 0, "sent": 0}

    sent_count = 0
    expired_keys = []
    changed = False

    for sub_id, entry in list(subs.items()):
        if not entry.get("enabled", True):
            continue

        tz_name = entry.get("timezone", "America/Sao_Paulo")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("America/Sao_Paulo")

        now_user = datetime.now(tz)
        today_str = now_user.strftime("%Y-%m-%d")
        target_hour = int(entry.get("notify_hour", 21))
        target_min = int(entry.get("notify_minute", 0))

        # Verifica se está na janela do horário agendado (ex: 21:00 até 21:04) e ainda não enviou hoje
        in_time_window = (
            now_user.hour == target_hour
            and target_min <= now_user.minute <= min(59, target_min + 4)
        )
        already_sent_today = entry.get("last_notified_date") == today_str

        if force_all or (in_time_window and not already_sent_today):
            logger.info(f"Disparando alerta meteorológico agendado para {entry.get('city')} ({sub_id[:10]}...)")
            ok, msg = send_push_to_subscriber(entry, is_test=False)
            if ok:
                entry["last_notified_date"] = today_str
                entry["last_notified_at"] = now_user.strftime("%Y-%m-%d %H:%M:%S")
                sent_count += 1
                changed = True
            elif msg == "EXPIRED":
                expired_keys.append(sub_id)
                changed = True

    for k in expired_keys:
        subs.pop(k, None)

    if changed:
        save_subscriptions(subs)

    return {"checked": len(subs), "sent": sent_count}


def background_scheduler_loop():
    """Loop leve em segundo plano que verifica o relógio a cada 30 segundos."""
    logger.info("Agendador em background iniciado (verificação contínua para envio às 21:00).")
    while True:
        try:
            run_scheduled_notifications_check(force_all=False)
        except Exception as e:
            logger.error(f"Erro no loop do agendador: {e}")
        time.sleep(30)


scheduler_thread = threading.Thread(target=background_scheduler_loop, daemon=True)
scheduler_thread.start()


# =====================================================================
# 6. ROTAS DA APLICAÇÃO E API REST
# =====================================================================
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/sw.js")
def service_worker():
    """Service Worker deve ser servido na raiz '/' para ter escopo total no iOS PWA."""
    response = send_from_directory(STATIC_DIR, "sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/manifest.json")
def manifest():
    return send_from_directory(STATIC_DIR, "manifest.json")


@app.route("/api/vapid-public-key", methods=["GET"])
def api_vapid_public_key():
    return jsonify({"publicKey": VAPID_KEYS["public_key"]})


@app.route("/api/weather", methods=["GET"])
def api_weather():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    city = request.args.get("city", type=str)

    if lat is None or lon is None:
        return jsonify({"error": "Parâmetros lat e lon são obrigatórios."}), 400

    if not city:
        city = reverse_geocode_coords(lat, lon)

    try:
        data = fetch_and_analyze_weather(lat, lon, city)
        return jsonify(data)
    except Exception as e:
        logger.exception("Erro ao buscar previsão meteorológica:")
        return jsonify({"error": f"Não foi possível obter a previsão: {str(e)}"}), 502


@app.route("/api/search-city", methods=["GET"])
def api_search_city():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"results": []})
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": 6, "language": "pt", "format": "json"},
            timeout=6,
        )
        items = r.json().get("results", []) if r.ok else []
        results = []
        for it in items:
            admin1 = it.get("admin1", "")
            country = it.get("country", "")
            label_parts = [it.get("name", "")]
            if admin1:
                label_parts.append(admin1)
            if country:
                label_parts.append(country)
            results.append({
                "name": it.get("name"),
                "display_name": ", ".join(label_parts),
                "lat": it.get("latitude"),
                "lon": it.get("longitude"),
                "timezone": it.get("timezone", "America/Sao_Paulo"),
            })
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    body = request.get_json(force=True) or {}
    subscription = body.get("subscription")
    if not subscription or not subscription.get("endpoint"):
        return jsonify({"error": "Objeto subscription inválido."}), 400

    sub_id = subscription["endpoint"]
    lat = float(body.get("lat", -23.5505))
    lon = float(body.get("lon", -46.6333))
    city = body.get("city") or reverse_geocode_coords(lat, lon)
    timezone = body.get("timezone", "America/Sao_Paulo")
    notify_time = body.get("notify_time", "21:00")

    try:
        nh, nm = [int(x) for x in notify_time.split(":")]
    except Exception:
        nh, nm = 21, 0

    subs = load_subscriptions()
    existing = subs.get(sub_id, {})
    subs[sub_id] = {
        "subscription": subscription,
        "lat": lat,
        "lon": lon,
        "city": city,
        "timezone": timezone,
        "notify_hour": nh,
        "notify_minute": nm,
        "notify_time": f"{nh:02d}:{nm:02d}",
        "enabled": bool(body.get("enabled", True)),
        "updated_at": datetime.now().isoformat(),
        "last_notified_date": existing.get("last_notified_date"),
    }
    save_subscriptions(subs)
    logger.info(f"Inscrição salva/atualizada para {city} às {nh:02d}:{nm:02d}")
    return jsonify({
        "status": "ok",
        "city": city,
        "notify_time": f"{nh:02d}:{nm:02d}",
    })


@app.route("/api/unsubscribe", methods=["POST"])
def api_unsubscribe():
    body = request.get_json(force=True) or {}
    endpoint = body.get("endpoint")
    subs = load_subscriptions()
    if endpoint and endpoint in subs:
        subs.pop(endpoint, None)
        save_subscriptions(subs)
    return jsonify({"status": "ok"})


@app.route("/api/test-notification", methods=["POST"])
def api_test_notification():
    body = request.get_json(force=True) or {}
    subscription = body.get("subscription")
    lat = float(body.get("lat", -23.208))
    lon = float(body.get("lon", -45.9031))
    city = body.get("city") or "Sua Localização"
    preview = body.get("preview")

    if not subscription or not subscription.get("endpoint"):
        return jsonify({"error": "Ative as notificações primeiro antes de testar."}), 400

    temp_entry = {
        "subscription": subscription,
        "lat": lat,
        "lon": lon,
        "city": city,
    }
    ok, msg = send_push_to_subscriber(temp_entry, is_test=True, custom_preview=preview)
    if ok:
        return jsonify({"status": "ok", "message": msg})
    return jsonify({"error": msg}), 500


@app.route("/api/cron/trigger", methods=["GET", "POST"])
def api_cron_trigger():
    """Endpoint para acionamento via cron externo (ex: cron-job.org ou GitHub Actions às 21:00)."""
    force = request.args.get("force", "false").lower() == "true"
    result = run_scheduled_notifications_check(force_all=force)
    return jsonify({"status": "ok", **result})


@app.route("/api/subscriptions-backup", methods=["GET"])
def api_subscriptions_backup():
    """Retorna as inscrições atuais para backup permanente no repositório."""
    return jsonify(load_subscriptions())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Rain Check rodando na porta {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

