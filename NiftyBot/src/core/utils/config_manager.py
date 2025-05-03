#!/usr/bin/env python3
# Configuration manager utility

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger('app.utils')

class ConfigManager:
    """
    Manages application configuration and settings
    """
    
    def __init__(self):
        """Initialize the configuration manager"""
        self.app_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.config_dir = os.path.join(self.app_dir, 'data')
        self.settings_file = os.path.join(self.config_dir, 'settings.json')
        
        # Create config directory if it doesn't exist
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Default strategy settings
        self.default_settings = {
            'trigger_level': 70,
            'execution_level': 95,
            'target_points': 20,
            'stop_loss': 25,
            'strike_distance': 200,
            'lot_size': 1,
            'update_interval': 1  # in seconds
        }
        
        # Initialize settings
        self.settings = self._load_settings()
        
    def _load_settings(self):
        """
        Load settings from file
        
        Returns:
        --------
        dict
            Settings dictionary
        """
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                logger.info(f"Settings loaded from {self.settings_file}")
                return settings
            else:
                # Create default settings
                self._save_settings(self.default_settings)
                logger.info(f"Default settings created at {self.settings_file}")
                return self.default_settings
        except Exception as e:
            logger.exception(f"Error loading settings: {str(e)}")
            return self.default_settings
            
    def _save_settings(self, settings):
        """
        Save settings to file
        
        Parameters:
        -----------
        settings : dict
            Settings to save
        """
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
            logger.info(f"Settings saved to {self.settings_file}")
        except Exception as e:
            logger.exception(f"Error saving settings: {str(e)}")
            
    def get_strategy_settings(self):
        """
        Get strategy settings
        
        Returns:
        --------
        dict
            Strategy settings
        """
        return self.settings
        
    def save_strategy_settings(self, settings):
        """
        Save strategy settings
        
        Parameters:
        -----------
        settings : dict
            Strategy settings to save
            
        Returns:
        --------
        bool
            True if successful, False otherwise
        """
        try:
            # Update with provided settings
            for key, value in settings.items():
                self.settings[key] = value
                
            # Save to file
            self._save_settings(self.settings)
            return True
        except Exception as e:
            logger.exception(f"Error saving strategy settings: {str(e)}")
            return False
            
    def get_latest_logs(self, count=100):
        """
        Get the latest log entries
        
        Parameters:
        -----------
        count : int, optional
            Number of log entries to return (default is 100)
            
        Returns:
        --------
        list
            List of log entries
        """
        try:
            logs_folder = os.path.join(self.app_dir, 'logs')
            today = datetime.now().strftime('%Y%m%d')
            log_file = os.path.join(logs_folder, f"app_{today}.log")
            
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    
                # Return the last 'count' lines
                return lines[-count:] if len(lines) > count else lines
            else:
                return ["No logs found"]
        except Exception as e:
            logger.exception(f"Error getting logs: {str(e)}")
            return [f"Error getting logs: {str(e)}"]