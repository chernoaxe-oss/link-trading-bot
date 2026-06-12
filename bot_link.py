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
ESTADO_FILE = "estado_link.json"

# Horario de sueño UTC (23:00-07:00 AR = 02:00-10:00 UTC)
HORA_INICIO_SUENO = 2
HORA_FIN_SUENO = 10

alerta_long_ts = None
entrada_enviada_ts = None
salida_enviada_ts = None
en_operacion = False
precio_entrada = 0
esperando_confirmacion = False
alerta_ts_pendiente = None
ultimo_update_id = None
banda_inf_tocada_ts = None

def guardar_estado():
    estado = {
        "en_operacion": en_operacion,
        "precio_entrada": precio_entrada,
        "esperando_confirmacion": esperando_confirmacion,
        "banda_inf_tocada_ts": str(banda_inf_tocada_ts) if banda_inf_tocada_ts is not None else None,
        "alerta_ts_pendiente": str(alerta_ts_pendiente) if alerta_ts_pendiente is not None else None,
        "entrada_enviada_ts": str(entrada_enviada_ts) if entrada_enviada_ts is not None else None,
        "salida_enviada_ts": str(salida_enviada_ts) if salida_enviada_ts is not None else None,
        "ultimo_update_id": ultimo_update_id,
    }
    with open(ESTADO_FILE, "w") as f:
        json.dump(estado, f)

def cargar_estado():
    global en_operacion, precio_entrada, esperando_confirmacion
    global banda_inf_tocada_ts, alerta_ts_pendiente
    global entrada_enviada_ts, salida_enviada_ts, ultimo_update_id

    if not os.path.exists(ESTADO_FILE):
        return

    try:
        with open(ESTADO_FILE, "r") as f:
            estado = json.load(f)

        en_operacion = estado.get("en_operacion", False)
        precio_entrada = estado.get("precio_entrada", 0)
        esperando_confirmacion = estado.get("esperando_confirmacion", False)
        ultimo_update_id = estado.get("ultimo_update_id", None)
        banda_inf_tocada_ts = estado.get("banda_inf_tocada_ts", None)
        alerta_ts_pendiente = estado.get("alerta_ts_pendiente", None)
        entrada_enviada_ts = estado.get("entrada_enviada_ts", None)
        salida_enviada_ts = estado.get("salida_enviada_ts", None)

        if en_operacion:
            enviar_mensaje(f"🔄 Bot reiniciado con operación abierta\nPrecio de entrada: ${precio_entrada:.4f}\nMonitoreando salida...")
        elif esperando_confirmacion:
            esperando_confirmacion = False
            alerta_ts_pendiente = None
            guardar_estado()
            enviar_mensaje("🔄 Bot reiniciado — señal pendiente cancelada, esperando nueva oportunidad")
        else:
            enviar_mensaje("🔄 Bot actualizado con filtro de horario de sueño")

    except Exception as e:
        enviar_mensaje(f"⚠️ Error cargando estado: {str(e)}")

def enviar_mensaje(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for chat in [CHAT_ID, CHAT_ID_AMIGO]:
        params = {"chat_id": chat, "text": texto}
        requests.get(url, params=params)

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

def registrar_operacion(resultado, p_entrada, p_salida, porcentaje, ganancia_dolares, plataforma):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "parent": {"database_id": NOTION_FONDEO_DB_ID},
        "properties": {
            "Nombre": {"title": [{"text": {"content": f"LINK - {datetime.now().strftime('%d/%m/%Y %H:%M')}"}}]},
            "PLATAFORMA": {"select": {"name": plataforma}},
            "Resultado": {"select": {"name": resultado}},
            "Precio de entradsa": {"number": p_entrada},
            "Precio de salida": {"number": p_salida},
            "Porcentaje": {"number": porcentaje},
            "Ganacia/ Perdida": {"number": ganancia_dolares},
            "Fecha": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}}
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.status_code

def verificar_senal():
    global alerta_long_ts, entrada_enviada_ts, salida_enviada_ts
    global en_operacion, precio_entrada
    global esperando_confirmacion, alerta_ts_pendiente
    global banda_inf_tocada_ts

    try:
        # Verificar horario de sueño
        hora_utc = datetime.utcnow().hour
        dormido = HORA_INICIO_SUENO <= hora_utc < HORA_FIN_SUENO

        data = yf.download("LINK-USD", period="5d", interval="15m", progress=False)
        data = data[['Close', 'High', 'Low', 'Open', 'Volume']]
        data.columns = ['Close', 'High', 'Low', 'Open', 'Volume']
        close = data['Close']

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0)

        ts_actual = str(data.index[-1])
        rsi_actual = float(rsi.iloc[-1])
        precio_actual = float(close.iloc[-1])
        banda_inf_actual = float(bb.bollinger_lband().iloc[-1])

        rsi_anterior = float(rsi.iloc[-2])
        precio_anterior = float(close.iloc[-2])
        banda_sup_anterior = float(bb.bollinger_hband().iloc[-2])
        ts_anterior = str(data.index[-2])

        if precio_actual <= banda_inf_actual:
            banda_inf_tocada_ts = ts_actual
            guardar_estado()

        if esperando_confirmacion:
            mensaje_usuario = obtener_ultimo_mensaje()
            if mensaje_usuario == "si":
                esperando_confirmacion = False
                precio_entrada = precio_actual
                en_operacion = True
                salida_enviada_ts = None
                guardar_estado()
                mensaje = f"🟢 ENTRADA CONFIRMADA - LONG 📈\n"
                mensaje += f"Precio de entrada: ${precio_entrada:.4f}\n"
                mensaje += f"⚡ Entrar con 30% del Trading Power en Quantfury"
                enviar_mensaje(mensaje)
                return
            elif ts_actual != alerta_ts_pendiente and ts_anterior != alerta_ts_pendiente:
                esperando_confirmacion = False
                alerta_ts_pendiente = None
                guardar_estado()

        # Salida — siempre activa aunque esté durmiendo
        if en_operacion and salida_enviada_ts != ts_anterior:
            if rsi_anterior >= 70 and precio_anterior >= banda_sup_anterior:
                precio_salida = precio_actual
                porcentaje = ((precio_salida - precio_entrada) / precio_entrada) * 100
                resultado = "TP" if porcentaje > 0 else "SL"
                ganancia_dolares = round(50000 * porcentaje / 100, 2)
                en_operacion = False
                salida_enviada_ts = ts_anterior
                banda_inf_tocada_ts = None
                guardar_estado()

                mensaje = f"🔴 SALIDA LONG - {resultado}\n"
                mensaje += f"Entrada: ${precio_entrada:.4f} | Salida: ${precio_salida:.4f}\n"
                mensaje += f"Resultado: {porcentaje:.2f}% | Fondeo: ${ganancia_dolares:.2f}\n"
                mensaje += f"⚡ Cerrar posicion AHORA"
                enviar_mensaje(mensaje)

                status = registrar_operacion(resultado, precio_entrada, precio_salida,
                                             round(porcentaje, 2), ganancia_dolares, "Quantfury")
                if status == 200:
                    enviar_mensaje(f"✅ Operacion registrada en Notion")
                else:
                    enviar_mensaje(f"⚠️ Error Notion: {status}")
                return

        # Entradas — solo si no está durmiendo
        if dormido:
            return

        if not en_operacion and not esperando_confirmacion:
            if precio_actual <= banda_inf_actual and rsi_actual <= 30:
                if alerta_long_ts != ts_actual:
                    mensaje = f"⚠️ ALERTA TEMPRANA - LONG 📈\n"
                    mensaje += f"RSI: {rsi_actual:.2f} tocó 30\n"
                    mensaje += f"Precio: ${precio_actual:.4f} tocó banda inferior\n"
                    mensaje += f"Esperá que el RSI cruce hacia arriba para entrar"
                    enviar_mensaje(mensaje)
                    alerta_long_ts = ts_actual

            if rsi_anterior <= 30 and rsi_actual > 30 and banda_inf_tocada_ts is not None:
                if entrada_enviada_ts != ts_actual:
                    esperando_confirmacion = True
                    alerta_ts_pendiente = ts_actual
                    entrada_enviada_ts = ts_actual
                    guardar_estado()
                    mensaje = f"🟢 SEÑAL ENTRADA LONG 📈\n"
                    mensaje += f"RSI cruzó hacia arriba 30\n"
                    mensaje += f"RSI: {rsi_anterior:.2f} → {rsi_actual:.2f}\n"
                    mensaje += f"Precio: ${precio_actual:.4f}\n"
                    mensaje += f"Respondé 'si' para confirmar entrada"
                    enviar_mensaje(mensaje)

    except Exception as e:
        enviar_mensaje(f"⚠️ Error: {str(e)}")

obtener_ultimo_mensaje()
cargar_estado()

while True:
    now = datetime.now()
    print(f"{now.strftime('%H:%M:%S')} - Verificando...")
    verificar_senal()
    time.sleep(60)
