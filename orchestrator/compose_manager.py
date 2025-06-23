"""Docker Compose manager for MCP Orchestrator."""

import os
import subprocess
import yaml
import re
import tempfile
import time
from typing import Dict, Any, List, Optional, Tuple

from orchestrator.utils.logging import setup_logging
from orchestrator.config_manager import ConfigManager

# Set up logger
logger = setup_logging(__name__)

class ComposeManager:
    """Manages Docker Compose for MCP services."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize the Compose Manager.
        
        Args:
            config_manager: The configuration manager instance
        """
        self.config_manager = config_manager
        self.compose_path = config_manager.compose_path
        self.port_allocations = {}  # Maps server_id -> host_port
        self._use_legacy_compose = False  # Flag to indicate whether to use docker-compose or docker compose
        self._check_docker_compose()
        
    def _check_docker_compose(self) -> None:
        """Check if docker compose is installed."""
        try:
            # Try modern docker compose (as plugin)
            result = subprocess.run(["docker", "compose", "--version"], 
                                  capture_output=True, text=True, check=True)
            logger.info(f"Using Docker Compose: {result.stdout.strip()}")
            return
        except FileNotFoundError:
            logger.warning("Docker command not found in PATH. Checking docker-compose...")
            # Log the PATH to help with debugging
            logger.info(f"Current PATH: {os.environ.get('PATH', 'Not set')}")
            try:
                # Try classic docker-compose as fallback
                result = subprocess.run(["docker-compose", "--version"],
                                      capture_output=True, text=True, check=True)
                logger.warning(f"Using legacy docker-compose: {result.stdout.strip()}")
                logger.warning("Please consider upgrading to Docker Compose V2")
                # Update all command methods to use docker-compose instead of docker compose
                self._use_legacy_compose = True
                return
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.error(f"docker-compose also not available: {str(e)}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error checking Docker Compose version: {str(e)}")
            if e.stderr:
                logger.error(f"Error output: {e.stderr}")
            
        # If we get here, no Docker Compose is available
        error_message = (
            "Docker Compose is required but not available. "
            "Please ensure Docker is installed and in your PATH. "
            "For systemd services, make sure the PATH includes /usr/bin and /usr/local/bin. "
            "You may need to restart the service after installing Docker."
        )
        logger.error(error_message)
        raise RuntimeError(error_message)
    
    def _service_exists(self, service_id: str) -> bool:
        """Check if a service exists in docker-compose.
        
        Args:
            service_id: The service ID
            
        Returns:
            True if service exists and is running, False otherwise
        """
        try:
            # Use docker compose ps to check if service is running
            cmd = ["docker-compose", "-f", self.compose_path, "ps", "--services", "--filter", f"name={service_id}"] if self._use_legacy_compose else \
                  ["docker", "compose", "-f", self.compose_path, "ps", "--services", "--filter", f"name={service_id}"]
                  
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            # If service is in the list, it exists
            return service_id in result.stdout.strip().split('\n')
        except Exception as e:
            logger.error(f"Error checking service existence: {str(e)}")
            return False
            
    def _update_port_for_server(self, service_id: str) -> Optional[int]:
        """Get and store the host port for a service.
        
        Args:
            service_id: The service ID
            
        Returns:
            Host port if found, None otherwise
        """
        try:
            # Get current directory name for the docker-compose project name
            dir_name = os.path.basename(os.path.dirname(os.path.abspath(self.compose_path)))
            container_name = f"{dir_name}-{service_id}-1"
            
            # Use docker inspect to get port mappings
            result = subprocess.run(
                ["docker", "inspect", "--format", 
                 "{{range $p, $conf := .NetworkSettings.Ports}}{{(index $conf 0).HostPort}}{{end}}", 
                 container_name],
                capture_output=True, text=True, check=False
            )
            
            # Extract port from output
            if result.returncode == 0 and result.stdout.strip():
                # Just take the first port if there are multiple
                port = int(result.stdout.strip().split()[0])
                self.port_allocations[service_id] = port
                logger.info(f"Updated port mapping for {service_id}: {port}")
                return port
                
        except Exception as e:
            logger.error(f"Failed to get port for {service_id}: {str(e)}")
            
        return None
        
    def get_service_info(self, service_id: str) -> Dict[str, Any]:
        """Get information about a service.
        
        Args:
            service_id: The service ID
            
        Returns:
            Dictionary with service information
        """
        try:
            # Check if service exists in compose file
            compose_data = self.config_manager.load_compose_data()
            if 'services' not in compose_data or service_id not in compose_data['services']:
                logger.warning(f"Service {service_id} not found in compose file")
                return {"exists": False}
            
            # Check if service is actually running
            if not self._service_exists(service_id):
                logger.warning(f"Service {service_id} exists in config but is not running")
                return {"exists": False}
                
            # Get service container details
            dir_name = os.path.basename(os.path.dirname(os.path.abspath(self.compose_path)))
            container_name = f"{dir_name}-{service_id}-1"
            
            # Get container info using docker inspect
            inspect_result = subprocess.run(
                ["docker", "inspect", container_name],
                capture_output=True, text=True, check=False
            )
            
            if inspect_result.returncode != 0:
                logger.warning(f"Could not inspect container for {service_id}")
                return {"exists": False}
                
            # Parse container info
            container_info = yaml.safe_load(inspect_result.stdout)[0]
            
            # Extract relevant information
            status = container_info["State"]["Status"]
            running = container_info["State"]["Running"]
            health = container_info.get("State", {}).get("Health", {}).get("Status", "unknown")
            
            # Get port
            host_port = self.port_allocations.get(service_id)
            if host_port is None:
                host_port = self._update_port_for_server(service_id)
            
            return {
                "exists": True,
                "id": container_info["Id"],
                "status": status,
                "running": running,
                "health": health,
                "host_port": host_port,
                "created": container_info["Created"],
                "image": container_info["Config"]["Image"]
            }
            
        except Exception as e:
            logger.error(f"Failed to get service info for {service_id}: {str(e)}")
            return {"exists": False, "error": str(e)}
    
    def start_service(self, service_id: str) -> bool:
        """Start a service using docker-compose.
        
        Args:
            service_id: The service ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if service exists in compose file
            compose_data = self.config_manager.load_compose_data()
            if 'services' not in compose_data or service_id not in compose_data['services']:
                logger.warning(f"Service {service_id} not found in compose file")
                return False
                
            # Start the service
            cmd = ["docker-compose", "-f", self.compose_path, "up", "-d", service_id] if self._use_legacy_compose else \
                  ["docker", "compose", "-f", self.compose_path, "up", "-d", service_id]
                  
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                logger.error(f"Failed to start service {service_id}: {result.stderr}")
                return False
                
            logger.info(f"Started service {service_id}")
            
            # Update port allocation
            self._update_port_for_server(service_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting service {service_id}: {str(e)}")
            return False
    
    def stop_service(self, service_id: str) -> bool:
        """Stop a service using docker-compose.
        
        Args:
            service_id: The service ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Stop the service
            cmd = ["docker-compose", "-f", self.compose_path, "stop", service_id] if self._use_legacy_compose else \
                  ["docker", "compose", "-f", self.compose_path, "stop", service_id]
                  
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                logger.error(f"Failed to stop service {service_id}: {result.stderr}")
                return False
                
            logger.info(f"Stopped service {service_id}")
            
            # Remove port allocation
            if service_id in self.port_allocations:
                del self.port_allocations[service_id]
                
            return True
            
        except Exception as e:
            logger.error(f"Error stopping service {service_id}: {str(e)}")
            return False
    
    def restart_service(self, service_id: str) -> bool:
        """Restart a service using docker-compose.
        
        Args:
            service_id: The service ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Restart the service
            cmd = ["docker-compose", "-f", self.compose_path, "restart", service_id] if self._use_legacy_compose else \
                  ["docker", "compose", "-f", self.compose_path, "restart", service_id]
                  
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                logger.error(f"Failed to restart service {service_id}: {result.stderr}")
                return False
                
            logger.info(f"Restarted service {service_id}")
            
            # Update port allocation
            self._update_port_for_server(service_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error restarting service {service_id}: {str(e)}")
            return False
    
    def sync_services(self) -> Dict[str, Any]:
        """Synchronize services with the MCP Compose configuration.
        
        Returns:
            Dictionary with synchronization results
        """
        results = {
            "created": [],
            "updated": [],
            "stopped": [],
            "errors": []
        }
        
        try:
            # Get MCP service configurations
            mcp_services = self.config_manager.get_mcp_servers()
            
            # Process each MCP service
            for service_id, service_meta in mcp_services.items():
                try:
                    if service_meta.get('disabled', False):
                        # Service is disabled, stop it if it exists
                        if self._service_exists(service_id):
                            if self.stop_service(service_id):
                                results["stopped"].append(service_id)
                        continue
                        
                    # Start or update service
                    if not self._service_exists(service_id):
                        # Service doesn't exist, start it
                        if self.start_service(service_id):
                            results["created"].append(service_id)
                    else:
                        # Service exists, restart it to apply any config changes
                        if self.restart_service(service_id):
                            results["updated"].append(service_id)
                
                except Exception as e:
                    logger.error(f"Error processing service {service_id}: {str(e)}")
                    results["errors"].append(f"{service_id}: {str(e)}")
            
            # Clean up services not in config
            compose_data = self.config_manager.load_compose_data()
            running_services = self._get_running_services()
            
            for service_id in running_services:
                if service_id not in mcp_services and service_id in compose_data.get('services', {}):
                    try:
                        if self.stop_service(service_id):
                            results["stopped"].append(service_id)
                    except Exception as e:
                        logger.error(f"Error stopping orphaned service {service_id}: {str(e)}")
            
            logger.info(f"Service sync complete: {len(results['created'])} created, " 
                        f"{len(results['updated'])} updated, {len(results['stopped'])} stopped")
            return results
            
        except Exception as e:
            logger.error(f"Failed to synchronize services: {str(e)}")
            results["errors"].append(f"General error: {str(e)}")
            return results
            
    def _get_running_services(self) -> List[str]:
        """Get list of currently running services.
        
        Returns:
            List of service IDs
        """
        try:
            cmd = ["docker-compose", "-f", self.compose_path, "ps", "--services"] if self._use_legacy_compose else \
                  ["docker", "compose", "-f", self.compose_path, "ps", "--services"]
                  
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                logger.error(f"Failed to list services: {result.stderr}")
                return []
                
            # Parse output
            services = [s for s in result.stdout.strip().split('\n') if s]
            return services
            
        except Exception as e:
            logger.error(f"Error listing services: {str(e)}")
            return []
    
    def get_all_service_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all MCP services.
        
        Returns:
            Dictionary mapping service IDs to service information
        """
        info = {}
        
        # Get MCP service configurations
        mcp_services = self.config_manager.get_mcp_servers()
        
        # Get info for each service
        for service_id in mcp_services.keys():
            info[service_id] = self.get_service_info(service_id)
            
        return info
    
    def get_port_for_server(self, server_id: str) -> Optional[int]:
        """Get the host port assigned to a server.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            Port number if found, None otherwise
        """
        # First check cache
        if server_id in self.port_allocations:
            return self.port_allocations[server_id]
        
        # Try to get from container
        return self._update_port_for_server(server_id)
