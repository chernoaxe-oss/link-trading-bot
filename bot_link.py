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

alerta_enviada = False
senal_salida_enviada = False
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
            "Aa": {
                "title": [{"text": {"content": "LINK"}}]
            },
            "RESULTADO": {
                "select": {"name": resultado}
            },
            "PORCENTAJE": {
                "number": porcentaje
            },
            "Fecha": {
                "date": {"start": datetime.now().strftime("%Y-%m-%d")}
            },
            "TOTAL REAL": {
                "number": total_real
            }
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.status_code

def registrar_en_notion_fondeo(resultado, precio_entrada, precio_salida, porcentaje, ganancia_dolares, balance, fase="Fase 1", cuenta="Cuenta 1"):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "parent": {"database_id": NOTION_FONDEO_DB_ID},
        "properties": {
            "Nombre": {
                "title": [{"text": {"content": f"LINK - {datetime.now().strftime('%d/%m/%Y %H:%M')}"}}]
            },
            "Cuenta": {
                "select": {"name": cuenta}
            },
            "Fase": {
                "select": {"name": fase}
            },
            "Resultado": {
                "select": {"name": resultado}
            },
            "Precio entrada": {
                "number": precio_entrada
            },
            "Precio salida": {
                "number": precio_salida
            },
            "Porcentaje": {
                "number": porcentaje
            },
            "Ganancia/Perdida": {
                "number": ganancia_dolares
            },
            "Balance cuenta": {
                "number": balance
            },
            "Fecha": {
                "date": {"start": datetime.now().strftime("%Y-%m-%d")}
            }
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.status_code

def verificar_senal():
    global alerta_enviada, senal_salida_enviada, en_operacion, precio_entrada
    try:
        data = yf.download("LINK-USD", period="1d", interval="15m", progress=False)
        data = data[['Close', 'High', 'Low', 'Open', 'Volume']]
        data.columns = ['Close', 'High', 'Low', 'Open', 'Volume']
        close = data['Close']

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0)

        rsi_actual = rsi.iloc[-1]
        precio_actual = close.iloc[-1]
        banda_inferior_actual = bb.bollinger_lband().iloc[-1]
        banda_superior_actual = bb.bollinger_hband().iloc[-1]

        rsi_anterior = rsi.iloc[-2]
        precio_anterior = close.iloc[-2]
        banda_inferior_anterior = bb.bollinger_lband().iloc[-2]
        banda_superior_anterior = bb.bollinger_hband().iloc[-2]

        # ALERTA TEMPRANA
        if rsi_actual < 30 and precio_actual <= banda_inferior_actual and not alerta_enviada and not en_operacion:
            mensaje = f"⚠️ ALERTA TEMPRANA - LINK\n"
            mensaje += f"El precio está tocando la banda inferior AHORA\n"
            mensaje += f"RSI: {rsi_actual:.2f}\n"
            mensaje += f"Precio: ${precio_actual:.4f}\n"
            mensaje += f"Esperá el cierre de la vela para confirmar entrada"
            enviar_mensaje(mensaje)
            alerta_enviada = True

        elif not (rsi_actual < 30 and precio_actual <= banda_inferior_actual):
            alerta_enviada = False

        # SEÑAL DE ENTRADA CONFIRMADA
        if rsi_anterior < 30 and precio_anterior <= banda_inferior_anterior and not en_operacion:
            precio_entrada = float(precio_actual)
            en_operacion = True
            senal_salida_enviada = False
            mensaje = f"🟢 SEÑAL DE ENTRADA CONFIRMADA - LINK\n"
            mensaje += f"RSI: {rsi_anterior:.2f}\n"
            mensaje += f"Precio de entrada: ${precio_entrada:.4f}\n"
            mensaje += f"⚡ Entrar con 30% del Trading Power en Quantfury\n"
            mensaje += f"⚡ Entrar con 100x en Bybit"
            enviar_mensaje(mensaje)

        # SEÑAL DE SALIDA CONFIRMADA
        if rsi_anterior > 70 and precio_anterior >= banda_superior_anterior and en_operacion and not senal_salida_enviada:
            precio_salida = float(precio_actual)
            porcentaje = ((precio_salida - precio_entrada) / precio_entrada) * 100
            resultado = "TP" if porcentaje > 0 else "SL"
            ganancia_dolares = round(50000 * porcentaje / 100, 2)
            en_operacion = False
            senal_salida_enviada = True

            mensaje = f"🔴 SEÑAL DE SALIDA CONFIRMADA - LINK\n"
            mensaje += f"RSI: {rsi_anterior:.2f}\n"
            mensaje += f"Precio entrada: ${precio_entrada:.4f}\n"
            mensaje += f"Precio salida: ${precio_salida:.4f}\n"
            mensaje += f"Resultado: {resultado} ({porcentaje:.2f}%)\n"
            mensaje += f"Ganancia/Pérdida en fondeo: ${ganancia_dolares:.2f}\n"
            mensaje += f"⚡ Cerrar posición en Quantfury y Bybit AHORA"
            enviar_mensaje(mensaje)

            # Registrar en Notion Quantfury
            registrar_en_notion(resultado, round(porcentaje, 2), 0)

            # Registrar en Notion Fondeo
            status = registrar_en_notion_fondeo(
                resultado,
                precio_entrada,
                precio_salida,
                round(porcentaje, 2),
                ganancia_dolares,
                0
            )
            if status == 200:
                enviar_mensaje(f"✅ Operación registrada en ambos journals de Notion")
            else:
                enviar_mensaje(f"⚠️ Error al registrar en Notion Fondeo (status {status})")

    except Exception as e:
        enviar_mensaje(f"⚠️ Error en el bot: {str(e)}")

enviar_mensaje("🤖 Bot de LINK actualizado con Journal Fondeo. Monitoreando señales...")

while True:
    now = datetime.now()
    print(f"{now.strftime('%H:%M:%S')} - Verificando señal...")
    verificar_senal()
    time.sleep(60)
