"""Configuration manager for MCP Docker Orchestrator."""

import json
import os
import configparser
from typing import Dict, Any, Optional
from orchestrator.utils.logging import setup_logging

# Set up logger
logger = setup_logging(__name__)

class ConfigManager:
    """Handles loading and managing configuration for the MCP Orchestrator."""

    def __init__(self, mcp_config_path: str = "mcp.config.json", 
                 settings_path: str = "settings.conf"):
        """Initialize the ConfigManager.
        
        Args:
            mcp_config_path: Path to the MCP configuration file
            settings_path: Path to the settings file
        """
        self.mcp_config_path = mcp_config_path
        self.settings_path = settings_path
        self.mcp_config = {}
        self.settings = {}
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from files."""
        self._load_mcp_config()
        self._load_settings()
        logger.info("Configuration loaded successfully")

    def _load_mcp_config(self) -> None:
        """Load MCP server configuration from JSON file."""
        try:
            if not os.path.exists(self.mcp_config_path):
                logger.warning(f"MCP config file {self.mcp_config_path} not found, creating empty config")
                self.mcp_config = {"mcpServers": {}}
                return

            with open(self.mcp_config_path, "r") as f:
                self.mcp_config = json.load(f)
                
            # Validate structure
            if "mcpServers" not in self.mcp_config:
                logger.warning("Invalid MCP config structure, missing 'mcpServers' key")
                self.mcp_config = {"mcpServers": {}}
            
            logger.info(f"Loaded {len(self.mcp_config.get('mcpServers', {}))} MCP server configurations")
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse MCP config file: {str(e)}")
            self.mcp_config = {"mcpServers": {}}
        except Exception as e:
            logger.error(f"Error loading MCP config: {str(e)}")
            self.mcp_config = {"mcpServers": {}}

    def _load_settings(self) -> None:
        """Load settings from configuration file."""
        try:
            config = configparser.ConfigParser()
            
            # Define default settings
            self.settings = {
                "aws": {
                    "region": "us-west-2",
                    "alb_arn": "",
                    "listener_arn": "",
                    "vpc_id": ""
                },
                "service": {
                    "reconciliation_interval_seconds": 60,
                    "port_range_start": 8000,
                    "port_range_end": 9000
                },
                "dashboard": {
                    "username": "admin",
                    "password": "changeme",
                    "path": "/monitor"
                },
                "logging": {
                    "level": "INFO"
                }
            }
            
            # Load from file if exists
            if os.path.exists(self.settings_path) and os.path.getsize(self.settings_path) > 0:
                config.read(self.settings_path)
                
                # Update settings from file
                if "aws" in config:
                    self.settings["aws"].update({k: v for k, v in config["aws"].items()})
                if "service" in config:
                    self.settings["service"].update({k: v for k, v in config["service"].items()})
                if "dashboard" in config:
                    self.settings["dashboard"].update({k: v for k, v in config["dashboard"].items()})
                if "logging" in config:
                    self.settings["logging"].update({k: v for k, v in config["logging"].items()})
                
                logger.info("Settings loaded from file")
            else:
                logger.warning(f"Settings file {self.settings_path} not found or empty, using defaults")
                # Create default settings file
                self._save_default_settings()
        
        except Exception as e:
            logger.error(f"Error loading settings: {str(e)}")

    def _save_default_settings(self) -> None:
        """Save default settings to file."""
        try:
            config = configparser.ConfigParser()
            
            # Convert settings dictionary to ConfigParser format
            for section, values in self.settings.items():
                config[section] = {k: str(v) for k, v in values.items()}
            
            # Write to file
            with open(self.settings_path, "w") as f:
                config.write(f)
            
            logger.info(f"Default settings saved to {self.settings_path}")
        
        except Exception as e:
            logger.error(f"Error saving default settings: {str(e)}")

    def get_mcp_servers(self) -> Dict[str, Any]:
        """Get all configured MCP servers.
        
        Returns:
            Dictionary of MCP server configurations
        """
        return self.mcp_config.get("mcpServers", {})

    def get_mcp_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific MCP server.
        
        Args:
            server_id: ID of the MCP server
            
        Returns:
            Server configuration or None if not found
        """
        return self.mcp_config.get("mcpServers", {}).get(server_id)

    def get_setting(self, section: str, key: str, default: Any = None) -> Any:
        """Get a specific setting value.
        
        Args:
            section: Settings section name
            key: Setting key
            default: Default value if setting is not found
            
        Returns:
            Setting value or default if not found
        """
        return self.settings.get(section, {}).get(key, default)
