"""Configuration manager for MCP Docker Orchestrator."""

import json
import yaml
import os
import configparser
from typing import Dict, Any, Optional
from orchestrator.utils.logging import setup_logging

# Set up logger
logger = setup_logging(__name__)

class ConfigManager:
    """Handles loading and managing configuration for the MCP Orchestrator."""

    def __init__(self, compose_path: str = "mcp-compose.yaml", 
                 settings_path: str = "settings.conf"):
        """Initialize the ConfigManager.
        
        Args:
            compose_path: Path to the Docker Compose configuration file
            settings_path: Path to the settings file
        """
        self.compose_path = compose_path
        self.settings_path = settings_path
        self.compose_data = {}
        self.settings = {}
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from files."""
        self._load_compose_data()
        self._load_settings()
        logger.info("Configuration loaded successfully")

    def _load_compose_data(self) -> Dict[str, Any]:
        """Load Docker Compose configuration from YAML file."""
        try:
            if not os.path.exists(self.compose_path):
                logger.warning(f"Compose file {self.compose_path} not found, creating empty config")
                self.compose_data = {"version": "3", "services": {}}
                self._save_default_compose()
                return self.compose_data

            with open(self.compose_path, "r") as f:
                self.compose_data = yaml.safe_load(f) or {}
                
            # Validate structure
            if "services" not in self.compose_data:
                logger.warning("Invalid Docker Compose structure, missing 'services' key")
                self.compose_data = {"version": "3", "services": {}}
                self._save_default_compose()
            
            logger.info(f"Loaded {len(self.compose_data.get('services', {}))} service configurations")
            return self.compose_data
        
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse Docker Compose file: {str(e)}")
            self.compose_data = {"version": "3", "services": {}}
            return self.compose_data
        except Exception as e:
            logger.error(f"Error loading Docker Compose file: {str(e)}")
            self.compose_data = {"version": "3", "services": {}}
            return self.compose_data
            
    def load_compose_data(self) -> Dict[str, Any]:
        """Reload and return the Docker Compose data."""
        return self._load_compose_data()

    def _save_default_compose(self) -> None:
        """Save default Docker Compose configuration to file."""
        try:
            with open(self.compose_path, "w") as f:
                yaml.dump(self.compose_data, f, default_flow_style=False)
            
            logger.info(f"Default Docker Compose configuration saved to {self.compose_path}")
        
        except Exception as e:
            logger.error(f"Error saving default Docker Compose configuration: {str(e)}")

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
        """Get all configured MCP servers from Docker Compose configuration.
        
        Returns:
            Dictionary of MCP server configurations with metadata
        """
        servers = {}
        
        if not self.compose_data or 'services' not in self.compose_data:
            return servers
            
        for service_id, service_config in self.compose_data.get('services', {}).items():
            # Extract MCP-specific metadata from labels
            labels = service_config.get('labels', {})
            
            # Handle string format labels (convert to dict if needed)
            if isinstance(labels, list):
                label_dict = {}
                for label in labels:
                    if '=' in label:
                        key, value = label.split('=', 1)
                        label_dict[key] = value
                labels = label_dict
                
            # Extract metadata
            disabled = str(labels.get('mcp.disabled', "false")).lower() == "true"
            path = labels.get('mcp.path', f"/mcp/{service_id}")
            
            servers[service_id] = {
                'service_config': service_config,
                'disabled': disabled,
                'path': path
            }
                
        return servers

    def get_mcp_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific MCP server.
        
        Args:
            server_id: ID of the MCP server
            
        Returns:
            Server configuration or None if not found
        """
        servers = self.get_mcp_servers()
        return servers.get(server_id)

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
