import requests
import yfinance as yf
import pandas as pd
import ta
import time
from datetime import datetime

TOKEN = "8876856197:AAEtpTiDK4zlgoCYvGv09Tzl1L9B9s3bWAc"
CHAT_ID = "1482855145"
CHAT_ID_AMIGO = "7611216982"
NOTION_TOKEN = "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"
NOTION_DB_ID = "33f9d65898f4808dbe28e21c1cf69379"
NOTION_FONDEO_DB_ID = "3799d65898f480539868f003b846e5d7"

alerta_enviada_ts = None
entrada_enviada_ts = None
salida_enviada_ts = None
en_operacion = False
precio_entrada = 0
direccion_actual = None
esperando_confirmacion = False
alerta_ts_pendiente = None
ultimo_update_id = None

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

def registrar_en_notion(resultado, porcentaje, total_real):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "Aa": {"title": [{"text": {"content": "LINK Scalping"}}]},
            "RESULTADO": {"select": {"name": resultado}},
            "PORCENTAJE": {"number": porcentaje},
            "Fecha": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
            "TOTAL REAL": {"number": total_real}
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.status_code

def registrar_en_notion_fondeo(resultado, p_entrada, p_salida, porcentaje, ganancia_dolares, balance):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "parent": {"database_id": NOTION_FONDEO_DB_ID},
        "properties": {
            "Nombre": {"title": [{"text": {"content": f"LINK Scalping - {datetime.now().strftime('%d/%m/%Y %H:%M')}"}}]},
            "Cuenta": {"select": {"name": "Cuenta 1"}},
            "Fase": {"select": {"name": "Fase 1"}},
            "Resultado": {"select": {"name": resultado}},
            "Precio entrada": {"number": p_entrada},
            "Precio salida": {"number": p_salida},
            "Porcentaje": {"number": porcentaje},
            "Ganancia/Perdida": {"number": ganancia_dolares},
            "Balance cuenta": {"number": balance},
            "Fecha": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}}
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.status_code

def verificar_senal():
    global alerta_enviada_ts, entrada_enviada_ts, salida_enviada_ts
    global en_operacion, precio_entrada, direccion_actual
    global esperando_confirmacion, alerta_ts_pendiente

    try:
        data = yf.download("LINK-USD", period="1d", interval="1m", progress=False)
        data = data[['Close', 'High', 'Low', 'Open', 'Volume']]
        data.columns = ['Close', 'High', 'Low', 'Open', 'Volume']
        close = data['Close']

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0)

        ts_actual = data.index[-1]
        rsi_actual = float(rsi.iloc[-1])
        precio_actual = float(close.iloc[-1])
        banda_inf_actual = float(bb.bollinger_lband().iloc[-1])
        banda_sup_actual = float(bb.bollinger_hband().iloc[-1])

        ts_anterior = data.index[-2]
        rsi_anterior = float(rsi.iloc[-2])
        precio_anterior = float(close.iloc[-2])
        banda_inf_anterior = float(bb.bollinger_lband().iloc[-2])
        banda_sup_anterior = float(bb.bollinger_hband().iloc[-2])

        if esperando_confirmacion:
            mensaje_usuario = obtener_ultimo_mensaje()
            if mensaje_usuario == "si":
                esperando_confirmacion = False
                precio_entrada = precio_actual
                en_operacion = True
                salida_enviada_ts = None
                tipo = "LONG 📈" if direccion_actual == "long" else "SHORT 📉"
                mensaje = f"🟢 ENTRADA SCALPING - {tipo}\n"
                mensaje += f"Precio: ${precio_entrada:.4f}\n"
                mensaje += f"⚡ Entrar con 50x en Bybit"
                enviar_mensaje(mensaje)
                return
            elif ts_actual != alerta_ts_pendiente and ts_anterior != alerta_ts_pendiente:
                esperando_confirmacion = False
                alerta_ts_pendiente = None
                direccion_actual = None

        if not en_operacion and not esperando_confirmacion:
            if rsi_actual < 30 and precio_actual <= banda_inf_actual:
                if alerta_enviada_ts != ts_actual:
                    mensaje = f"⚠️ SCALPING - LONG 📈\n"
                    mensaje += f"RSI: {rsi_actual:.2f} | Precio: ${precio_actual:.4f}\n"
                    mensaje += f"Respondé 'si' para entrar"
                    enviar_mensaje(mensaje)
                    alerta_enviada_ts = ts_actual
                    esperando_confirmacion = True
                    alerta_ts_pendiente = ts_actual
                    direccion_actual = "long"

            elif rsi_actual > 70 and precio_actual >= banda_sup_actual:
                if alerta_enviada_ts != ts_actual:
                    mensaje = f"⚠️ SCALPING - SHORT 📉\n"
                    mensaje += f"RSI: {rsi_actual:.2f} | Precio: ${precio_actual:.4f}\n"
                    mensaje += f"Respondé 'si' para entrar"
                    enviar_mensaje(mensaje)
                    alerta_enviada_ts = ts_actual
                    esperando_confirmacion = True
                    alerta_ts_pendiente = ts_actual
                    direccion_actual = "short"

        if en_operacion and salida_enviada_ts != ts_anterior:
            if direccion_actual == "long" and rsi_anterior > 70 and precio_anterior >= banda_sup_anterior:
                precio_salida = precio_actual
                porcentaje = ((precio_salida - precio_entrada) / precio_entrada) * 100
                resultado = "TP" if porcentaje > 0 else "SL"
                ganancia_dolares = round(25000 * porcentaje / 100, 2)
                en_operacion = False
                salida_enviada_ts = ts_anterior
                direccion_actual = None
                mensaje = f"🔴 SALIDA SCALPING LONG - {resultado}\n"
                mensaje += f"Entrada: ${precio_entrada:.4f} | Salida: ${precio_salida:.4f}\n"
                mensaje += f"Resultado: {porcentaje:.2f}% | Fondeo: ${ganancia_dolares:.2f}\n"
                mensaje += f"⚡ Cerrar posicion AHORA"
                enviar_mensaje(mensaje)
                registrar_en_notion(resultado, round(porcentaje, 2), 0)
                status = registrar_en_notion_fondeo(resultado, precio_entrada, precio_salida, round(porcentaje, 2), ganancia_dolares, 0)
                if status == 200:
                    enviar_mensaje(f"✅ Operacion registrada en Notion")

            elif direccion_actual == "short" and rsi_anterior < 30 and precio_anterior <= banda_inf_anterior:
                precio_salida = precio_actual
                porcentaje = ((precio_entrada - precio_salida) / precio_entrada) * 100
                resultado = "TP" if porcentaje > 0 else "SL"
                ganancia_dolares = round(25000 * porcentaje / 100, 2)
                en_operacion = False
                salida_enviada_ts = ts_anterior
                direccion_actual = None
                mensaje = f"🔴 SALIDA SCALPING SHORT - {resultado}\n"
                mensaje += f"Entrada: ${precio_entrada:.4f} | Salida: ${precio_salida:.4f}\n"
                mensaje += f"Resultado: {porcentaje:.2f}% | Fondeo: ${ganancia_dolares:.2f}\n"
                mensaje += f"⚡ Cerrar posicion AHORA"
                enviar_mensaje(mensaje)
                registrar_en_notion(resultado, round(porcentaje, 2), 0)
                status = registrar_en_notion_fondeo(resultado, precio_entrada, precio_salida, round(porcentaje, 2), ganancia_dolares, 0)
                if status == 200:
                    enviar_mensaje(f"✅ Operacion registrada en Notion")

    except Exception as e:
        enviar_mensaje(f"⚠️ Error bot scalping: {str(e)}")

obtener_ultimo_mensaje()
enviar_mensaje("🤖 Bot SCALPING iniciado - Listo para operar")

while True:
    now = datetime.now()
    print(f"{now.strftime('%H:%M:%S')} - Scalping verificando...")
    verificar_senal()
    time.sleep(30)
