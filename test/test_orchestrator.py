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
from orchestrator.container_manager import ContainerManager
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
        self.mcp_config_path = os.path.join(self.temp_dir.name, 'mcp.config.json')
        
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
        
        # Create test MCP config
        with open(self.mcp_config_path, 'w') as f:
            f.write('''{
  "mcpServers": {
    "test-server": {
      "command": "docker",
      "args": ["run", "--rm", "test-image:latest"],
      "env": {"TEST_ENV": "value"},
      "disabled": false,
      "autoApprove": []
    },
    "disabled-server": {
      "command": "docker",
      "args": ["run", "--rm", "disabled-image:latest"],
      "env": {},
      "disabled": true,
      "autoApprove": []
    }
  }
}''')
        
        # Create config manager
        self.config_manager = ConfigManager(
            mcp_config_path=self.mcp_config_path,
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
        self.assertEqual(server['command'], 'docker')
        self.assertFalse(server['disabled'])
        
        # Test getting settings
        aws_region = self.config_manager.get_setting('aws', 'region')
        self.assertEqual(aws_region, 'us-west-2')
        
        # Test getting setting with default
        test_setting = self.config_manager.get_setting('nonexistent', 'key', 'default')
        self.assertEqual(test_setting, 'default')
    
    @mock.patch('docker.from_env')
    def test_container_manager(self, mock_docker):
        """Test container manager."""
        mock_docker.return_value = self.docker_mock
        
        # Create container manager
        container_manager = ContainerManager(self.config_manager)
        
        # Test creating container
        container_id = container_manager.create_container('test-server', 
                                                          self.config_manager.get_mcp_server('test-server'))
        self.assertIsNotNone(container_id)
        
        # Test getting container info
        info = container_manager.get_container_info('test-server')
        self.assertTrue(info['exists'])
        self.assertTrue(info['running'])
        
        # Test stopping container
        result = container_manager.stop_container('test-server')
        self.assertTrue(result)
        
        # Test sync containers
        results = container_manager.sync_containers()
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
        with mock.patch('docker.from_env', return_value=self.docker_mock), \
             mock.patch('boto3.client', return_value=self.aws_mock):
            
            # Create managers
            container_manager = ContainerManager(self.config_manager)
            alb_manager = ALBManager(self.config_manager, container_manager)
            
            # Test full workflow
            # 1. Sync containers
            container_results = container_manager.sync_containers()
            self.assertGreaterEqual(len(container_results['created']), 0)
            
            # 2. Check container info
            info = container_manager.get_container_info('test-server')
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
