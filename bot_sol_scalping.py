import requests
import yfinance as yf
import pandas as pd
import ta
import time
import json
import os
from datetime import datetime

TOKEN = "8876856197:AAG4x0X7i61Sfk9rW-22vfftqVQ517Ri-UA"
CHAT_ID = "1482855145"
CHAT_ID_AMIGO = "7611216982"
NOTION_TOKEN = "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"
NOTION_FONDEO_DB_ID = "3799d658-98f4-8053-9868-f003b846e5d7"
ESTADO_FILE = "estado_sol_scalping.json"

SYMBOL = "SOL-USD"
TRADING_POWER = 6000
POSICION = TRADING_POWER * 0.30  # $1,800

HORA_INICIO_SUENO = 2
HORA_FIN_SUENO = 10

en_operacion = False
precio_entrada = 0
direccion = None
esperando_confirmacion = False
ultimo_update_id = None
banda_inf_tocada = False
banda_sup_tocada = False
ciclos_esperando = 0
alerta_temprana_ctx = None
CICLOS_MAX_ESPERA = 3

def guardar_estado():
    estado = {
        "en_operacion": en_operacion,
        "precio_entrada": precio_entrada,
        "direccion": direccion,
        "esperando_confirmacion": esperando_confirmacion,
        "ultimo_update_id": ultimo_update_id,
        "ciclos_esperando": ciclos_esperando,
        "alerta_temprana_ctx": alerta_temprana_ctx
    }
    with open(ESTADO_FILE, "w") as f:
        json.dump(estado, f)

def cargar_estado():
    global en_operacion, precio_entrada, direccion
    global esperando_confirmacion, ultimo_update_id
    global ciclos_esperando, alerta_temprana_ctx
    if not os.path.exists(ESTADO_FILE):
        return
    try:
        with open(ESTADO_FILE, "r") as f:
            estado = json.load(f)
        en_operacion           = estado.get("en_operacion", False)
        precio_entrada         = estado.get("precio_entrada", 0)
        direccion              = estado.get("direccion", None)
        esperando_confirmacion = estado.get("esperando_confirmacion", False)
        ultimo_update_id       = estado.get("ultimo_update_id", None)
        ciclos_esperando       = estado.get("ciclos_esperando", 0)
        alerta_temprana_ctx    = estado.get("alerta_temprana_ctx", None)
        if en_operacion:
            enviar_mensaje(f"🔄 Bot SOL reiniciado con operación abierta\n{direccion} desde ${precio_entrada:.4f}")
        elif esperando_confirmacion:
            esperando_confirmacion = False
            ciclos_esperando = 0
            guardar_estado()
            enviar_mensaje("🔄 Bot SOL reiniciado — señal pendiente cancelada")
        else:
            enviar_mensaje("⚡ Bot Scalping SOL iniciado\n1H+15m+5m → 1m | Posición $1,800")
    except Exception as e:
        enviar_mensaje(f"⚠️ Error cargando estado SOL: {str(e)}")

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
            "Nombre": {"title": [{"text": {"content": f"SOL Scalping - {datetime.now().strftime('%d/%m/%Y %H:%M')}"}}]},
            "PLATAFORMA": {"select": {"name": "Quantfury SOL"}},
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
    except:
        return None

def get_contexto(data):
    if data is None or len(data) < 2:
        return None
    high_ant  = float(data['high'].iloc[-2])
    low_ant   = float(data['low'].iloc[-2])
    high_act  = float(data['high'].iloc[-1])
    low_act   = float(data['low'].iloc[-1])
    close_act = float(data['close'].iloc[-1])
    if high_act > high_ant and close_act < high_ant:
        return 'SHORT'
    elif low_act < low_ant and close_act > low_ant:
        return 'LONG'
    return None

def verificar_senal():
    global en_operacion, precio_entrada, direccion
    global esperando_confirmacion, ciclos_esperando
    global banda_inf_tocada, banda_sup_tocada, alerta_temprana_ctx

    try:
        hora_utc = datetime.utcnow().hour
        dormido = HORA_INICIO_SUENO <= hora_utc < HORA_FIN_SUENO

        df_1h  = get_data("1h",  "7d")
        df_15m = get_data("15m", "5d")
        df_5m  = get_data("5m",  "2d")
        df_1m  = get_data("1m",  "1d")

        if df_1m is None:
            return

        ctx_1h  = get_contexto(df_1h)
        ctx_15m = get_contexto(df_15m)
        ctx_5m  = get_contexto(df_5m)

        precio_actual   = float(df_1m['close'].iloc[-1])
        rsi_actual      = float(df_1m['rsi'].iloc[-1])
        rsi_anterior    = float(df_1m['rsi'].iloc[-2])
        precio_anterior = float(df_1m['close'].iloc[-2])
        bb_inf          = float(df_1m['bb_inf'].iloc[-1])
        bb_sup          = float(df_1m['bb_sup'].iloc[-1])
        bb_inf_ant      = float(df_1m['bb_inf'].iloc[-2])
        bb_sup_ant      = float(df_1m['bb_sup'].iloc[-2])

        if precio_actual <= bb_inf:
            banda_inf_tocada = True
        if precio_actual >= bb_sup:
            banda_sup_tocada = True

        # Salida natural
        if en_operacion:
            if direccion == 'LONG':
                if rsi_anterior >= 70 and precio_anterior >= bb_sup_ant:
                    porcentaje = ((precio_actual - precio_entrada) / precio_entrada) * 100
                    resultado = "TP" if porcentaje > 0 else "SL"
                    ganancia = round(POSICION * porcentaje / 100, 2)
                    en_operacion = False
                    alerta_temprana_ctx = None
                    guardar_estado()
                    enviar_mensaje(
                        f"{'✅' if resultado=='TP' else '❌'} SALIDA LONG — {resultado} SOL\n"
                        f"Entrada: ${precio_entrada:.4f} | Salida: ${precio_actual:.4f}\n"
                        f"{porcentaje:.2f}% | ${ganancia:.2f}\n"
                        f"⚡ Cerrar posición SOL en Quantfury AHORA"
                    )
                    registrar_operacion(resultado, precio_entrada, precio_actual,
                                       round(porcentaje, 2), ganancia)
            elif direccion == 'SHORT':
                if rsi_anterior <= 30 and precio_anterior <= bb_inf_ant:
                    porcentaje = ((precio_entrada - precio_actual) / precio_entrada) * 100
                    resultado = "TP" if porcentaje > 0 else "SL"
                    ganancia = round(POSICION * porcentaje / 100, 2)
                    en_operacion = False
                    alerta_temprana_ctx = None
                    guardar_estado()
                    enviar_mensaje(
                        f"{'✅' if resultado=='TP' else '❌'} SALIDA SHORT — {resultado} SOL\n"
                        f"Entrada: ${precio_entrada:.4f} | Salida: ${precio_actual:.4f}\n"
                        f"{porcentaje:.2f}% | ${ganancia:.2f}\n"
                        f"⚡ Cerrar posición SOL en Quantfury AHORA"
                    )
                    registrar_operacion(resultado, precio_entrada, precio_actual,
                                       round(porcentaje, 2), ganancia)
            return

        # Confirmación pendiente
        if esperando_confirmacion:
            mensaje = obtener_ultimo_mensaje()
            if mensaje == "si":
                esperando_confirmacion = False
                ciclos_esperando = 0
                en_operacion = True
                alerta_temprana_ctx = None
                guardar_estado()
                dir_txt = "LONG 📈" if direccion == 'LONG' else "SHORT 📉"
                enviar_mensaje(
                    f"🟢 ENTRADA CONFIRMADA — {dir_txt} SOL\n"
                    f"Precio: ${precio_entrada:.4f}\n"
                    f"Posición: $1,800 (30% de $6,000 TP)\n"
                    f"⚡ Entrar en SOL en Quantfury AHORA\n"
                    f"Salida: natural (RSI+Bollinger en 1m)"
                )
            else:
                ciclos_esperando += 1
                guardar_estado()
                if ciclos_esperando >= CICLOS_MAX_ESPERA:
                    esperando_confirmacion = False
                    ciclos_esperando = 0
                    alerta_temprana_ctx = None
                    guardar_estado()
                    enviar_mensaje("⏱️ Señal SOL cancelada por tiempo")
            return

        if dormido:
            return

        # Verificar confluencia 1H+15m+5m
        confluencia = (ctx_1h  is not None and
                       ctx_15m is not None and
                       ctx_5m  is not None and
                       ctx_1h == ctx_15m == ctx_5m)

        if not confluencia:
            alerta_temprana_ctx = None
            guardar_estado()
            return

        dir_ctx = ctx_1h

        # Alerta temprana
        banda_tocada = (dir_ctx == 'LONG' and banda_inf_tocada) or \
                       (dir_ctx == 'SHORT' and banda_sup_tocada)

        if banda_tocada and alerta_temprana_ctx != dir_ctx:
            alerta_temprana_ctx = dir_ctx
            guardar_estado()
            banda_txt = "banda inferior" if dir_ctx == 'LONG' else "banda superior"
            enviar_mensaje(
                f"⚠️ ALERTA SOL — {dir_ctx} {'📈' if dir_ctx=='LONG' else '📉'}\n"
                f"1H+15m+5m alineados\n"
                f"Precio tocó {banda_txt} en 1m\n"
                f"Esperá cruce del RSI — prepará Quantfury SOL"
            )

        # Señal LONG
        if dir_ctx == 'LONG' and not en_operacion:
            if rsi_anterior <= 30 and rsi_actual > 30 and banda_inf_tocada:
                precio_entrada   = precio_actual
                direccion        = 'LONG'
                esperando_confirmacion = True
                ciclos_esperando = 0
                banda_inf_tocada = False
                alerta_temprana_ctx = None
                guardar_estado()
                enviar_mensaje(
                    f"🟢 SEÑAL LONG — SOL Scalping 📈\n"
                    f"1H: {ctx_1h} | 15m: {ctx_15m} | 5m: {ctx_5m}\n"
                    f"Precio: ${precio_entrada:.4f}\n"
                    f"Posición: $1,800 | Salida natural\n"
                    f"⚡ Respondé 'si' para confirmar (3 min)"
                )

        # Señal SHORT
        elif dir_ctx == 'SHORT' and not en_operacion:
            if rsi_anterior >= 70 and rsi_actual < 70 and banda_sup_tocada:
                precio_entrada   = precio_actual
                direccion        = 'SHORT'
                esperando_confirmacion = True
                ciclos_esperando = 0
                banda_sup_tocada = False
                alerta_temprana_ctx = None
                guardar_estado()
                enviar_mensaje(
                    f"🔴 SEÑAL SHORT — SOL Scalping 📉\n"
                    f"1H: {ctx_1h} | 15m: {ctx_15m} | 5m: {ctx_5m}\n"
                    f"Precio: ${precio_entrada:.4f}\n"
                    f"Posición: $1,800 | Salida natural\n"
                    f"⚡ Respondé 'si' para confirmar (3 min)"
                )

    except Exception as e:
        enviar_mensaje(f"⚠️ Error bot SOL: {str(e)}")

obtener_ultimo_mensaje()
cargar_estado()

while True:
    now = datetime.now()
    print(f"{now.strftime('%H:%M:%S')} - SOL verificando...")
    verificar_senal()
    time.sleep(30)
