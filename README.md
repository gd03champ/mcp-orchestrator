# MCP Docker Orchestrator

A systemd-managed daemon that orchestrates MCP (Model Context Protocol) servers as Docker containers and configures AWS ALB path-based routing.

## Features

- **Docker Compose Integration**: Manage MCP servers using standard Docker Compose format
- **AWS ALB Integration**: Configure path-based routing in AWS Application Load Balancer
- **Web Dashboard**: Monitor and control MCP services through a web interface
- **Self-healing**: Automatically reconcile configuration and actual state
- **Secure**: No persistence of secrets, compatible with LiteLLM Proxy

## Architecture

The MCP Docker Orchestrator consists of several core components:

- **Configuration Manager**: Handles loading and parsing of Docker Compose configuration
- **Compose Manager**: Manages Docker Compose service lifecycle
- **ALB Manager**: Configures AWS ALB routing rules
- **Dashboard**: Web interface for monitoring and management
- **Orchestrator Service**: Main process that coordinates all components

## Prerequisites

- Python 3.8 or higher
- Docker and Docker Compose
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

3. Configure MCP servers in `mcp-compose.yaml`

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

### MCP Server Configuration (`mcp-compose.yaml`)

```yaml
version: '3'

services:
  example-mcp-server:
    image: mcp/example:latest
    restart: always
    environment:
      FASTMCP_LOG_LEVEL: "ERROR"
      ADDITIONAL_ENV_VAR: "value"
    labels:
      mcp.path: "/mcp/example"
      mcp.disabled: "false"
      mcp.managed_by: "mcp-orchestrator"
```

Each MCP server configuration consists of:

- **image**: Docker image to run
- **restart**: Restart policy (always recommended)
- **environment**: Environment variables
- **labels**:
  - **mcp.path**: Path pattern for ALB routing
  - **mcp.disabled**: Whether this server is disabled
  - **mcp.managed_by**: Should always be "mcp-orchestrator"

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
python orchestrator/main.py --compose /path/to/mcp-compose.yaml --settings /path/to/settings.conf

# Migrate from old config format
python orchestrator/main.py --migrate /path/to/old/mcp.config.json
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
- Actions (start/stop/restart services)
- Synchronization controls

## Routing

Each MCP server is mapped to a path based on its ID or the mcp.path label:

```
/mcp/{server-id}/*
```

These path patterns are configured in the ALB listener rules.

## Migrating from mcp.config.json

If you're upgrading from an older version that used `mcp.config.json`, you can use the built-in migration tool:

```bash
python orchestrator/main.py --migrate /path/to/mcp.config.json
```

This will:
1. Read your existing `mcp.config.json`
2. Convert it to the new Docker Compose format
3. Save it as `mcp-compose.yaml`

## Troubleshooting

### Container Issues

- Check Docker Compose status: `docker compose ps`
- Verify container logs: `docker compose logs {service-id}`
- Check for port conflicts
- If you see "Permission denied" errors:
  - The service user needs access to the Docker socket
  - Make sure the user is in the docker group
  - You may need to log out and log back in for group changes to take effect

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
