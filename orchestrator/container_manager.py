"""Docker container manager for MCP Orchestrator."""

import time
import docker
from docker.errors import DockerException, NotFound
from typing import Dict, Any, List, Optional, Tuple
import socket
from tenacity import retry, stop_after_attempt, wait_exponential

from orchestrator.utils.logging import setup_logging
from orchestrator.config_manager import ConfigManager

# Set up logger
logger = setup_logging(__name__)

class ContainerManager:
    """Manages Docker containers for MCP services."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize the Container Manager.
        
        Args:
            config_manager: The configuration manager instance
        """
        self.config_manager = config_manager
        self.client = None
        self.port_allocations = {}  # Maps server_id -> host_port
        self._connect_docker()
        
    def _connect_docker(self) -> None:
        """Connect to Docker daemon."""
        try:
            self.client = docker.from_env()
            # Test connection
            self.client.ping()
            logger.info("Connected to Docker daemon")
        except DockerException as e:
            logger.error(f"Failed to connect to Docker daemon: {str(e)}")
            raise

    def _find_available_port(self) -> int:
        """Find an available port on the host.
        
        Returns:
            An available port number
        """
        port_range_start = int(self.config_manager.get_setting("service", "port_range_start", 8000))
        port_range_end = int(self.config_manager.get_setting("service", "port_range_end", 9000))
        
        # Check already allocated ports
        allocated_ports = set(self.port_allocations.values())
        
        # Try ports in the configured range
        for port in range(port_range_start, port_range_end + 1):
            if port in allocated_ports:
                continue
                
            # Check if port is available
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('localhost', port)) != 0:
                    # Port is available
                    return port
        
        # No available ports found
        raise RuntimeError(f"No available ports in range {port_range_start}-{port_range_end}")

    def _get_container_name(self, server_id: str) -> str:
        """Generate a standardized container name for a server ID.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            A container name
        """
        return f"mcp-{server_id}"

    def _parse_docker_command(self, config: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Parse Docker command from MCP server configuration.
        
        Args:
            config: MCP server configuration
            
        Returns:
            Tuple of (image, command_args)
        """
        if config.get("command") != "docker":
            raise ValueError(f"Unsupported command: {config.get('command')}")
            
        args = config.get("args", [])
        if not args or "run" not in args:
            raise ValueError("Invalid Docker command format")
            
        # Extract the image name
        run_index = args.index("run")
        image_index = None
        
        for i in range(run_index + 1, len(args)):
            # Skip options and their values
            if args[i].startswith("-"):
                continue
            if i > 0 and args[i-1].startswith("-") and not args[i-1].startswith("--"):
                continue
                
            # Found the image name
            image_index = i
            break
            
        if image_index is None:
            raise ValueError("Could not find Docker image in command")
            
        image = args[image_index]
        
        # Create command args (exclude 'docker', 'run', and the image)
        command_args = args[1:run_index] + args[run_index+1:image_index] + args[image_index+1:]
        
        return image, command_args

    def _container_exists(self, container_name: str) -> bool:
        """Check if a container with the given name exists.
        
        Args:
            container_name: Name of the container to check
            
        Returns:
            True if container exists, False otherwise
        """
        try:
            self.client.containers.get(container_name)
            return True
        except NotFound:
            return False
        except Exception as e:
            logger.error(f"Error checking container existence: {str(e)}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_container(self, server_id: str, config: Dict[str, Any]) -> Optional[str]:
        """Create and start a Docker container for an MCP server.
        
        Args:
            server_id: The MCP server ID
            config: The MCP server configuration
            
        Returns:
            Container ID if successful, None otherwise
        """
        try:
            if config.get("disabled", False):
                logger.info(f"Server {server_id} is disabled, skipping")
                return None
                
            container_name = self._get_container_name(server_id)
            
            # Check if container already exists
            if self._container_exists(container_name):
                logger.info(f"Container {container_name} already exists")
                return self.client.containers.get(container_name).id
                
            # Parse Docker command
            image, command_args = self._parse_docker_command(config)
            
            # Find available port and update port allocations
            host_port = self._find_available_port()
            self.port_allocations[server_id] = host_port
            
            # Set up port mapping (assuming container exposes port 8080)
            container_port = 8080
            ports = {f"{container_port}/tcp": host_port}
            
            # Set up environment variables
            env_dict = config.get("env", {})
            
            # Create and start container
            container = self.client.containers.run(
                image=image,
                name=container_name,
                detach=True,
                ports=ports,
                environment=env_dict,
                restart_policy={"Name": "always"},
                labels={
                    "mcp_service": server_id,
                    "managed_by": "mcp-orchestrator"
                }
            )
            
            logger.info(f"Created container for {server_id} with ID {container.id}")
            return container.id
            
        except Exception as e:
            logger.error(f"Failed to create container for {server_id}: {str(e)}")
            return None

    def stop_container(self, server_id: str) -> bool:
        """Stop and remove a container.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            container_name = self._get_container_name(server_id)
            
            # Check if container exists
            if not self._container_exists(container_name):
                logger.info(f"Container {container_name} does not exist")
                return True
                
            # Get container
            container = self.client.containers.get(container_name)
            
            # Stop and remove container
            container.stop(timeout=10)
            container.remove()
            
            # Remove port allocation
            if server_id in self.port_allocations:
                del self.port_allocations[server_id]
                
            logger.info(f"Stopped and removed container {container_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop container for {server_id}: {str(e)}")
            return False

    def restart_container(self, server_id: str) -> bool:
        """Restart a container.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            container_name = self._get_container_name(server_id)
            
            # Check if container exists
            if not self._container_exists(container_name):
                logger.warning(f"Container {container_name} does not exist, cannot restart")
                return False
                
            # Get container
            container = self.client.containers.get(container_name)
            
            # Restart container
            container.restart(timeout=10)
            logger.info(f"Restarted container {container_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart container for {server_id}: {str(e)}")
            return False

    def get_container_info(self, server_id: str) -> Dict[str, Any]:
        """Get information about a container.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            Dictionary with container information
        """
        try:
            container_name = self._get_container_name(server_id)
            
            # Check if container exists
            if not self._container_exists(container_name):
                logger.warning(f"Container {container_name} does not exist")
                return {"exists": False}
                
            # Get container
            container = self.client.containers.get(container_name)
            
            # Get container info
            container_info = container.attrs
            
            # Extract relevant information
            status = container_info["State"]["Status"]
            running = container_info["State"]["Running"]
            health = container_info.get("State", {}).get("Health", {}).get("Status", "unknown")
            host_port = self.port_allocations.get(server_id)
            
            return {
                "exists": True,
                "id": container.id,
                "status": status,
                "running": running,
                "health": health,
                "host_port": host_port,
                "created": container_info["Created"],
                "image": container_info["Config"]["Image"]
            }
            
        except Exception as e:
            logger.error(f"Failed to get container info for {server_id}: {str(e)}")
            return {"exists": False, "error": str(e)}

    def sync_containers(self) -> Dict[str, Any]:
        """Synchronize containers with the MCP server configuration.
        
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
            # Get MCP server configurations
            mcp_servers = self.config_manager.get_mcp_servers()
            
            # Track existing containers
            existing_containers = []
            
            # Process each MCP server
            for server_id, config in mcp_servers.items():
                try:
                    container_name = self._get_container_name(server_id)
                    existing_containers.append(container_name)
                    
                    if config.get("disabled", False):
                        # Server is disabled, stop container if it exists
                        if self._container_exists(container_name):
                            self.stop_container(server_id)
                            results["stopped"].append(server_id)
                        continue
                        
                    # Create or update container
                    if not self._container_exists(container_name):
                        if self.create_container(server_id, config):
                            results["created"].append(server_id)
                    else:
                        # Container exists, check if config has changed
                        # For now, just restart the container (in future could check for config changes)
                        if self.restart_container(server_id):
                            results["updated"].append(server_id)
                
                except Exception as e:
                    logger.error(f"Error processing server {server_id}: {str(e)}")
                    results["errors"].append(f"{server_id}: {str(e)}")
            
            # Find and remove orphaned containers
            try:
                all_containers = self.client.containers.list(all=True, filters={"label": "managed_by=mcp-orchestrator"})
                
                for container in all_containers:
                    if container.name not in existing_containers:
                        logger.info(f"Found orphaned container {container.name}, removing")
                        container.stop(timeout=10)
                        container.remove()
                        results["stopped"].append(container.name)
                        
            except Exception as e:
                logger.error(f"Error cleaning up orphaned containers: {str(e)}")
            
            logger.info(f"Container sync complete: {len(results['created'])} created, {len(results['updated'])} updated, {len(results['stopped'])} stopped")
            return results
            
        except Exception as e:
            logger.error(f"Failed to synchronize containers: {str(e)}")
            results["errors"].append(f"General error: {str(e)}")
            return results

    def get_all_container_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all MCP containers.
        
        Returns:
            Dictionary mapping server IDs to container information
        """
        info = {}
        
        # Get MCP server configurations
        mcp_servers = self.config_manager.get_mcp_servers()
        
        # Get info for each server
        for server_id in mcp_servers.keys():
            info[server_id] = self.get_container_info(server_id)
            
        return info

    def get_port_for_server(self, server_id: str) -> Optional[int]:
        """Get the host port assigned to a server.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            Port number if found, None otherwise
        """
        return self.port_allocations.get(server_id)
