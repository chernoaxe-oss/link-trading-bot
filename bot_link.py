import requests
import yfinance as yf
import pandas as pd
import ta
import time
from datetime import datetime

TOKEN = "8876856197:AAEtpTiDK4zlgoCYvGv09Tzl1L9B9s3bWAc"
CHAT_ID = "1482855145"

def enviar_mensaje(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": texto}
    requests.get(url, params=params)

def verificar_senal():
    try:
        data = yf.download("LINK-USD", period="1d", interval="15m", progress=False)
        data = data[['Close', 'High', 'Low', 'Open', 'Volume']]
        data.columns = ['Close', 'High', 'Low', 'Open', 'Volume']
        close = data['Close']

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2.0)

        ultima_vela_rsi = rsi.iloc[-2]
        ultima_vela_precio = close.iloc[-2]
        banda_inferior = bb.bollinger_lband().iloc[-2]
        banda_superior = bb.bollinger_hband().iloc[-2]
        precio_actual = close.iloc[-1]

        if ultima_vela_rsi < 30 and ultima_vela_precio <= banda_inferior:
            mensaje = f"🟢 SEÑAL DE ENTRADA LINK\n"
            mensaje += f"RSI: {ultima_vela_rsi:.2f} (por debajo de 30)\n"
            mensaje += f"Precio tocó banda inferior: ${ultima_vela_precio:.4f}\n"
            mensaje += f"Precio actual: ${precio_actual:.4f}\n"
            mensaje += f"⚡ Entrar con 30% del Trading Power"
            enviar_mensaje(mensaje)

        if ultima_vela_rsi > 70 and ultima_vela_precio >= banda_superior:
            mensaje = f"🔴 SEÑAL DE SALIDA LINK\n"
            mensaje += f"RSI: {ultima_vela_rsi:.2f} (por encima de 70)\n"
            mensaje += f"Precio tocó banda superior: ${ultima_vela_precio:.4f}\n"
            mensaje += f"Precio actual: ${precio_actual:.4f}\n"
            mensaje += f"⚡ Cerrar posición"
            enviar_mensaje(mensaje)

    except Exception as e:
        enviar_mensaje(f"⚠️ Error en el bot: {str(e)}")

enviar_mensaje("🤖 Bot de LINK iniciado en Railway. Monitoreando señales...")

while True:
    now = datetime.now()
    print(f"{now.strftime('%H:%M:%S')} - Verificando señal...")
    verificar_senal()
    time.sleep(900)
