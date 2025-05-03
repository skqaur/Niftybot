## 2. src/api/angel_api.py


#!/usr/bin/env python3
# Angel One API Wrapper

import json
import time
import pyotp
import logging
import requests
import websocket
from datetime import datetime, timedelta
from threading import Thread

# Set up logger
logger = logging.getLogger('app.api')

class AngelOneAPI:
    """
    Wrapper for Angel One Smart API
    """
    
    def __init__(self, api_key, client_id):
        """
        Initialize the API wrapper
        
        Parameters:
        -----------
        api_key : str
            API key from Angel One
        client_id : str
            Client ID / User ID
        """
        self.api_key = api_key
        self.client_id = client_id
        self.access_token = None
        self.refresh_token = None
        self.feed_token = None
        self.ws = None
        self.ws_callbacks = []
        self.base_url = "https://apiconnect.angelbroking.com"
        
    def login(self, username, password, totp_secret):
        """
        Authenticate with Angel One API
        
        Parameters:
        -----------
        username : str
            User ID / Client ID
        password : str
            Trading password/PIN
        totp_secret : str
            TOTP secret for 2FA
            
        Returns:
        --------
        dict
            Login status and message
        """
        try:
            # Generate TOTP code
            totp = pyotp.TOTP(totp_secret)
            otp_token = totp.now()
            
            # Prepare login request
            login_url = f"{self.base_url}/rest/auth/angelbroking/user/v1/loginByPassword"
            
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
                'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
                'X-MACAddress': 'MAC_ADDRESS',
                'X-PrivateKey': self.api_key
            }
            
            login_data = {
                "clientcode": username,
                "password": password,
                "totp": otp_token
            }
            
            # Send login request
            response = requests.post(login_url, json=login_data, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] and data['data']['jwtToken']:
                    self.access_token = data['data']['jwtToken']
                    self.refresh_token = data['data']['refreshToken']
                    self.feed_token = data['data']['feedToken']
                    logger.info(f"Login successful for user {username}")
                    return {"status": True, "message": "Login successful"}
                else:
                    logger.error(f"Login failed: {data.get('message', 'Unknown error')}")
                    return {"status": False, "message": data.get('message', 'Login failed')}
            else:
                logger.error(f"Login request failed with status code: {response.status_code}")
                return {"status": False, "message": f"Login failed with status code: {response.status_code}"}
                
        except Exception as e:
            logger.exception(f"Error during login: {str(e)}")
            return {"status": False, "message": str(e)}
    
    def logout(self):
        """
        Logout from Angel One API
        
        Returns:
        --------
        dict
            Logout status
        """
        try:
            if not self.access_token:
                return {"status": False, "message": "Not logged in"}
                
            logout_url = f"{self.base_url}/rest/secure/angelbroking/user/v1/logout"
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
                'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
                'X-MACAddress': 'MAC_ADDRESS',
                'X-PrivateKey': self.api_key
            }
            
            logout_data = {
                "clientcode": self.client_id
            }
            
            response = requests.post(logout_url, json=logout_data, headers=headers)
            
            if response.status_code == 200:
                self.access_token = None
                self.refresh_token = None
                self.feed_token = None
                logger.info("Logout successful")
                return {"status": True, "message": "Logout successful"}
            else:
                logger.error(f"Logout failed with status code: {response.status_code}")
                return {"status": False, "message": f"Logout failed with status code: {response.status_code}"}
                
        except Exception as e:
            logger.exception(f"Error during logout: {str(e)}")
            return {"status": False, "message": str(e)}
    
    def _make_request(self, method, url, json=None, params=None):
        """
        Make authenticated API request
        
        Parameters:
        -----------
        method : str
            HTTP method (GET, POST, etc.)
        url : str
            API endpoint URL
        json : dict, optional
            JSON payload for POST requests
        params : dict, optional
            Query parameters for GET requests
            
        Returns:
        --------
        dict
            API response
        """
        if not self.access_token:
            logger.error("Not authenticated. Please login first.")
            return None
            
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-UserType': 'USER',
            'X-SourceID': 'WEB',
            'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
            'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
            'X-MACAddress': 'MAC_ADDRESS',
            'X-PrivateKey': self.api_key
        }
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=json)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API request failed with status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None
                
        except Exception as e:
            logger.exception(f"Error making API request: {str(e)}")
            return None
    
    def get_profile(self):
        """
        Get user profile information
        
        Returns:
        --------
        dict
            User profile data
        """
        try:
            url = f"{self.base_url}/rest/secure/angelbroking/user/v1/getProfile"
            response = self._make_request("GET", url)
            
            if response and response.get('status'):
                return response['data']
            else:
                logger.error("Failed to fetch profile")
                return None
                
        except Exception as e:
            logger.exception(f"Error fetching profile: {str(e)}")
            return None
    
    def get_ltp(self, exchange, tradingsymbol, symboltoken):
        """
        Get Last Traded Price (LTP) for a symbol
        
        Parameters:
        -----------
        exchange : str
            Exchange (NSE, BSE, NFO, etc.)
        tradingsymbol : str
            Trading symbol
        symboltoken : str
            Symbol token
            
        Returns:
        --------
        dict
            LTP data
        """
        try:
            url = f"{self.base_url}/rest/secure/angelbroking/order/v1/getLtpData"
            
            ltp_data = {
                "exchange": exchange,
                "tradingsymbol": tradingsymbol,
                "symboltoken": symboltoken
            }
            
            response = self._make_request("POST", url, json=ltp_data)
            
            if response and response.get('status'):
                return response['data']
            else:
                logger.error(f"Failed to fetch LTP for {tradingsymbol}")
                return None
                
        except Exception as e:
            logger.exception(f"Error fetching LTP: {str(e)}")
            return None
    
    def get_option_chain(self, symbol, expiry):
        """
        Get option chain for a given symbol and expiry
        
        Parameters:
        -----------
        symbol : str
            Symbol name (e.g., 'NIFTY')
        expiry : str
            Expiry date (format: YYMMDD)
            
        Returns:
        --------
        list
            List of dictionaries containing strike prices and their premiums
        """
        try:
            logger.info(f"Fetching option chain for {symbol} {expiry}")
            
            # NOTE: This is a simplified implementation. In production, you would need
            # to use the actual API endpoint provided by Angel One for option chain data.
            # This might involve multiple API calls or a specific endpoint not documented here.
            
            # For now, we'll simulate it by fetching data for a range of strikes
            # In actual implementation, you'd need to use the proper option chain endpoint
            
            current_nifty = self.get_ltp("NSE", "NIFTY-INDEX", "99926000")
            if not current_nifty:
                return []
                
            current_price = float(current_nifty['last_price'])
            
            # Generate a range of strikes (typically ±10 strikes from ATM)
            atm_strike = int(round(current_price / 50) * 50)
            strike_step = 50
            strike_range = 10  # ±10 strikes
            
            option_chain = []
            
            for i in range(-strike_range, strike_range + 1):
                strike = atm_strike + (i * strike_step)
                
                # Construct trading symbols (simplified for Nifty weekly options)
                ce_symbol = f"NIFTY{expiry}{strike}CE"
                pe_symbol = f"NIFTY{expiry}{strike}PE"
                
                # Attempt to get LTP data for each option
                # Note: You'll need proper symbol tokens from the contract master file
                ce_data = self.get_ltp("NFO", ce_symbol, f"{ce_symbol}_TOKEN")
                pe_data = self.get_ltp("NFO", pe_symbol, f"{pe_symbol}_TOKEN")
                
                option_chain.append({
                    'strike': strike,
                    'last_price_CE': float(ce_data['last_price']) if ce_data else 0,
                    'last_price_PE': float(pe_data['last_price']) if pe_data else 0,
                    'tradingsymbol_CE': ce_symbol,
                    'tradingsymbol_PE': pe_symbol,
                    'token_CE': f"{ce_symbol}_TOKEN",
                    'token_PE': f"{pe_symbol}_TOKEN"
                })
            
            return option_chain
            
        except Exception as e:
            logger.exception(f"Error fetching option chain: {str(e)}")
            return []
    
    def place_order(self, order_params):
        """
        Place an order on Angel One
        
        Parameters:
        -----------
        order_params : dict
            Order parameters
            
        Returns:
        --------
        str
            Order ID if successful, None otherwise
        """
        try:
            # Validate required parameters
            required_params = [
                'variety', 'tradingsymbol', 'symboltoken', 'transactiontype',
                'exchange', 'ordertype', 'producttype', 'duration', 'quantity'
            ]
            
            for param in required_params:
                if param not in order_params:
                    raise ValueError(f"Missing required parameter: {param}")
            
            # Validate quantity is a multiple of lot size for options
            if order_params['exchange'] == 'NFO':
                try:
                    quantity = int(order_params['quantity'])
                    if quantity <= 0:
                        raise ValueError("Quantity must be positive")
                except ValueError:
                    raise ValueError("Invalid quantity value")
                    
            # Validate price for limit orders
            if order_params['ordertype'] == 'LIMIT' and 'price' not in order_params:
                raise ValueError("Price is required for LIMIT orders")
                
            # Validate trigger price for SL and SL-M orders
            if order_params['ordertype'] in ['STOPLOSS', 'STOPLOSS_MARKET'] and 'triggerprice' not in order_params:
                raise ValueError("Trigger price is required for STOPLOSS orders")
            
            # Set default values for certain parameters
            order_params.setdefault('price', '0')
            order_params.setdefault('triggerprice', '0')
            order_params.setdefault('squareoff', '0')
            order_params.setdefault('stoploss', '0')
            order_params.setdefault('trailingStopLoss', '0')
            order_params.setdefault('disclosedquantity', '0')
            
            logger.info(f"Placing order: {order_params}")
            
            # Call the SmartAPI order placement endpoint
            url = f"{self.base_url}/rest/secure/angelbroking/order/v1/placeOrder"
            response = self._make_request("POST", url, json=order_params)
            
            if response and response.get('status') and response.get('data', {}).get('orderid'):
                order_id = response['data']['orderid']
                logger.info(f"Order placed successfully: {order_id}")
                return order_id
            else:
                logger.error(f"Failed to place order: {response}")
                return None
                
        except Exception as e:
            logger.exception(f"Error placing order: {str(e)}")
            return None
    
    def get_position(self):
        """
        Get current positions
        
        Returns:
        --------
        list
            List of positions
        """
        try:
            url = f"{self.base_url}/rest/secure/angelbroking/order/v1/getPosition"
            response = self._make_request("GET", url)
            
            if response and response.get('status'):
                return response.get('data', [])
            else:
                logger.error("Failed to fetch positions")
                return []
                
        except Exception as e:
            logger.exception(f"Error fetching positions: {str(e)}")
            return []
    
    def get_trade_book(self):
        """
        Get trade book for the day
        
        Returns:
        --------
        list
            List of trades
        """
        try:
            url = f"{self.base_url}/rest/secure/angelbroking/order/v1/getTradeBook"
            response = self._make_request("GET", url)
            
            if response and response.get('status'):
                return response.get('data', [])
            else:
                logger.error("Failed to fetch trade book")
                return []
                
        except Exception as e:
            logger.exception(f"Error fetching trade book: {str(e)}")
            return []
    
    def find_nearest_expiry(self):
        """
        Find the nearest weekly expiry date for Nifty options
        
        Returns:
        --------
        str
            Expiry date in format 'YYMMDD'
        """
        try:
            # Get current date
            today = datetime.now()
            
            # Find the next Thursday (weekday 3)
            days_until_thursday = (3 - today.weekday()) % 7
            
            # If today is Thursday and before market close, use today as expiry
            if today.weekday() == 3 and today.hour < 15:
                next_thursday = today
            else:
                # Otherwise, use next Thursday
                if days_until_thursday == 0:
                    days_until_thursday = 7
                next_thursday = today + timedelta(days=days_until_thursday)
            
            # Format as YYMMDD
            expiry_date = next_thursday.strftime('%y%m%d')
            
            logger.info(f"Selected expiry date: {expiry_date}")
            return expiry_date
            
        except Exception as e:
            logger.exception(f"Error finding nearest expiry: {str(e)}")
            # Default to current date as fallback
            return datetime.now().strftime('%y%m%d')
    
    def search_option_contracts(self, symbol, expiry, strike, option_type, contract_size=75):
        """
        Search for option contracts based on parameters
        
        Parameters:
        -----------
        symbol : str
            Symbol name (e.g., 'NIFTY')
        expiry : str
            Expiry date (format: YYMMDD)
        strike : int
            Strike price
        option_type : str
            Option type ('CE' for Call, 'PE' for Put)
            
        Returns:
        --------
        dict
            Option contract details
        """
        try:
            # Construct the typical trading symbol format
            # For Nifty, it's usually "NIFTY{expiry}{strike}{option_type}"
            trading_symbol = f"{symbol}{expiry}{strike}{option_type}"
            
            # In actual implementation, you would look up the symbol token
            # from a contract master file or API
            
            # For demonstration, create a simulated response
            contract = {
                'tradingsymbol': trading_symbol,
                'symboltoken': f"{trading_symbol}_TOKEN",  # This would be the actual token from exchange
                'strike': strike,
                'expiry': expiry,
                'option_type': option_type,
                'lot_size': contract_size  # Nifty option lot size
            }
            
            logger.info(f"Found option contract: {trading_symbol}")
            return contract
            
        except Exception as e:
            logger.exception(f"Error searching option contracts: {str(e)}")
            return None
    
    def connect_websocket(self, on_data):
        """
        Connect to Angel One WebSocket for real-time data
        
        Parameters:
        -----------
        on_data : callable
            Callback function for data updates
        """
        try:
            if not self.feed_token:
                logger.error("Feed token not available. Please login first.")
                return
            
            # WebSocket URL (this is a placeholder - use actual Angel One WebSocket URL)
            ws_url = f"wss://smartapisocket.angelone.in/smart-stream"
            
            def on_open(ws):
                logger.info("WebSocket connection opened")
                # Subscribe to Nifty index
                subscribe_message = {
                    "action": "subscribe",
                    "params": {
                        "mode": "FULL",
                        "exchangeType": "NSE",
                        "tokens": ["26000"]  # Nifty index token
                    }
                }
                ws.send(json.dumps(subscribe_message))
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    on_data(data)
                except Exception as e:
                    logger.exception(f"Error processing WebSocket message: {str(e)}")
            
            def on_error(ws, error):
                logger.error(f"WebSocket error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
            
            # Create WebSocket connection
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                header={
                    "Authorization": f"Bearer {self.feed_token}",
                    "x-api-key": self.api_key,
                    "x-client-code": self.client_id,
                    "x-feed-token": self.feed_token
                }
            )
            
            # Run WebSocket in a separate thread
            ws_thread = Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            logger.info("WebSocket thread started")
            
        except Exception as e:
            logger.exception(f"Error connecting to WebSocket: {str(e)}")
    
    def subscribe_symbol(self, exchange_type, token):
        """
        Subscribe to a symbol for real-time updates
        
        Parameters:
        -----------
        exchange_type : int
            Exchange type (1: NSE, 2: NFO, etc.)
        token : str
            Symbol token
        """
        try:
            if not self.ws:
                logger.error("WebSocket not connected")
                return
            
            subscribe_message = {
                "action": "subscribe",
                "params": {
                    "mode": "FULL",
                    "exchangeType": exchange_type,
                    "tokens": [token]
                }
            }
            
            self.ws.send(json.dumps(subscribe_message))
            logger.info(f"Subscribed to symbol: {token}")
            
        except Exception as e:
            logger.exception(f"Error subscribing to symbol: {str(e)}")
