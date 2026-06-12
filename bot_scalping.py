import requests
import pandas as pd
import ta
from datetime import datetime, timezone
import time
import json
import os
import yfinance as yf

# ── Configuración ─────────────────────────────────────────────────────────────
TOKEN = "8876856197:AAG4x0X7i61Sfk9rW-22vfftqVQ517Ri-UA"
CHAT_ID = "1482855145"
CHAT_ID_AMIGO = "7611216982"
NOTION_TOKEN = "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"
NOTION_FONDEO_DB_ID = "3799d658-98f4-8053-9868-f003b846e5d7"
ESTADO_FILE = "estado_turtle.json"

SYMBOL = "LINK-USD"
MARGEN = 1000
APALANCAMIENTO = 50
POSICION = MARGEN * APALANCAMIENTO  # $50,000
TP_PCT = 0.01
SL_PCT = 0.03
COMISION = POSICION * 0.0011

# Horario de sueño UTC (23:00-07:00 AR = 02:00-10:00 UTC)
HORA_INICIO_SUENO = 2
HORA_FIN_SUENO = 10

# ── Estado ────────────────────────────────────────────────────────────────────
en_operacion = False
precio_entrada = 0
precio_tp = 0
precio_sl = 0
direccion = None
esperando_confirmacion = False
ultimo_update_id = None
banda_inf_tocada_5m = False
banda_sup_tocada_5m = False
ciclos_esperando = 0
CICLOS_MAX_ESPERA = 6  # 3 minutos (6 x 30s)

def guardar_estado():
    estado = {
        "en_operacion": en_operacion,
        "precio_entrada": precio_entrada,
        "precio_tp": precio_tp,
        "precio_sl": precio_sl,
        "direccion": direccion,
        "esperando_confirmacion": esperando_confirmacion,
        "ultimo_update_id": ultimo_update_id,
        "ciclos_esperando": ciclos_esperando
    }
    with open(ESTADO_FILE, "w") as f:
        json.dump(estado, f)

def cargar_estado():
    global en_operacion, precio_entrada, precio_tp, precio_sl
    global direccion, esperando_confirmacion, ultimo_update_id, ciclos_esperando
    if not os.path.exists(ESTADO_FILE):
        return
    try:
        with open(ESTADO_FILE, "r") as f:
            estado = json.load(f)
        en_operacion           = estado.get("en_operacion", False)
        precio_entrada         = estado.get("precio_entrada", 0)
        precio_tp              = estado.get("precio_tp", 0)
        precio_sl              = estado.get("precio_sl", 0)
        direccion              = estado.get("direccion", None)
        esperando_confirmacion = estado.get("esperando_confirmacion", False)
        ultimo_update_id       = estado.get("ultimo_update_id", None)
        ciclos_esperando       = estado.get("ciclos_esperando", 0)
        if en_operacion:
            enviar_mensaje(f"🔄 Bot reiniciado con operación abierta\n{direccion} a ${precio_entrada:.4f}\nTP: ${precio_tp:.4f} | SL: ${precio_sl:.4f}")
        elif esperando_confirmacion:
            esperando_confirmacion = False
            ciclos_esperando = 0
            guardar_estado()
            enviar_mensaje("🔄 Bot reiniciado — señal pendiente cancelada")
        else:
            enviar_mensaje("🤖 Bot Turtle iniciado — sin operación abierta")
    except Exception as e:
        enviar_mensaje(f"⚠️ Error cargando estado: {str(e)}")

# ── Telegram ──────────────────────────────────────────────────────────────────
def enviar_mensaje(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for chat in [CHAT_ID, CHAT_ID_AMIGO]:
        params = {"chat_id": chat, "text": texto}
        try:
            requests.get(url, params=params)
        except:
            pass

def obtener_ultimo_mensaje():
    global ultimo_update_id
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"timeout": 1, "offset": ultimo_update_id}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data["ok"] and data["result"]:
            for update in data["result"]:
                ultimo_update_id = update["update_id"] + 1
                if "message" in update and "text" in update["message"]:
                    if str(update["message"]["chat"]["id"]) == CHAT_ID:
                        return update["message"]["text"].lower().strip()
    except:
        pass
    return None

# ── Notion ────────────────────────────────────────────────────────────────────
def registrar_operacion(resultado, p_entrada, p_salida, porcentaje, ganancia_dolares):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "parent": {"database_id": NOTION_FONDEO_DB_ID},
        "properties": {
            "Nombre": {"title": [{"text": {"content": f"LINK Turtle - {datetime.now().strftime('%d/%m/%Y %H:%M')}"}}]},
            "PLATAFORMA": {"select": {"name": "Fondeo"}},
            "Resultado": {"select": {"name": resultado}},
            "Precio de entradsa": {"number": p_entrada},
            "Precio de salida": {"number": p_salida},
            "Porcentaje": {"number": porcentaje},
            "Ganacia/ Perdida": {"number": ganancia_dolares},
            "Fecha": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}}
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        return response.status_code
    except:
        return 0

# ── Descarga de datos ─────────────────────────────────────────────────────────
def get_data(interval, period):
    try:
        data = yf.download(SYMBOL, period=period, interval=interval, progress=False)
        if data is None or len(data) < 20:
            return None
        data = data[['Close', 'High', 'Low', 'Open', 'Volume']]
        data.columns = ['close', 'high', 'low', 'open', 'volume']
        close = data['close']
        data['rsi'] = ta.momentum.RSIIndicator(close, window=14).rsi()
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0)
        data['bb_inf'] = bb.bollinger_lband()
        data['bb_sup'] = bb.bollinger_hband()
        result = data.dropna()
        if len(result) < 2:
            return None
        return result
    except Exception as e:
        return None

# ── Detección de fakeout ──────────────────────────────────────────────────────
def detectar_fakeout(data, i):
    if i < 1:
        return None
    high_ant  = float(data['high'].iloc[i-1])
    low_ant   = float(data['low'].iloc[i-1])
    high_act  = float(data['high'].iloc[i])
    low_act   = float(data['low'].iloc[i])
    close_act = float(data['close'].iloc[i])
    if high_act > high_ant and close_act < high_ant:
        return 'SHORT'
    elif low_act < low_ant and close_act > low_ant:
        return 'LONG'
    return None

def get_contexto(data):
    if data is None or len(data) < 2:
        return None
    return detectar_fakeout(data, len(data) - 1)

# ── Lógica principal ──────────────────────────────────────────────────────────
def verificar_senal():
    global en_operacion, precio_entrada, precio_tp, precio_sl
    global direccion, esperando_confirmacion
    global banda_inf_tocada_5m, banda_sup_tocada_5m, ciclos_esperando

    try:
        # Verificar horario de sueño
        hora_utc = datetime.now(timezone.utc).hour
        dormido = HORA_INICIO_SUENO <= hora_utc < HORA_FIN_SUENO

        # Descargar datos
        df_4h  = get_data("4h",  "60d")
        df_1h  = get_data("1h",  "7d")
        df_15m = get_data("15m", "5d")
        df_5m  = get_data("5m",  "2d")

        if df_5m is None:
            enviar_mensaje("⚠️ Error descargando datos de 5m")
            return

        # Contextos
        ctx_4h  = get_contexto(df_4h)
        ctx_1h  = get_contexto(df_1h)
        ctx_15m = get_contexto(df_15m)

        # Datos actuales 5m
        precio_actual = float(df_5m['close'].iloc[-1])
        rsi_actual    = float(df_5m['rsi'].iloc[-1])
        rsi_anterior  = float(df_5m['rsi'].iloc[-2])
        bb_inf        = float(df_5m['bb_inf'].iloc[-1])
        bb_sup        = float(df_5m['bb_sup'].iloc[-1])

        if precio_actual <= bb_inf:
            banda_inf_tocada_5m = True
        if precio_actual >= bb_sup:
            banda_sup_tocada_5m = True

        # ── Salida ────────────────────────────────────────────────────────
        if en_operacion:
            if direccion == 'LONG' and precio_actual >= precio_tp:
                porcentaje = ((precio_tp - precio_entrada) / precio_entrada) * 100
                ganancia = round(POSICION * porcentaje / 100 - COMISION, 2)
                en_operacion = False
                guardar_estado()
                enviar_mensaje(f"✅ SALIDA LONG — TP\nEntrada: ${precio_entrada:.4f} | Salida: ${precio_tp:.4f}\n{porcentaje:.2f}% | ${ganancia:.2f}\n⚡ Cerrar posición AHORA")
                registrar_operacion("TP", precio_entrada, precio_tp, round(porcentaje, 2), ganancia)

            elif direccion == 'LONG' and precio_actual <= precio_sl:
                porcentaje = ((precio_sl - precio_entrada) / precio_entrada) * 100
                ganancia = round(POSICION * porcentaje / 100 - COMISION, 2)
                en_operacion = False
                guardar_estado()
                enviar_mensaje(f"❌ SALIDA LONG — SL\nEntrada: ${precio_entrada:.4f} | Salida: ${precio_sl:.4f}\n{porcentaje:.2f}% | ${ganancia:.2f}\n⚡ Cerrar posición AHORA")
                registrar_operacion("SL", precio_entrada, precio_sl, round(porcentaje, 2), ganancia)

            elif direccion == 'SHORT' and precio_actual <= precio_tp:
                porcentaje = ((precio_entrada - precio_tp) / precio_entrada) * 100
                ganancia = round(POSICION * porcentaje / 100 - COMISION, 2)
                en_operacion = False
                guardar_estado()
                enviar_mensaje(f"✅ SALIDA SHORT — TP\nEntrada: ${precio_entrada:.4f} | Salida: ${precio_tp:.4f}\n{porcentaje:.2f}% | ${ganancia:.2f}\n⚡ Cerrar posición AHORA")
                registrar_operacion("TP", precio_entrada, precio_tp, round(porcentaje, 2), ganancia)

            elif direccion == 'SHORT' and precio_actual >= precio_sl:
                porcentaje = ((precio_entrada - precio_sl) / precio_entrada) * 100
                ganancia = round(POSICION * porcentaje / 100 - COMISION, 2)
                en_operacion = False
                guardar_estado()
                enviar_mensaje(f"❌ SALIDA SHORT — SL\nEntrada: ${precio_entrada:.4f} | Salida: ${precio_sl:.4f}\n{porcentaje:.2f}% | ${ganancia:.2f}\n⚡ Cerrar posición AHORA")
                registrar_operacion("SL", precio_entrada, precio_sl, round(porcentaje, 2), ganancia)
            return

        # ── Confirmación pendiente ────────────────────────────────────────
        if esperando_confirmacion:
            mensaje = obtener_ultimo_mensaje()
            if mensaje == "si":
                esperando_confirmacion = False
                ciclos_esperando = 0
                en_operacion = True
                guardar_estado()
                dir_txt = "LONG 📈" if direccion == 'LONG' else "SHORT 📉"
                enviar_mensaje(
                    f"🟢 ENTRADA CONFIRMADA — {dir_txt}\n"
                    f"Precio: ${precio_entrada:.4f}\n"
                    f"TP: ${precio_tp:.4f} | SL: ${precio_sl:.4f}\n"
                    f"⚡ Entrar con $1,000 margen 50x en Bybit"
                )
            else:
                ciclos_esperando += 1
                guardar_estado()
                if ciclos_esperando >= CICLOS_MAX_ESPERA:
                    esperando_confirmacion = False
                    ciclos_esperando = 0
                    guardar_estado()
                    enviar_mensaje("⏱️ Señal cancelada por tiempo (3 min sin respuesta)")
            return

        # ── No operar si está durmiendo ───────────────────────────────────
        if dormido:
            return

        # ── Verificar confluencia ─────────────────────────────────────────
        confluencia = (ctx_4h is not None and
                       ctx_1h is not None and
                       ctx_15m is not None and
                       ctx_4h == ctx_1h == ctx_15m)

        if not confluencia:
            # Alerta temprana — 2 de 3 alineados
            ctxs = [c for c in [ctx_4h, ctx_1h, ctx_15m] if c is not None]
            if len(ctxs) == 2 and ctxs[0] == ctxs[1]:
                dir_alerta = ctxs[0]
                banda_ok = (dir_alerta == 'LONG' and banda_inf_tocada_5m) or \
                           (dir_alerta == 'SHORT' and banda_sup_tocada_5m)
                if banda_ok:
                    enviar_mensaje(
                        f"⚠️ ALERTA TEMPRANA — {dir_alerta}\n"
                        f"2 de 3 timeframes alineados\n"
                        f"Prepará Bybit, señal próxima"
                    )
            return

        dir_ctx = ctx_4h

        # ── Señal LONG ────────────────────────────────────────────────────
        if dir_ctx == 'LONG' and not en_operacion:
            if rsi_anterior <= 30 and rsi_actual > 30 and banda_inf_tocada_5m:
                precio_entrada = precio_actual
                precio_tp      = precio_entrada * (1 + TP_PCT)
                precio_sl      = precio_entrada * (1 - SL_PCT)
                direccion      = 'LONG'
                esperando_confirmacion = True
                ciclos_esperando = 0
                banda_inf_tocada_5m = False
                guardar_estado()
                enviar_mensaje(
                    f"🟢 SEÑAL LONG — Triple Turtle Soap 📈\n"
                    f"4H: {ctx_4h} | 1H: {ctx_1h} | 15m: {ctx_15m}\n"
                    f"Precio: ${precio_entrada:.4f}\n"
                    f"TP: ${precio_tp:.4f} (+1%)\n"
                    f"SL: ${precio_sl:.4f} (-3%)\n"
                    f"⚡ Respondé 'si' para confirmar (3 min)"
                )

        # ── Señal SHORT ───────────────────────────────────────────────────
        elif dir_ctx == 'SHORT' and not en_operacion:
            if rsi_anterior >= 70 and rsi_actual < 70 and banda_sup_tocada_5m:
                precio_entrada = precio_actual
                precio_tp      = precio_entrada * (1 - TP_PCT)
                precio_sl      = precio_entrada * (1 + SL_PCT)
                direccion      = 'SHORT'
                esperando_confirmacion = True
                ciclos_esperando = 0
                banda_sup_tocada_5m = False
                guardar_estado()
                enviar_mensaje(
                    f"🔴 SEÑAL SHORT — Triple Turtle Soap 📉\n"
                    f"4H: {ctx_4h} | 1H: {ctx_1h} | 15m: {ctx_15m}\n"
                    f"Precio: ${precio_entrada:.4f}\n"
                    f"TP: ${precio_tp:.4f} (-1%)\n"
                    f"SL: ${precio_sl:.4f} (+3%)\n"
                    f"⚡ Respondé 'si' para confirmar (3 min)"
                )

    except Exception as e:
        enviar_mensaje(f"⚠️ Error bot scalping: {str(e)}")

# ── Arranque ──────────────────────────────────────────────────────────────────
obtener_ultimo_mensaje()
cargar_estado()

while True:
    now = datetime.now()
    print(f"{now.strftime('%H:%M:%S')} - Turtle verificando...")
    verificar_senal()
    time.sleep(30)
