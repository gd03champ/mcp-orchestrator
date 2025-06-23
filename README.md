# MCP Docker Orchestrator

A systemd-managed daemon that orchestrates MCP (Model Context Protocol) servers as Docker containers and configures AWS ALB path-based routing.

## Features

- **Dynamic Container Management**: Automatically manage Docker containers for MCP servers based on configuration
- **AWS ALB Integration**: Configure path-based routing in AWS Application Load Balancer
- **Web Dashboard**: Monitor and control MCP services through a web interface
- **Self-healing**: Automatically reconcile configuration and actual state
- **Secure**: No persistence of secrets, compatible with LiteLLM Proxy

## Architecture

The MCP Docker Orchestrator consists of several core components:

- **Configuration Manager**: Handles loading and parsing of configuration files
- **Container Manager**: Manages Docker container lifecycle
- **ALB Manager**: Configures AWS ALB routing rules
- **Dashboard**: Web interface for monitoring and management
- **Orchestrator Service**: Main process that coordinates all components

## Prerequisites

- Python 3.8 or higher
- Docker
- AWS Account with appropriate permissions
- Linux host (for systemd service)

## Installation

### Automatic Installation

The easiest way to install is using the provided setup script:

```bash
sudo ./setup.sh
```

This will:
1. Install Python dependencies
2. Create default configuration files
3. Set up the systemd service
4. Configure permissions

### Manual Installation

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure settings in `settings.conf`

3. Configure MCP servers in `mcp.config.json`

4. Install systemd service:
   ```bash
   sudo cp service.template /etc/systemd/system/mcp-orchestrator.service
   # Edit the service file to configure paths
   sudo systemctl daemon-reload
   sudo systemctl enable mcp-orchestrator.service
   ```

## Configuration

### Settings (`settings.conf`)

```ini
[aws]
region = us-west-2      # AWS region
alb_arn =               # ARN of your Application Load Balancer
listener_arn =          # ARN of your ALB listener
vpc_id =                # ID of your VPC

[service]
reconciliation_interval_seconds = 60  # How often to check and reconcile state
port_range_start = 8000               # Start of port range for container mapping
port_range_end = 9000                 # End of port range for container mapping

[dashboard]
username = admin        # Dashboard login username
password = changeme     # Dashboard login password (change this!)
path = /monitor         # URL path for dashboard

[logging]
level = INFO            # Logging level (DEBUG, INFO, WARNING, ERROR)
```

### MCP Server Configuration (`mcp.config.json`)

```json
{
  "mcpServers": {
    "example-mcp-server": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "--interactive",
        "--env", "FASTMCP_LOG_LEVEL=ERROR",
        "mcp/example:latest"
      ],
      "env": {
        "ADDITIONAL_ENV_VAR": "value"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Each MCP server configuration consists of:

- **command**: Must be "docker" for container-based servers
- **args**: Docker command arguments
- **env**: Additional environment variables
- **disabled**: Whether this server is disabled
- **autoApprove**: List of auto-approved actions (LiteLLM specific)

## Usage

### Starting the Service

```bash
sudo systemctl start mcp-orchestrator
```

### Checking Status

```bash
sudo systemctl status mcp-orchestrator
```

### Viewing Logs

```bash
sudo journalctl -u mcp-orchestrator -f
```

### Manual Execution

For testing or debugging:

```bash
# Run once and exit
python orchestrator/main.py --one-shot

# Run without dashboard
python orchestrator/main.py --no-dashboard

# Specify custom config files
python orchestrator/main.py --config /path/to/mcp.config.json --settings /path/to/settings.conf
```

## Dashboard

The web dashboard is available at:

```
http://your-server:5000/monitor
```

Default login: admin / changeme

Features:
- Overview of MCP servers
- Container status monitoring
- ALB routing configuration
- Actions (start/stop/restart containers)
- Synchronization controls

## Routing

Each MCP server is mapped to a path based on its ID:

```
/mcp/{server-id}/*
```

These path patterns are configured in the ALB listener rules.

## Troubleshooting

### Container Issues

- Check Docker status: `docker ps -a`
- Verify container logs: `docker logs mcp-{server-id}`
- Check for port conflicts

### AWS ALB Issues

- Verify AWS credentials
- Check ALB listener ARN and rules
- Ensure target groups are properly configured
- Check EC2 instance is registered with target groups

### Service Issues

- Check systemd status: `systemctl status mcp-orchestrator`
- View logs: `journalctl -u mcp-orchestrator -f`
- Verify configuration files are properly formatted

## License

This project is licensed under the MIT License - see the LICENSE file for details.
