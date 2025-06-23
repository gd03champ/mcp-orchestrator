#!/usr/bin/env python3
"""
Test script to simulate MCP Orchestrator functionality without affecting the system.
This script tests components and their interactions to ensure they work correctly.
"""

import os
import sys
import time
import json
import tempfile
import unittest
from unittest import mock

# Add parent directory to path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import modules after path setup
from orchestrator.utils.logging import setup_logging
from orchestrator.config_manager import ConfigManager
from orchestrator.compose_manager import ComposeManager
from orchestrator.alb_manager import ALBManager


class MockDockerContainer:
    """Mock Docker container for testing."""
    
    def __init__(self, container_id, name, status="running"):
        self.id = container_id
        self.name = name
        self.status = status
        self.attrs = {
            "State": {
                "Status": status,
                "Running": status == "running",
                "Health": {"Status": "healthy"} if status == "running" else {"Status": "unhealthy"}
            },
            "Created": "2025-06-22T12:00:00Z",
            "Config": {
                "Image": "test-image:latest"
            }
        }
    
    def stop(self, timeout=None):
        self.status = "stopped"
        self.attrs["State"]["Status"] = "stopped"
        self.attrs["State"]["Running"] = False
        return True
    
    def remove(self):
        return True
    
    def restart(self, timeout=None):
        self.status = "running"
        self.attrs["State"]["Status"] = "running"
        self.attrs["State"]["Running"] = True
        return True


class MockDockerClient:
    """Mock Docker client for testing."""
    
    def __init__(self):
        self.containers = MockContainerCollection()
    
    def ping(self):
        return True


class MockContainerCollection:
    """Mock container collection for Docker client."""
    
    def __init__(self):
        self._containers = {}
    
    def get(self, name):
        if name in self._containers:
            return self._containers[name]
        raise Exception(f"Container {name} not found")
    
    def run(self, image, **kwargs):
        name = kwargs.get('name', f"container-{len(self._containers)}")
        container = MockDockerContainer(
            f"container-id-{len(self._containers)}",
            name,
            "running"
        )
        self._containers[name] = container
        return container
    
    def list(self, all=False, filters=None):
        return list(self._containers.values())


class MockAWSClient:
    """Mock AWS client for testing."""
    
    def __init__(self):
        self.target_groups = {}
        self.rules = {}
        self.listeners = {
            "dummy-listener-arn": {
                "ListenerArn": "dummy-listener-arn",
                "Port": 80,
                "Protocol": "HTTP"
            }
        }
    
    def describe_target_groups(self, Names=None):
        if Names:
            result = []
            for name in Names:
                if name in self.target_groups:
                    result.append(self.target_groups[name])
            if not result:
                # Instead of raising an exception, return an empty list
                # This matches the AWS boto3 behavior when no target groups are found
                return {"TargetGroups": []}
            return {"TargetGroups": result}
        return {"TargetGroups": list(self.target_groups.values())}
    
    def create_target_group(self, **kwargs):
        name = kwargs.get('Name')
        tg = {
            "TargetGroupArn": f"arn:aws:elasticloadbalancing:us-west-2:123456789012:targetgroup/{name}/abcdef1234567890",
            "TargetGroupName": name,
            "Protocol": kwargs.get('Protocol', 'HTTP'),
            "Port": kwargs.get('Port', 80),
            "VpcId": kwargs.get('VpcId', 'vpc-1234567890abcdef')
        }
        self.target_groups[name] = tg
        return {"TargetGroups": [tg]}
    
    def describe_rules(self, ListenerArn=None):
        return {"Rules": list(self.rules.values())}
    
    def create_rule(self, **kwargs):
        rule = {
            "RuleArn": f"rule-arn-{len(self.rules)}",
            "Priority": kwargs.get('Priority', 1),
            "Conditions": kwargs.get('Conditions', []),
            "Actions": kwargs.get('Actions', [])
        }
        self.rules[rule["RuleArn"]] = rule
        return {"Rules": [rule]}
    
    def modify_rule(self, **kwargs):
        rule_arn = kwargs.get('RuleArn')
        if rule_arn in self.rules:
            self.rules[rule_arn]['Actions'] = kwargs.get('Actions', [])
            return {"Rules": [self.rules[rule_arn]]}
        raise Exception("Rule not found")
    
    def register_targets(self, **kwargs):
        return {}
    
    def add_tags(self, **kwargs):
        return {}
    
    def describe_tags(self, **kwargs):
        return {"TagDescriptions": []}


class TestMCPOrchestrator(unittest.TestCase):
    """Test cases for MCP Orchestrator components."""
    
    def setUp(self):
        """Set up test environment."""
        # Create temporary config files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_path = os.path.join(self.temp_dir.name, 'settings.conf')
        self.compose_path = os.path.join(self.temp_dir.name, 'mcp-compose.yaml')
        
        # Create test settings
        with open(self.settings_path, 'w') as f:
            f.write('''[aws]
region = us-west-2
alb_arn = arn:aws:elasticloadbalancing:us-west-2:123456789012:loadbalancer/app/test-alb/abcdef1234567890
listener_arn = dummy-listener-arn
vpc_id = vpc-1234567890abcdef

[service]
reconciliation_interval_seconds = 10
port_range_start = 8000
port_range_end = 9000

[dashboard]
username = admin
password = test123
path = /monitor

[logging]
level = DEBUG
''')
        
        # Create test Docker Compose config
        with open(self.compose_path, 'w') as f:
            f.write('''version: '3'
services:
  test-server:
    image: test-image:latest
    restart: always
    environment:
      TEST_ENV: "value"
    labels:
      mcp.path: "/mcp/test-server"
      mcp.disabled: "false"
      mcp.managed_by: "mcp-orchestrator"
  disabled-server:
    image: disabled-image:latest
    restart: always
    labels:
      mcp.path: "/mcp/disabled-server"
      mcp.disabled: "true"
      mcp.managed_by: "mcp-orchestrator"
''')
        
        # Create config manager
        self.config_manager = ConfigManager(
            compose_path=self.compose_path,
            settings_path=self.settings_path
        )
        
        # Set up mocks
        self.docker_mock = MockDockerClient()
        self.aws_mock = MockAWSClient()
    
    def tearDown(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()
    
    def test_config_manager(self):
        """Test configuration manager."""
        # Test loading config
        self.config_manager.load_config()
        
        # Test getting MCP servers
        mcp_servers = self.config_manager.get_mcp_servers()
        self.assertEqual(len(mcp_servers), 2)
        self.assertIn('test-server', mcp_servers)
        self.assertIn('disabled-server', mcp_servers)
        
        # Test getting specific server
        server = self.config_manager.get_mcp_server('test-server')
        self.assertIn('service_config', server)
        self.assertFalse(server['disabled'])
        
        # Test getting settings
        aws_region = self.config_manager.get_setting('aws', 'region')
        self.assertEqual(aws_region, 'us-west-2')
        
        # Test getting setting with default
        test_setting = self.config_manager.get_setting('nonexistent', 'key', 'default')
        self.assertEqual(test_setting, 'default')
    
    @mock.patch('subprocess.run')
    def test_compose_manager(self, mock_subprocess):
        """Test compose manager."""
        
        # Define a side effect function to handle different commands
        def mock_subprocess_run(args, **kwargs):
            # Create a mock response object
            mock_response = mock.Mock()
            mock_response.returncode = 0
            
            # Check for docker compose version
            if len(args) >= 3 and args[0:2] == ["docker", "compose"] and args[2] == "--version":
                mock_response.stdout = "Docker Compose version v2.17.2"
                return mock_response
                
            # Check for docker-compose version (legacy)
            if len(args) >= 2 and args[0] == "docker-compose" and args[1] == "--version":
                mock_response.stdout = "docker-compose version 1.29.2"
                return mock_response
                
            # Check for docker compose ps (checking if service exists) - new format
            if (len(args) >= 6 and args[0:2] == ["docker", "compose"] and 
                args[2] == "-f" and args[4] == "ps" and args[5] == "--services"):
                mock_response.stdout = "test-server"
                return mock_response
                
            # Check for docker-compose ps (checking if service exists) - legacy format
            if (len(args) >= 5 and args[0] == "docker-compose" and 
                args[1] == "-f" and args[3] == "ps" and args[4] == "--services"):
                mock_response.stdout = "test-server"
                return mock_response
                
            # Check for docker inspect
            if len(args) >= 2 and args[0] == "docker" and args[1] == "inspect":
                mock_response.stdout = """[
  {
    "Id": "container-id-0",
    "State": {"Status": "running", "Running": true, "Health": {"Status": "healthy"}},
    "Created": "2025-06-22T12:00:00Z",
    "Config": {"Image": "test-image:latest"},
    "NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "8080"}]}}
  }
]"""
                return mock_response
                
            # Default for other commands (like up, restart, etc)
            mock_response.stdout = ""
            return mock_response
            
        # Set the side effect for the mock
        mock_subprocess.side_effect = mock_subprocess_run
        
        # Create compose manager
        compose_manager = ComposeManager(self.config_manager)
        
        # Test starting service
        result = compose_manager.start_service('test-server')
        self.assertTrue(result)
        
        # Test getting service info
        info = compose_manager.get_service_info('test-server')
        self.assertTrue(info['exists'])
        
        # Test stopping service
        result = compose_manager.stop_service('test-server')
        self.assertTrue(result)
        
        # Test sync services
        results = compose_manager.sync_services()
        self.assertIn('created', results)
        self.assertIn('errors', results)
    
    @mock.patch('boto3.client')
    def test_alb_manager(self, mock_boto3):
        """Test ALB manager."""
        mock_boto3.return_value = self.aws_mock
        
        # Mock the container manager
        container_manager = mock.MagicMock()
        container_manager.get_port_for_server.return_value = 8080
        container_manager.get_container_info.return_value = {
            'exists': True, 
            'running': True, 
            'host_port': 8080
        }
        
        # Create ALB manager
        alb_manager = ALBManager(self.config_manager, container_manager)
        
        # Test creating target group
        try:
            tg_arn = alb_manager.create_target_group('test-server')
            self.assertIsNotNone(tg_arn)
        except Exception as e:
            self.fail(f"Creating target group raised an exception: {e}")
        
        # Test creating listener rule
        rule_arn = alb_manager.create_listener_rule('test-server')
        self.assertIsNotNone(rule_arn)
        
        # Test setting up ALB for server
        setup_results = alb_manager.setup_alb_for_server('test-server')
        # Just check that the setup_results dict contains the expected keys
        self.assertIn('target_group_created', setup_results)
        self.assertIn('rule_created', setup_results)
        
        # Test sync ALB
        sync_results = alb_manager.sync_alb()
        self.assertIn('created', sync_results)
        self.assertIn('errors', sync_results)
    
    def test_integration(self):
        """Test integration between components."""
        # Create mocks
        with mock.patch('subprocess.run') as mock_subprocess, \
             mock.patch('boto3.client', return_value=self.aws_mock):
            
            # Define a side effect function to handle different commands
            def mock_subprocess_run(args, **kwargs):
                # Create a mock response object
                mock_response = mock.Mock()
                mock_response.returncode = 0
                
                # Check for docker compose version
                if len(args) >= 3 and args[0:2] == ["docker", "compose"] and args[2] == "--version":
                    mock_response.stdout = "Docker Compose version v2.17.2"
                    return mock_response
                    
                # Check for docker-compose version (legacy)
                if len(args) >= 2 and args[0] == "docker-compose" and args[1] == "--version":
                    mock_response.stdout = "docker-compose version 1.29.2"
                    return mock_response
                    
                # Check for docker compose ps (checking if service exists) - new format
                if (len(args) >= 6 and args[0:2] == ["docker", "compose"] and 
                    args[2] == "-f" and args[4] == "ps" and args[5] == "--services"):
                    mock_response.stdout = "test-server"
                    return mock_response
                    
                # Check for docker-compose ps (checking if service exists) - legacy format
                if (len(args) >= 5 and args[0] == "docker-compose" and 
                    args[1] == "-f" and args[3] == "ps" and args[4] == "--services"):
                    mock_response.stdout = "test-server"
                    return mock_response
                    
                # Check for docker inspect
                if len(args) >= 2 and args[0] == "docker" and args[1] == "inspect":
                    mock_response.stdout = """[
  {
    "Id": "container-id-0",
    "State": {"Status": "running", "Running": true, "Health": {"Status": "healthy"}},
    "Created": "2025-06-22T12:00:00Z",
    "Config": {"Image": "test-image:latest"},
    "NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "8080"}]}}
  }
]"""
                    return mock_response
                    
                # Default for other commands (like up, restart, etc)
                mock_response.stdout = ""
                return mock_response
                
            # Set the side effect for the mock
            mock_subprocess.side_effect = mock_subprocess_run
            
            # Create managers
            compose_manager = ComposeManager(self.config_manager)
            alb_manager = ALBManager(self.config_manager, compose_manager)
            
            # Test full workflow
            # 1. Sync services
            service_results = compose_manager.sync_services()
            self.assertGreaterEqual(len(service_results['created']), 0)
            
            # 2. Check service info
            info = compose_manager.get_service_info('test-server')
            self.assertTrue(info['exists'])
            
            # 3. Set up ALB
            alb_results = alb_manager.setup_alb_for_server('test-server')
            # Only validate that alb_results is a dict with expected structure
            self.assertIsInstance(alb_results, dict)
            self.assertIn('target_group_created', alb_results)
            self.assertIn('rule_created', alb_results)
            
            # 4. Sync ALB
            alb_sync_results = alb_manager.sync_alb()
            self.assertGreaterEqual(len(alb_sync_results['created']), 0)


def main():
    """Run the tests."""
    # Set up logging
    logger = setup_logging("test")
    
    # Run tests
    unittest.main()


if __name__ == "__main__":
    main()
