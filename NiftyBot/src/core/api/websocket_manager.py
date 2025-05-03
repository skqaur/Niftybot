import threading
import json
import logging
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

logger = logging.getLogger('app.websocket')

class WebSocketManager:
    def __init__(self, auth_token, api_key, client_code, feed_token):
        self.ltp_store = {}
        self.sws = SmartWebSocketV2(auth_token, api_key, client_code, feed_token)
        self.connected = False
        
    def on_data(self, wsapp, message):
        try:
            if 'last_traded_price' in message:
                token = message['token']
                ltp = message['last_traded_price']
                self.ltp_store[token] = ltp
                logger.debug(f"Updated LTP for {token}: {ltp}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def on_open(self, wsapp):
        logger.info("WebSocket connected")
        self.connected = True
        # Subscribe to Nifty
        self.sws.subscribe('abc123', 1, [{"exchangeType": 1, "tokens": ["26000"]}])
    
    def on_error(self, wsapp, error):
        logger.error(f"WebSocket error: {error}")
        self.connected = False
    
    def on_close(self, wsapp):
        logger.info("WebSocket closed")
        self.connected = False
    
    def connect(self):
        self.sws.on_open = self.on_open
        self.sws.on_data = self.on_data
        self.sws.on_error = self.on_error
        self.sws.on_close = self.on_close
        self.sws.connect()
    
    def get_ltp(self, token):
        return self.ltp_store.get(token)