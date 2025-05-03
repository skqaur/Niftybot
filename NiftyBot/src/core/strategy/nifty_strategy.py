#!/usr/bin/env python3
# Nifty Options Trading Strategy Implementation

import os
import json
import time
import math
import logging
import threading
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger('app.strategy')

class NiftyOptionStrategy:
    """
    Implementation of the Nifty Options Trading Strategy
    
    Strategy operates on the following rules:
    1. When price is between XX00 and XX69.99:
       - Set virtual stop order at XX70
       - If price breaks above XX70, confirm trigger with SL at XX69.99, target at XX95
       - If target hit: Execute ACTUALBUY (Nifty Call Option with premium closest to ₹200)
       - Set new target at XX+20 (XX15), SL at XX70
       
    2. When price is between XX70 and XX99.99 (without active trigger):
       - Set virtual limit order at XX70
       - If price falls back to trigger during this candle, activate with target XX95, SL XX69.99
       - If target hit: Execute ACTUALBUY
       - If SL hit: Revert to first condition logic
    """
    
    def __init__(self, api, settings=None):
        """
        Initialize the strategy
        
        Parameters:
        -----------
        api : AngelOneAPI
            Instance of the Angel One API wrapper
        settings : dict, optional
            Strategy settings (defaults will be used if not provided)
        """
        self.api = api
        self.running = False
        self.simulation_mode = True
        self.lock = threading.Lock()
        
        # Default settings
        self.settings = {
            'trigger_level': 70,
            'execution_level': 95,
            'target_points': 20,
            'stop_loss': 25,
            'option_premium_target': 200,  # Target premium for option selection (₹)
            'option_premium_range': 25,    # Acceptable range for premium (₹)
            'lot_size': 1,
            'contract_size': 75,
            'update_interval': 1,  # in seconds
        }
        
        # Update with provided settings
        if settings:
            self.update_settings(settings)
            
        # Strategy state variables
        self.reset_state()
        
        # Trade history
        self.trade_history = []
        self._load_trade_history()
    
    def reset_state(self):
        """Reset the strategy state variables"""
        self.current_base = None
        self.active_trigger = False
        self.in_trade = False
        self.trigger_price = None
        self.stop_loss_price = None
        self.target_price = None
        self.entry_price = None
        self.entry_time = None
        self.setup_type = None
        self.current_option = None
        self.current_option_price = None
        self.current_pnl = None
        
    def update_settings(self, settings):
        """
        Update strategy settings
        
        Parameters:
        -----------
        settings : dict
            Strategy settings to update
        """
        with self.lock:
            for key, value in settings.items():
                if key in self.settings:
                    self.settings[key] = value
            
            logger.info(f"Strategy settings updated: {self.settings}")
            
    def set_simulation_mode(self, enabled):
        """
        Enable or disable simulation mode
        
        Parameters:
        -----------
        enabled : bool
            True to enable simulation mode, False to disable
        """
        with self.lock:
            self.simulation_mode = enabled
            logger.info(f"Simulation mode {'enabled' if enabled else 'disabled'}")
            
    def start(self):
        """Start the strategy execution"""
        if self.running:
            logger.warning("Strategy already running")
            return
            
        try:
            # Reset the state
            self.reset_state()
            
            # Connect to WebSocket for real-time updates
            self.api.connect_websocket(self._on_price_update)
            
            # Subscribe to Nifty index
            self.api.subscribe_symbol(1, "26000")  # NSE exchange, Nifty index token
            
            self.running = True
            logger.info("Strategy started")
            
            # Start the strategy loop
            self._strategy_loop()
            
        except Exception as e:
            logger.exception(f"Error starting strategy: {str(e)}")
            self.stop()
            
    def stop(self):
        """Stop the strategy execution"""
        if not self.running:
            logger.warning("Strategy not running")
            return
            
        try:
            self.running = False
            
            # Close any open positions if needed
            if self.in_trade:
                self._exit_position("Strategy stopped")
                
            logger.info("Strategy stopped")
            
        except Exception as e:
            logger.exception(f"Error stopping strategy: {str(e)}")
            
    def get_trade_history(self):
        """
        Get the trade history
        
        Returns:
        --------
        list
            List of trade records
        """
        return self.trade_history
        
    def get_current_state(self):
        """
        Get the current strategy state
        
        Returns:
        --------
        dict
            Current strategy state
        """
        with self.lock:
            state = {
                'active_trigger': self.active_trigger,
                'in_trade': self.in_trade,
                'current_base': self.current_base,
                'trigger_price': self.trigger_price,
                'stop_loss_price': self.stop_loss_price,
                'target_price': self.target_price,
                'entry_price': self.entry_price,
                'entry_time': self.entry_time.strftime('%H:%M:%S') if self.entry_time else None,
                'setup_type': self.setup_type,
                'current_option': self.current_option,
                'current_option_price': self.current_option_price,
                'current_pnl': self.current_pnl,
                'simulation_mode': self.simulation_mode
            }
            return state
            
    def _strategy_loop(self):
        """Main strategy loop that runs in a separate thread"""
        while self.running:
            try:
                # Check if current time is within trading hours (9:30 AM to 3:30 PM, Mon-Fri)
                current_time = datetime.now()
                current_hour = current_time.hour
                current_minute = current_time.minute
                current_weekday = current_time.weekday()
                
                # Only process during trading hours (9:30 AM to 3:30 PM, Monday to Friday)
                is_trading_hours = (
                    0 <= current_weekday <= 4 and  # Monday to Friday
                    (
                        (current_hour == 9 and current_minute >= 30) or  # After 9:30 AM
                        (9 < current_hour < 15) or  # Between 10 AM and 3 PM
                        (current_hour == 15 and current_minute <= 30)  # Before 3:30 PM
                    )
                )
                
                if not is_trading_hours:
                    # Sleep for a minute if outside trading hours
                    time.sleep(60)
                    continue

                # Sleep for the update interval
                time.sleep(self.settings['update_interval'])
                
                # Get the current Nifty price
                nifty_data = self.api.get_ltp("NSE", "NIFTY-INDEX", "26000")
                current_price = float(nifty_data['last_price'])
                
                # Process the price
                self._process_price(current_price)
                
                # Monitor active positions
                self._monitor_positions()
                
            except Exception as e:
                logger.exception(f"Error in strategy loop: {str(e)}")
                # Don't exit the loop on error, just continue
    
    def _process_price(self, price):
        """
        Process current price and execute strategy logic
        
        Parameters:
        -----------
        price : float
            Current Nifty price
        """
        with self.lock:
            # Initialize base price if not set
            if self.current_base is None:
                self._update_base_price(price)
                
            # Check if in trade
            if self.in_trade:
                # Check if target or stop loss is hit
                if price >= self.target_price:  # Target hit
                    self._exit_position("Target Hit")
                elif price <= self.stop_loss_price:  # Stop loss hit
                    self._exit_position("Stop Loss")
                    
            # Check if trigger is active
            elif self.active_trigger:
                # Check if execution target is hit
                if price >= self.target_price:
                    # Execute buy
                    self._enter_position(self.target_price)
                # Check if trigger stop loss is hit
                elif price <= self.stop_loss_price:
                    # Invalidate trigger
                    self.active_trigger = False
                    logger.info(f"Trigger invalidated at {price}")
                    
            # Check for new setup conditions
            else:
                price_zone = self._check_price_zone(price)
                
                if price_zone == '00-69':
                    # Setup stop order at trigger level (70)
                    self.trigger_price = self.current_base + self.settings['trigger_level']
                    
                    # Check if price breaks above trigger
                    if price >= self.trigger_price:
                        # Activate trigger
                        self._activate_trigger("Stop Order (00-69)")
                        
                elif price_zone == '70-99':
                    # Setup limit order at trigger level (70)
                    self.trigger_price = self.current_base + self.settings['trigger_level']
                    
                    # Check if price falls back to trigger
                    if price <= self.trigger_price:
                        # Activate trigger
                        self._activate_trigger("Limit Order (70-99)")
    
    
    def _update_base_price(self, price):
        """
        Update the base price reference (nearest 100)
        
        Parameters:
        -----------
        price : float
            Current price
        """
        self.current_base = int(price / 100) * 100
        logger.info(f"Base price updated to {self.current_base}")
        
    def _check_price_zone(self, price):
        """
        Determine which price zone the current price is in
        
        Parameters:
        -----------
        price : float
            Current price
            
        Returns:
        --------
        str
            Price zone ('00-69' or '70-99')
        """
        if self.current_base is None:
            self._update_base_price(price)
            
        price_offset = price - self.current_base
        
        if 0 <= price_offset < self.settings['trigger_level']:
            return '00-69'
        elif self.settings['trigger_level'] <= price_offset < 100:
            return '70-99'
        else:
            # Price has moved to a new 100s level, update the base
            self._update_base_price(price)
            return self._check_price_zone(price)
            
    def _activate_trigger(self, setup_type):
        """
        Activate a trade trigger
        
        Parameters:
        -----------
        setup_type : str
            Type of setup ('Stop Order (00-69)' or 'Limit Order (70-99)')
        """
        self.active_trigger = True
        self.stop_loss_price = self.trigger_price - 0.01  # Just below trigger
        self.target_price = self.current_base + self.settings['execution_level']
        self.setup_type = setup_type
        
        logger.info(f"Trigger activated at {self.trigger_price} with target {self.target_price} and stop loss {self.stop_loss_price}")
        logger.info(f"Setup type: {setup_type}")
        
    def _enter_position(self, entry_price):
        """
        Enter a position (buy Nifty call option)
        
        Parameters:
        -----------
        entry_price : float
            Entry price (Nifty level)
        """
        self.in_trade = True
        self.entry_price = entry_price
        self.entry_time = datetime.now()
        
        # Set new target and stop loss for the trade
        self.target_price = self.entry_price + self.settings['target_points']
        self.stop_loss_price = self.trigger_price
        
        logger.info(f"Entering position at {entry_price} with target {self.target_price} and stop loss {self.stop_loss_price}")
        
        # Find the Nifty call option to buy
        try:
            expiry_date = self.api.find_nearest_expiry()
            
            # Find option with premium closest to target (₹200)
            option_data = self._find_option_with_premium(entry_price, expiry_date, 
                                                          self.settings['option_premium_target'])
            
            if not option_data:
                logger.error(f"Failed to find option with premium close to ₹{self.settings['option_premium_target']}")
                self.in_trade = False
                return
            
            strike_price = option_data['strike']
            option_price = option_data['premium']
            option_symbol = option_data['tradingsymbol']
            option_token = option_data['token']
            
            # In simulation mode, just log the intent
            if self.simulation_mode:
                self.current_option = f"NIFTY {expiry_date} {strike_price} CE"
                self.current_option_price = option_price
                logger.info(f"Simulation: Would buy {self.current_option} at ₹{self.current_option_price}")
            else:
                # In real trading mode, place the order
                self.current_option = option_symbol
                
                # Place the order
                order_params = {
                    "variety": "NORMAL",
                    "tradingsymbol": option_symbol,
                    "symboltoken": option_token,
                    "transactiontype": "BUY",
                    "exchange": "NFO",
                    "ordertype": "MARKET",
                    "producttype": "INTRADAY",
                    "duration": "DAY",
                    "quantity": str(self.settings['lot_size'] * self.settings['contract_size'])  #lot size for Nifty options
                }
                
                order_id = self.api.place_order(order_params)
                
                if not order_id:
                    logger.error("Failed to place buy order")
                    self.in_trade = False
                    return
                    
                logger.info(f"Order placed successfully: {order_id}")
                
                # Get the execution price
                time.sleep(2)  # Wait for order execution
                trade_book = self.api.get_trade_book()
                
                for trade in trade_book:
                    if trade['orderid'] == order_id:
                        self.current_option_price = float(trade['averageprice'])
                        break
                else:
                    # If not found in trade book, use the current market price
                    option_ltp = self.api.get_ltp("NFO", option_symbol, option_token)
                    self.current_option_price = float(option_ltp['last_price'])
                
                logger.info(f"Bought {self.current_option} at ₹{self.current_option_price}")
                
        except Exception as e:
            logger.exception(f"Error entering position: {str(e)}")
            self.in_trade = False
            
    def _exit_position(self, reason):
        """
        Exit the current position
        
        Parameters:
        -----------
        reason : str
            Reason for exiting the position
        """
        if not self.in_trade:
            return
            
        exit_time = datetime.now()
        exit_price = self.target_price if reason == "Target Hit" else self.stop_loss_price
        pnl = self._calculate_pnl(exit_price)
        
        logger.info(f"Exiting position at {exit_price} due to {reason}. P&L: {pnl}")
        
        # In simulation mode, just log the intent
        if self.simulation_mode:
            logger.info(f"Simulation: Would sell {self.current_option}")
            exit_option_price = self.current_option_price * (1 + (0.1 if reason == "Target Hit" else -0.05))
        else:
            # In real trading mode, place the sell order
            try:
                # Get the current position details
                positions = self.api.get_position()
                position_found = False
                exit_option_price = self.current_option_price
                
                for position in positions:
                    if position['tradingsymbol'] == self.current_option:
                        position_found = True
                        
                        # Place the sell order
                        order_params = {
                            "variety": "NORMAL",
                            "tradingsymbol": position['tradingsymbol'],
                            "symboltoken": position['symboltoken'],
                            "transactiontype": "SELL",
                            "exchange": "NFO",
                            "ordertype": "MARKET",
                            "producttype": "INTRADAY",
                            "duration": "DAY",
                            "quantity": position['quantity']
                        }
                        
                        order_id = self.api.place_order(order_params)
                        
                        if not order_id:
                            logger.error("Failed to place sell order")
                            return
                            
                        logger.info(f"Sell order placed successfully: {order_id}")
                        
                        # Get the execution price
                        time.sleep(2)  # Wait for order execution
                        trade_book = self.api.get_trade_book()
                        
                        for trade in trade_book:
                            if trade['orderid'] == order_id:
                                exit_option_price = float(trade['averageprice'])
                                break
                        break
                        
                if not position_found:
                    logger.warning(f"Position {self.current_option} not found")
                    
            except Exception as e:
                logger.exception(f"Error exiting position: {str(e)}")
                exit_option_price = self.current_option_price
        
        # Record the trade
        trade_record = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'entry_time': self.entry_time.strftime('%H:%M:%S'),
            'entry_price': self.entry_price,
            'exit_time': exit_time.strftime('%H:%M:%S'),
            'exit_price': exit_price,
            'pnl': pnl,
            'outcome': reason,
            'setup_type': self.setup_type,
            'option': self.current_option,
            'option_entry_price': self.current_option_price,
            'option_exit_price': exit_option_price,
            'simulation': self.simulation_mode
        }
        
        self.trade_history.append(trade_record)
        self._save_trade_history()
        
        # Reset the state
        self.reset_state()
        
    def _find_option_with_premium(self, nifty_price, expiry_date, target_premium):
    """
    Find option with premium closest to target premium
    
    Parameters:
    -----------
    nifty_price : float
        Current Nifty price
    expiry_date : str
        Option expiry date
    target_premium : float
        Target option premium
        
    Returns:
    --------
    dict
        Option details
    """
    try:
        logger.info(f"Finding option with premium closest to ₹{target_premium} for Nifty at {nifty_price}")
        
        # Get the option chain from the API
        option_chain = self.api.get_option_chain("NIFTY", expiry_date)
        
        if not option_chain or len(option_chain) == 0:
            logger.error("Option chain not available - halting trade")
            return None
        
        # Process the real option chain
        best_option = None
        best_diff = float('inf')
        
        for option in option_chain:
            if 'last_price_CE' in option and option['last_price_CE'] > 0:
                diff = abs(option['last_price_CE'] - target_premium)
                
                if diff < best_diff:
                    best_diff = diff
                    best_option = {
                        'strike': option['strike'],
                        'premium': option['last_price_CE'],
                        'tradingsymbol': option['tradingsymbol_CE'],
                        'token': option['token_CE']
                    }
        
        if best_option is None:
            logger.error("No suitable option found in the chain")
            return None
            
        logger.info(f"Selected option: {best_option['tradingsymbol']}, Premium: ₹{best_option['premium']:.2f}, Diff: ₹{best_diff:.2f}")
        return best_option
        
    except Exception as e:
        logger.exception(f"Error finding option with premium: {str(e)}")
        return None
    
    
    def _calculate_pnl(self, exit_price):
        """
        Calculate the P&L for the trade
        
        Parameters:
        -----------
        exit_price : float
            Exit price (Nifty level)
            
        Returns:
        --------
        float
            P&L in rupees
        """
        # In actual implementation, would calculate based on option prices
        # Here we estimate based on Nifty movement
        nifty_points = exit_price - self.entry_price
        
        # Rough estimate: 1 Nifty point ≈ Rs. 75-100 per lot for ATM/ITM options
        option_value_change = nifty_points * 75  # Rs. 75 per Nifty point
        
        # Multiply by lot size
        pnl = option_value_change * self.settings['lot_size']
        
        return pnl
        
    def _on_price_update(self, data):
        """
        Callback for price updates from WebSocket
        
        Parameters:
        -----------
        data : dict
            Price data from WebSocket
        """
        try:
            # Process the price update
            if 'last_traded_price' in data:
                price = float(data['last_traded_price'])
                self._process_price(price)
        except Exception as e:
            logger.exception(f"Error processing price update: {str(e)}")
            
    def _load_trade_history(self):
        """Load trade history from file"""
        history_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'trade_history.json')
        
        try:
            if os.path.exists(history_file):
                with open(history_file, 'r') as f:
                    self.trade_history = json.load(f)
                logger.info(f"Loaded {len(self.trade_history)} trade records")
            else:
                logger.info("No trade history file found, starting with empty history")
                self.trade_history = []
        except Exception as e:
            logger.exception(f"Error loading trade history: {str(e)}")
            self.trade_history = []
            
    def _save_trade_history(self):
        """Save trade history to file"""
        try:
            # Create data directory if it doesn't exist
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
            os.makedirs(data_dir, exist_ok=True)
            
            history_file = os.path.join(data_dir, 'trade_history.json')
            
            with open(history_file, 'w') as f:
                json.dump(self.trade_history, f, indent=4)
                
            logger.info(f"Saved {len(self.trade_history)} trade records")
        except Exception as e:
            logger.exception(f"Error saving trade history: {str(e)}")