#!/usr/bin/env python3
"""
Test script to validate all required dependencies for MCP Orchestrator.
This script checks if all necessary Python modules are installed and accessible.
"""

import importlib
import sys
import subprocess
import os
import json

# ANSI colors for prettier output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
ENDC = '\033[0m'
BOLD = '\033[1m'

# List of required Python modules from requirements.txt
REQUIRED_MODULES = [
    'docker',
    'boto3',
    'flask',
    'pyyaml',
    'configparser',
    'click',
    'requests',
    'python-dotenv',
    'gunicorn',
    'tenacity'
]

# System dependencies
SYSTEM_DEPENDENCIES = [
    'docker',  # Docker CLI
    'aws',     # AWS CLI
    'python3'  # Python 3
]


def print_header(message):
    """Print a formatted header message."""
    print(f"\n{BLUE}{BOLD}{'=' * 60}{ENDC}")
    print(f"{BLUE}{BOLD} {message} {ENDC}")
    print(f"{BLUE}{BOLD}{'=' * 60}{ENDC}\n")


def check_python_module(module_name):
    """Check if a Python module can be imported."""
    try:
        importlib.import_module(module_name)
        print(f"{GREEN}✓ Module '{module_name}' is installed.{ENDC}")
        return True
    except ImportError as e:
        print(f"{RED}✗ Module '{module_name}' is NOT installed: {e}{ENDC}")
        return False


def check_system_dependency(dependency):
    """Check if a system dependency is available in PATH."""
    try:
        subprocess.run(['which', dependency], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{GREEN}✓ System dependency '{dependency}' is available.{ENDC}")
        return True
    except subprocess.CalledProcessError:
        print(f"{RED}✗ System dependency '{dependency}' is NOT available in PATH.{ENDC}")
        return False


def check_docker_functionality():
    """Test Docker functionality by listing containers."""
    try:
        # Try to import the Docker module
        import docker
        
        # Try to connect to Docker daemon
        client = docker.from_env()
        client.ping()  # Test connection
        
        # List containers as a simple test
        containers = client.containers.list(all=True)
        print(f"{GREEN}✓ Docker API connection successful. Found {len(containers)} containers.{ENDC}")
        return True
    except ImportError:
        print(f"{RED}✗ Docker Python module not installed.{ENDC}")
        return False
    except Exception as e:
        print(f"{RED}✗ Docker API connection failed: {e}{ENDC}")
        return False


def check_aws_functionality():
    """Test AWS functionality by checking credentials."""
    try:
        # Try to import the boto3 module
        import boto3
        
        # Check for AWS credentials
        session = boto3.Session()
        credentials = session.get_credentials()
        
        if credentials is None:
            print(f"{YELLOW}⚠ AWS credentials not found or not configured.{ENDC}")
            print(f"{YELLOW}  To configure AWS credentials, run 'aws configure' or set up environment variables.{ENDC}")
            return False
        
        # Try to get the account ID as a simple test
        try:
            sts = session.client('sts')
            account_id = sts.get_caller_identity().get('Account')
            print(f"{GREEN}✓ AWS API connection successful. Account ID: {account_id}{ENDC}")
            return True
        except Exception as e:
            print(f"{YELLOW}⚠ AWS API connection test failed: {e}{ENDC}")
            print(f"{YELLOW}  This may be due to missing credentials or permissions.{ENDC}")
            return False
            
    except ImportError:
        print(f"{RED}✗ Boto3 Python module not installed.{ENDC}")
        return False


def check_flask_functionality():
    """Test Flask functionality by creating a simple app."""
    try:
        # Try to import Flask
        from flask import Flask
        
        # Create a simple test app
        app = Flask(__name__)
        
        @app.route('/')
        def home():
            return 'Flask is working!'
        
        print(f"{GREEN}✓ Flask imports and app creation successful.{ENDC}")
        return True
    except ImportError:
        print(f"{RED}✗ Flask Python module not installed.{ENDC}")
        return False
    except Exception as e:
        print(f"{RED}✗ Flask test failed: {e}{ENDC}")
        return False


def check_config_files(config_files=["settings.conf", "mcp.config.json"]):
    """Check that config files exist and are valid."""
    results = {}
    
    for config_file in config_files:
        if not os.path.exists(config_file):
            print(f"{YELLOW}⚠ Config file '{config_file}' not found.{ENDC}")
            results[config_file] = False
            continue
        
        # Check file format
        if config_file.endswith('.json'):
            try:
                with open(config_file) as f:
                    json.load(f)
                print(f"{GREEN}✓ JSON config file '{config_file}' is valid.{ENDC}")
                results[config_file] = True
            except json.JSONDecodeError as e:
                print(f"{RED}✗ JSON config file '{config_file}' is invalid: {e}{ENDC}")
                results[config_file] = False
        elif config_file.endswith('.conf'):
            try:
                import configparser
                config = configparser.ConfigParser()
                config.read(config_file)
                print(f"{GREEN}✓ Config file '{config_file}' is valid.{ENDC}")
                results[config_file] = True
            except Exception as e:
                print(f"{RED}✗ Config file '{config_file}' is invalid: {e}{ENDC}")
                results[config_file] = False
    
    return all(results.values())


def check_directory_structure():
    """Check that the expected directory structure exists."""
    required_dirs = [
        "orchestrator",
        "orchestrator/dashboard",
        "orchestrator/dashboard/templates",
        "orchestrator/utils"
    ]
    
    all_exist = True
    
    for directory in required_dirs:
        if os.path.exists(directory) and os.path.isdir(directory):
            print(f"{GREEN}✓ Directory '{directory}' exists.{ENDC}")
        else:
            print(f"{RED}✗ Directory '{directory}' does not exist.{ENDC}")
            all_exist = False
    
    return all_exist


def main():
    """Main function to run all tests."""
    print_header("MCP Orchestrator Dependency Test")
    
    # Track test results
    all_passed = True
    
    # Check Python modules
    print_header("Checking Python Modules")
    modules_passed = all([check_python_module(module) for module in REQUIRED_MODULES])
    all_passed = all_passed and modules_passed
    
    # Check system dependencies
    print_header("Checking System Dependencies")
    system_passed = all([check_system_dependency(dep) for dep in SYSTEM_DEPENDENCIES])
    all_passed = all_passed and system_passed
    
    # Check Docker functionality
    print_header("Testing Docker Functionality")
    docker_passed = check_docker_functionality()
    all_passed = all_passed and docker_passed
    
    # Check AWS functionality
    print_header("Testing AWS Functionality")
    aws_passed = check_aws_functionality()
    # Don't fail on AWS check as it might be running locally without AWS
    
    # Check Flask functionality
    print_header("Testing Flask Functionality")
    flask_passed = check_flask_functionality()
    all_passed = all_passed and flask_passed
    
    # Check config files
    print_header("Checking Configuration Files")
    config_passed = check_config_files()
    all_passed = all_passed and config_passed
    
    # Check directory structure
    print_header("Checking Directory Structure")
    dir_passed = check_directory_structure()
    all_passed = all_passed and dir_passed
    
    # Print summary
    print_header("Test Results Summary")
    print(f"Python Modules: {GREEN if modules_passed else RED}{modules_passed}{ENDC}")
    print(f"System Dependencies: {GREEN if system_passed else RED}{system_passed}{ENDC}")
    print(f"Docker Functionality: {GREEN if docker_passed else RED}{docker_passed}{ENDC}")
    print(f"AWS Functionality: {GREEN if aws_passed else YELLOW}{aws_passed}{ENDC}")
    print(f"Flask Functionality: {GREEN if flask_passed else RED}{flask_passed}{ENDC}")
    print(f"Config Files: {GREEN if config_passed else RED}{config_passed}{ENDC}")
    print(f"Directory Structure: {GREEN if dir_passed else RED}{dir_passed}{ENDC}")
    print(f"\nOverall Result: {GREEN if all_passed else RED}{all_passed}{ENDC}")
    
    # Return success or failure
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
