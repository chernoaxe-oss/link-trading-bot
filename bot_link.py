import requests
import yfinance as yf
import pandas as pd
import ta
import time
from datetime import datetime

TOKEN = "8876856197:AAEtpTiDK4zlgoCYvGv09Tzl1L9B9s3bWAc"
CHAT_ID = "1482855145"

alerta_enviada = False
senal_entrada_enviada = False
senal_salida_enviada = False

def enviar_mensaje(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": texto}
    requests.get(url, params=params)

def verificar_senal():
    global alerta_enviada, senal_entrada_enviada, senal_salida_enviada
    try:
        data = yf.download("LINK-USD", period="1d", interval="15m", progress=False)
        data = data[['Close', 'High', 'Low', 'Open', 'Volume']]
        data.columns = ['Close', 'High', 'Low', 'Open', 'Volume']
        close = data['Close']

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0)

        # Vela actual (en curso)
        rsi_actual = rsi.iloc[-1]
        precio_actual = close.iloc[-1]
        banda_inferior_actual = bb.bollinger_lband().iloc[-1]
        banda_superior_actual = bb.bollinger_hband().iloc[-1]

        # Vela anterior (cerrada)
        rsi_anterior = rsi.iloc[-2]
        precio_anterior = close.iloc[-2]
        banda_inferior_anterior = bb.bollinger_lband().iloc[-2]
        banda_superior_anterior = bb.bollinger_hband().iloc[-2]

        # ALERTA TEMPRANA - precio toca banda durante la vela actual
        if rsi_actual < 30 and precio_actual <= banda_inferior_actual and not alerta_enviada:
            mensaje = f"⚠️ ALERTA TEMPRANA - LINK\n"
            mensaje += f"El precio está tocando la banda inferior AHORA\n"
            mensaje += f"RSI: {rsi_actual:.2f}\n"
            mensaje += f"Precio: ${precio_actual:.4f}\n"
            mensaje += f"Esperá el cierre de la vela para confirmar entrada"
            enviar_mensaje(mensaje)
            alerta_enviada = True
            senal_entrada_enviada = False
        elif not (rsi_actual < 30 and precio_actual <= banda_inferior_actual):
            alerta_enviada = False

        # SEÑAL DE ENTRADA - vela cerrada con condiciones cumplidas
        if rsi_anterior < 30 and precio_anterior <= banda_inferior_anterior and not senal_entrada_enviada:
            mensaje = f"🟢 SEÑAL DE ENTRADA CONFIRMADA - LINK\n"
            mensaje += f"La vela cerró con condiciones cumplidas\n"
            mensaje += f"RSI: {rsi_anterior:.2f}\n"
            mensaje += f"Precio de entrada: ${precio_actual:.4f}\n"
            mensaje += f"⚡ Entrar con 30% del Trading Power AHORA"
            enviar_mensaje(mensaje)
            senal_entrada_enviada = True

        # SEÑAL DE SALIDA - vela cerrada con condiciones cumplidas
        if rsi_anterior > 70 and precio_anterior >= banda_superior_anterior and not senal_salida_enviada:
            mensaje = f"🔴 SEÑAL DE SALIDA CONFIRMADA - LINK\n"
            mensaje += f"La vela cerró con condiciones cumplidas\n"
            mensaje += f"RSI: {rsi_anterior:.2f}\n"
            mensaje += f"Precio actual: ${precio_actual:.4f}\n"
            mensaje += f"⚡ Cerrar posición AHORA"
            enviar_mensaje(mensaje)
            senal_salida_enviada = True
        elif not (rsi_anterior > 70 and precio_anterior >= banda_superior_anterior):
            senal_salida_enviada = False

    except Exception as e:
        enviar_mensaje(f"⚠️ Error en el bot: {str(e)}")

enviar_mensaje("🤖 Bot de LINK actualizado. Alertas tempranas activadas!")

while True:
    now = datetime.now()
    print(f"{now.strftime('%H:%M:%S')} - Verificando señal...")
    verificar_senal()
    time.sleep(60)
