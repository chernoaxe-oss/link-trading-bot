import requests
import yfinance as yf
import pandas as pd
import ta
import time
from datetime import datetime

TOKEN = "8876856197:AAEtpTiDK4zlgoCYvGv09Tzl1L9B9s3bWAc"
CHAT_ID = "1482855145"
NOTION_TOKEN = "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"
NOTION_DB_ID = "33f9d65898f4808dbe28e21c1cf69379"
NOTION_FONDEO_DB_ID = "3799d65898f480539868f003b846e5d7"

alerta_enviada_ts = None
entrada_enviada_ts = None
salida_enviada_ts = None
en_operacion = False
precio_entrada = 0

def enviar_mensaje(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": texto}
    requests.get(url, params=params)

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
            "Aa": {"title": [{"text": {"content": "LINK"}}]},
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
            "Nombre": {"title": [{"text": {"content": f"LINK - {datetime.now().strftime('%d/%m/%Y %H:%M')}"}}]},
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
    global alerta_enviada_ts, entrada_enviada_ts, salida_enviada_ts, en_operacion, precio_entrada
    try:
        data = yf.download("LINK-USD", period="5d", interval="15m", progress=False)
        data = data[['Close', 'High', 'Low', 'Open', 'Volume']]
        data.columns = ['Close', 'High', 'Low', 'Open', 'Volume']
        close = data['Close']

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0)

        # Vela actual (en curso)
        ts_actual = data.index[-1]
        rsi_actual = float(rsi.iloc[-1])
        precio_actual = float(close.iloc[-1])
        banda_inf_actual = float(bb.bollinger_lband().iloc[-1])

        # Vela anterior (cerrada)
        ts_anterior = data.index[-2]
        rsi_anterior = float(rsi.iloc[-2])
        precio_anterior = float(close.iloc[-2])
        banda_inf_anterior = float(bb.bollinger_lband().iloc[-2])
        banda_sup_anterior = float(bb.bollinger_hband().iloc[-2])

        # ALERTA TEMPRANA - vela actual toca banda con RSI bajo 30
        if rsi_actual < 30 and precio_actual <= banda_inf_actual and not en_operacion:
            if alerta_enviada_ts != ts_actual:
                mensaje = f"⚠️ ALERTA TEMPRANA - LINK\n"
                mensaje += f"El precio está tocando la banda inferior AHORA\n"
                mensaje += f"RSI: {rsi_actual:.2f}\n"
                mensaje += f"Precio: ${precio_actual:.4f}\n"
                mensaje += f"Esperá el cierre de la vela para confirmar entrada"
                enviar_mensaje(mensaje)
                alerta_enviada_ts = ts_actual

        # SEÑAL DE ENTRADA - vela anterior cerró con RSI bajo 30 y precio en banda
        if rsi_anterior < 30 and precio_anterior <= banda_inf_anterior and not en_operacion:
            if entrada_enviada_ts != ts_anterior:
                precio_entrada = precio_actual
                en_operacion = True
                salida_enviada_ts = None
                mensaje = f"🟢 SEÑAL DE ENTRADA CONFIRMADA - LINK\n"
                mensaje += f"RSI vela cerrada: {rsi_anterior:.2f}\n"
                mensaje += f"Precio de entrada: ${precio_entrada:.4f}\n"
                mensaje += f"⚡ Entrar con 30% del Trading Power en Quantfury\n"
                mensaje += f"⚡ Entrar con 100x en Bybit"
                enviar_mensaje(mensaje)
                entrada_enviada_ts = ts_anterior

        # SEÑAL DE SALIDA - vela anterior cerró con RSI sobre 70 y precio en banda superior
        if rsi_anterior > 70 and precio_anterior >= banda_sup_anterior and en_operacion:
            if salida_enviada_ts != ts_anterior:
                precio_salida = precio_actual
                porcentaje = ((precio_salida - precio_entrada) / precio_entrada) * 100
                resultado = "TP" if porcentaje > 0 else "SL"
                ganancia_dolares = round(50000 * porcentaje / 100, 2)
                en_operacion = False
                salida_enviada_ts = ts_anterior

                mensaje = f"🔴 SEÑAL DE SALIDA CONFIRMADA - LINK\n"
                mensaje += f"RSI vela cerrada: {rsi_anterior:.2f}\n"
                mensaje += f"Precio entrada: ${precio_entrada:.4f}\n"
                mensaje += f"Precio salida: ${precio_salida:.4f}\n"
                mensaje += f"Resultado: {resultado} ({porcentaje:.2f}%)\n"
                mensaje += f"Ganancia/Pérdida en fondeo: ${ganancia_dolares:.2f}\n"
                mensaje += f"⚡ Cerrar posición en Quantfury y Bybit AHORA"
                enviar_mensaje(mensaje)

                registrar_en_notion(resultado, round(porcentaje, 2), 0)
                status = registrar_en_notion_fondeo(
                    resultado, precio_entrada, precio_salida,
                    round(porcentaje, 2), ganancia_dolares, 0
                )
                if status == 200:
                    enviar_mensaje(f"✅ Operación registrada en ambos journals de Notion")
                else:
                    enviar_mensaje(f"⚠️ Error al registrar en Notion Fondeo (status {status})")

    except Exception as e:
        enviar_mensaje(f"⚠️ Error en el bot: {str(e)}")

enviar_mensaje("🤖 Bot actualizado - RSI corregido con 5 dias de datos")

while True:
    now = datetime.now()
    print(f"{now.strftime('%H:%M:%S')} - Verificando señal...")
    verificar_senal()
    time.sleep(60)
