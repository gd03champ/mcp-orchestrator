"""AWS ALB manager for MCP Orchestrator."""

import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential
from orchestrator.utils.logging import setup_logging
from orchestrator.config_manager import ConfigManager
from orchestrator.container_manager import ContainerManager

# Set up logger
logger = setup_logging(__name__)

class ALBManager:
    """Manages AWS ALB resources for MCP services."""

    def __init__(self, config_manager: ConfigManager, container_manager: ContainerManager):
        """Initialize the ALB Manager.
        
        Args:
            config_manager: The configuration manager instance
            container_manager: The container manager instance
        """
        self.config_manager = config_manager
        self.container_manager = container_manager
        self.client = None
        self.target_groups = {}  # Maps server_id -> target group ARN
        self._connect_aws()
    
    def _connect_aws(self) -> None:
        """Connect to AWS ELB service."""
        try:
            region = self.config_manager.get_setting("aws", "region", "us-west-2")
            self.client = boto3.client('elbv2', region_name=region)
            logger.info(f"Connected to AWS ELB service in {region}")
        except Exception as e:
            logger.error(f"Failed to connect to AWS ELB service: {str(e)}")
            raise
    
    def _get_target_group_name(self, server_id: str) -> str:
        """Generate a standardized target group name for a server ID.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            A target group name
        """
        # Replace non-alphanumeric characters with dashes and limit length to 32 chars
        clean_id = ''.join(c if c.isalnum() else '-' for c in server_id)
        return f"tg-mcp-{clean_id}"[:32]
    
    def _get_listener_arn(self) -> str:
        """Get the ALB listener ARN from configuration.
        
        Returns:
            ALB listener ARN
        """
        listener_arn = self.config_manager.get_setting("aws", "listener_arn", "")
        if not listener_arn:
            raise ValueError("Missing required configuration: aws.listener_arn")
        return listener_arn
    
    def _get_vpc_id(self) -> str:
        """Get the VPC ID from configuration.
        
        Returns:
            VPC ID
        """
        vpc_id = self.config_manager.get_setting("aws", "vpc_id", "")
        if not vpc_id:
            raise ValueError("Missing required configuration: aws.vpc_id")
        return vpc_id
    
    def _get_path_pattern(self, server_id: str) -> str:
        """Generate the path pattern for a server ID.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            Path pattern for ALB routing
        """
        return f"/mcp/{server_id}/*"
    
    def _target_group_exists(self, target_group_name: str) -> Optional[str]:
        """Check if a target group with the given name exists.
        
        Args:
            target_group_name: Name of the target group to check
            
        Returns:
            Target group ARN if it exists, None otherwise
        """
        try:
            response = self.client.describe_target_groups(Names=[target_group_name])
            if response.get('TargetGroups') and len(response['TargetGroups']) > 0:
                return response['TargetGroups'][0]['TargetGroupArn']
            return None
        except ClientError as e:
            if e.response['Error']['Code'] == 'TargetGroupNotFound':
                return None
            logger.error(f"Error checking target group existence: {str(e)}")
            raise
    
    def _rule_exists_for_path(self, path_pattern: str) -> Optional[Dict[str, Any]]:
        """Check if a rule exists for the given path pattern.
        
        Args:
            path_pattern: Path pattern to check
            
        Returns:
            Rule details if it exists, None otherwise
        """
        try:
            listener_arn = self._get_listener_arn()
            response = self.client.describe_rules(ListenerArn=listener_arn)
            
            for rule in response.get('Rules', []):
                for condition in rule.get('Conditions', []):
                    if condition.get('Field') == 'path-pattern':
                        for value in condition.get('Values', []):
                            if value == path_pattern:
                                return {
                                    'RuleArn': rule['RuleArn'],
                                    'Priority': rule['Priority'],
                                    'Actions': rule['Actions']
                                }
            return None
        except ClientError as e:
            logger.error(f"Error checking rule existence: {str(e)}")
            raise
    
    def _get_next_available_priority(self) -> int:
        """Get the next available rule priority.
        
        Returns:
            Next available priority
        """
        try:
            listener_arn = self._get_listener_arn()
            response = self.client.describe_rules(ListenerArn=listener_arn)
            
            priorities = []
            for rule in response.get('Rules', []):
                # Skip default rule (priority is "default")
                if rule['Priority'] != 'default':
                    priorities.append(int(rule['Priority']))
            
            if not priorities:
                return 1
            
            # Find the first available priority
            priorities.sort()
            for i in range(1, priorities[-1] + 2):
                if i not in priorities:
                    return i
            
            return priorities[-1] + 1
        except ClientError as e:
            logger.error(f"Error getting next available priority: {str(e)}")
            # Fallback to a high priority
            return 1000
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_target_group(self, server_id: str) -> Optional[str]:
        """Create a target group for an MCP server.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            Target group ARN if successful, None otherwise
        """
        try:
            target_group_name = self._get_target_group_name(server_id)
            
            # Check if target group already exists
            existing_arn = self._target_group_exists(target_group_name)
            if existing_arn:
                logger.info(f"Target group {target_group_name} already exists")
                self.target_groups[server_id] = existing_arn
                return existing_arn
            
            # Get port for server
            port = self.container_manager.get_port_for_server(server_id)
            if not port:
                logger.error(f"No port found for server {server_id}")
                return None
            
            # Create target group
            response = self.client.create_target_group(
                Name=target_group_name,
                Protocol='HTTP',
                Port=port,
                VpcId=self._get_vpc_id(),
                TargetType='instance',
                HealthCheckPath='/health',
                HealthCheckIntervalSeconds=30,
                HealthCheckTimeoutSeconds=5,
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=2,
                Matcher={'HttpCode': '200-299'}
            )
            
            if not response.get('TargetGroups') or len(response['TargetGroups']) == 0:
                logger.error(f"Failed to create target group for {server_id}")
                return None
            
            target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
            logger.info(f"Created target group {target_group_name} with ARN {target_group_arn}")
            
            # Store target group ARN
            self.target_groups[server_id] = target_group_arn
            
            # Add tags
            self.client.add_tags(
                ResourceArns=[target_group_arn],
                Tags=[
                    {'Key': 'Name', 'Value': target_group_name},
                    {'Key': 'ManagedBy', 'Value': 'mcp-orchestrator'},
                    {'Key': 'MCPService', 'Value': server_id}
                ]
            )
            
            return target_group_arn
        except Exception as e:
            logger.error(f"Failed to create target group for {server_id}: {str(e)}")
            return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def register_target(self, server_id: str) -> bool:
        """Register the EC2 instance as a target in the target group.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get target group ARN
            target_group_arn = self.target_groups.get(server_id)
            if not target_group_arn:
                target_group_arn = self.create_target_group(server_id)
                if not target_group_arn:
                    logger.error(f"No target group found for server {server_id}")
                    return False
            
            # Get port for server
            port = self.container_manager.get_port_for_server(server_id)
            if not port:
                logger.error(f"No port found for server {server_id}")
                return False
            
            # Get EC2 instance ID (assuming running on EC2)
            instance_id = self._get_instance_id()
            if not instance_id:
                logger.error("Failed to get EC2 instance ID")
                return False
            
            # Register target
            self.client.register_targets(
                TargetGroupArn=target_group_arn,
                Targets=[
                    {
                        'Id': instance_id,
                        'Port': port
                    }
                ]
            )
            
            logger.info(f"Registered instance {instance_id}:{port} with target group for {server_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to register target for {server_id}: {str(e)}")
            return False
    
    def _get_instance_id(self) -> Optional[str]:
        """Get the EC2 instance ID of the current instance.
        
        Returns:
            Instance ID if running on EC2, None otherwise
        """
        try:
            # Try to get instance ID from EC2 metadata service
            import requests
            response = requests.get('http://169.254.169.254/latest/meta-data/instance-id', timeout=2)
            if response.status_code == 200:
                return response.text
            
            # If not running on EC2, use a dummy instance ID for testing
            logger.warning("Not running on EC2, using dummy instance ID")
            return "i-dummy"
        except Exception as e:
            logger.error(f"Failed to get EC2 instance ID: {str(e)}")
            # Use dummy instance ID as fallback
            return "i-dummy"
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def create_listener_rule(self, server_id: str) -> Optional[str]:
        """Create a listener rule for an MCP server.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            Rule ARN if successful, None otherwise
        """
        try:
            # Get target group ARN
            target_group_arn = self.target_groups.get(server_id)
            if not target_group_arn:
                target_group_arn = self.create_target_group(server_id)
                if not target_group_arn:
                    logger.error(f"No target group found for server {server_id}")
                    return None
            
            # Get path pattern
            path_pattern = self._get_path_pattern(server_id)
            
            # Check if rule already exists
            existing_rule = self._rule_exists_for_path(path_pattern)
            if existing_rule:
                logger.info(f"Rule already exists for path {path_pattern}")
                
                # Check if the rule points to the correct target group
                for action in existing_rule.get('Actions', []):
                    if action.get('Type') == 'forward' and action.get('TargetGroupArn') == target_group_arn:
                        # Rule already points to the correct target group
                        return existing_rule['RuleArn']
                
                # Update rule to point to the correct target group
                self.client.modify_rule(
                    RuleArn=existing_rule['RuleArn'],
                    Actions=[
                        {
                            'Type': 'forward',
                            'TargetGroupArn': target_group_arn
                        }
                    ]
                )
                
                logger.info(f"Updated rule for path {path_pattern} to point to target group for {server_id}")
                return existing_rule['RuleArn']
            
            # Get listener ARN
            listener_arn = self._get_listener_arn()
            
            # Create rule
            response = self.client.create_rule(
                ListenerArn=listener_arn,
                Priority=self._get_next_available_priority(),
                Conditions=[
                    {
                        'Field': 'path-pattern',
                        'Values': [path_pattern]
                    }
                ],
                Actions=[
                    {
                        'Type': 'forward',
                        'TargetGroupArn': target_group_arn
                    }
                ]
            )
            
            if not response.get('Rules') or len(response['Rules']) == 0:
                logger.error(f"Failed to create listener rule for {server_id}")
                return None
            
            rule_arn = response['Rules'][0]['RuleArn']
            logger.info(f"Created listener rule for path {path_pattern} with ARN {rule_arn}")
            
            return rule_arn
        except Exception as e:
            logger.error(f"Failed to create listener rule for {server_id}: {str(e)}")
            return None
    
    def delete_rule_for_server(self, server_id: str) -> bool:
        """Delete the listener rule for an MCP server.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get path pattern
            path_pattern = self._get_path_pattern(server_id)
            
            # Check if rule exists
            existing_rule = self._rule_exists_for_path(path_pattern)
            if not existing_rule:
                logger.info(f"No rule found for path {path_pattern}")
                return True
            
            # Delete rule
            self.client.delete_rule(
                RuleArn=existing_rule['RuleArn']
            )
            
            logger.info(f"Deleted listener rule for path {path_pattern}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete listener rule for {server_id}: {str(e)}")
            return False
    
    def delete_target_group_for_server(self, server_id: str) -> bool:
        """Delete the target group for an MCP server.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            target_group_name = self._get_target_group_name(server_id)
            
            # Check if target group exists
            target_group_arn = self._target_group_exists(target_group_name)
            if not target_group_arn:
                logger.info(f"Target group {target_group_name} does not exist")
                return True
            
            # Delete target group
            self.client.delete_target_group(
                TargetGroupArn=target_group_arn
            )
            
            # Remove from cache
            if server_id in self.target_groups:
                del self.target_groups[server_id]
            
            logger.info(f"Deleted target group {target_group_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete target group for {server_id}: {str(e)}")
            return False
    
    def setup_alb_for_server(self, server_id: str) -> Dict[str, Any]:
        """Set up ALB resources for an MCP server.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            Dictionary with setup results
        """
        results = {
            "target_group_created": False,
            "target_registered": False,
            "rule_created": False,
            "errors": []
        }
        
        try:
            # Create target group
            target_group_arn = self.create_target_group(server_id)
            if not target_group_arn:
                results["errors"].append("Failed to create target group")
                return results
            
            results["target_group_created"] = True
            
            # Register target
            if not self.register_target(server_id):
                results["errors"].append("Failed to register target")
                return results
            
            results["target_registered"] = True
            
            # Create listener rule
            rule_arn = self.create_listener_rule(server_id)
            if not rule_arn:
                results["errors"].append("Failed to create listener rule")
                return results
            
            results["rule_created"] = True
            
            logger.info(f"Successfully set up ALB resources for {server_id}")
            return results
        except Exception as e:
            logger.error(f"Failed to set up ALB resources for {server_id}: {str(e)}")
            results["errors"].append(str(e))
            return results
    
    def cleanup_alb_for_server(self, server_id: str) -> Dict[str, Any]:
        """Clean up ALB resources for an MCP server.
        
        Args:
            server_id: The MCP server ID
            
        Returns:
            Dictionary with cleanup results
        """
        results = {
            "rule_deleted": False,
            "target_group_deleted": False,
            "errors": []
        }
        
        try:
            # Delete listener rule
            if self.delete_rule_for_server(server_id):
                results["rule_deleted"] = True
            else:
                results["errors"].append("Failed to delete listener rule")
            
            # Delete target group
            if self.delete_target_group_for_server(server_id):
                results["target_group_deleted"] = True
            else:
                results["errors"].append("Failed to delete target group")
            
            logger.info(f"Cleaned up ALB resources for {server_id}")
            return results
        except Exception as e:
            logger.error(f"Failed to clean up ALB resources for {server_id}: {str(e)}")
            results["errors"].append(str(e))
            return results
    
    def sync_alb(self) -> Dict[str, Any]:
        """Synchronize ALB resources with the MCP server configuration.
        
        Returns:
            Dictionary with synchronization results
        """
        results = {
            "created": [],
            "updated": [],
            "deleted": [],
            "errors": []
        }
        
        try:
            # Get MCP server configurations
            mcp_servers = self.config_manager.get_mcp_servers()
            
            # Set up ALB resources for each MCP server
            for server_id, config in mcp_servers.items():
                if config.get("disabled", False):
                    # Server is disabled, clean up ALB resources
                    self.cleanup_alb_for_server(server_id)
                    results["deleted"].append(server_id)
                    continue
                
                # Get container info
                container_info = self.container_manager.get_container_info(server_id)
                
                if not container_info.get("exists", False) or not container_info.get("running", False):
                    # Container doesn't exist or isn't running, skip
                    logger.info(f"Container for {server_id} doesn't exist or isn't running, skipping ALB setup")
                    continue
                
                # Set up ALB resources
                setup_results = self.setup_alb_for_server(server_id)
                if setup_results.get("errors"):
                    results["errors"].extend(f"{server_id}: {error}" for error in setup_results["errors"])
                else:
                    if setup_results.get("target_group_created") and setup_results.get("rule_created"):
                        results["created"].append(server_id)
                    else:
                        results["updated"].append(server_id)
            
            # Get all target groups
            response = self.client.describe_target_groups()
            
            # Find and clean up orphaned target groups
            for target_group in response.get('TargetGroups', []):
                tags_response = self.client.describe_tags(
                    ResourceArns=[target_group['TargetGroupArn']]
                )
                
                # Check if this is an MCP target group
                is_mcp_target_group = False
                server_id = None
                
                for tag_description in tags_response.get('TagDescriptions', []):
                    for tag in tag_description.get('Tags', []):
                        if tag.get('Key') == 'ManagedBy' and tag.get('Value') == 'mcp-orchestrator':
                            is_mcp_target_group = True
                        if tag.get('Key') == 'MCPService':
                            server_id = tag.get('Value')
                
                if is_mcp_target_group and server_id and server_id not in mcp_servers:
                    # This is an orphaned target group, clean it up
                    logger.info(f"Found orphaned target group for {server_id}, cleaning up")
                    self.cleanup_alb_for_server(server_id)
                    results["deleted"].append(server_id)
            
            logger.info(f"ALB sync complete: {len(results['created'])} created, {len(results['updated'])} updated, {len(results['deleted'])} deleted")
            return results
        except Exception as e:
            logger.error(f"Failed to synchronize ALB resources: {str(e)}")
            results["errors"].append(f"General error: {str(e)}")
            return results
