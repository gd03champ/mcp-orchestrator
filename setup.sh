#!/bin/bash
# MCP Docker Orchestrator Setup Script

set -e  # Exit on any error

# Default installation directory
DEFAULT_INSTALL_DIR="/opt/mcp-orchestrator"
INSTALL_DIR=${1:-$DEFAULT_INSTALL_DIR}
SERVICE_NAME="mcp-orchestrator"

# Colors for prettier output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================="
echo "MCP Docker Orchestrator Setup"
echo -e "==========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root or with sudo${NC}"
  exit 1
fi

# Check dependencies
echo "Checking dependencies..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is required but not installed.${NC}"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Warning: Docker does not appear to be installed.${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${YELLOW}Warning: AWS CLI does not appear to be installed.${NC}"
    echo "You may need it for AWS credentials configuration."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create installation directory if it doesn't exist
echo "Creating installation directory..."
mkdir -p $INSTALL_DIR

# Copy files to installation directory
echo "Copying files..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

# Copy all files
cp -r $SCRIPT_DIR/* $INSTALL_DIR/

# Create default settings file if it doesn't exist
if [ ! -f "$INSTALL_DIR/settings.conf" ]; then
    echo "Creating default settings.conf..."
    cat > $INSTALL_DIR/settings.conf << EOL
[aws]
region = us-west-2
alb_arn = 
listener_arn = 
vpc_id = 

[service]
reconciliation_interval_seconds = 60
port_range_start = 8000
port_range_end = 9000

[dashboard]
username = admin
password = changeme
path = /monitor

[logging]
level = INFO
EOL
fi

# Create default MCP config file if it doesn't exist
if [ ! -f "$INSTALL_DIR/mcp.config.json" ]; then
    echo "Creating default mcp.config.json..."
    cat > $INSTALL_DIR/mcp.config.json << EOL
{
  "mcpServers": {
  }
}
EOL
fi

# Install Python requirements
echo "Installing Python requirements..."
pip3 install -r $INSTALL_DIR/requirements.txt

# Get the current user
CURRENT_USER=$(logname || echo $SUDO_USER || echo $USER)
echo "Setting up service as user: $CURRENT_USER"

# Make main.py executable
chmod +x $INSTALL_DIR/orchestrator/main.py

# Replace placeholders in service template
echo "Configuring systemd service..."
sed -e "s|%INSTALL_DIR%|$INSTALL_DIR|g" \
    -e "s|%USER%|$CURRENT_USER|g" \
    $INSTALL_DIR/service.template > /etc/systemd/system/$SERVICE_NAME.service

# Set appropriate permissions
echo "Setting permissions..."
chown -R $CURRENT_USER:$CURRENT_USER $INSTALL_DIR

# Reload systemd and enable the service
echo "Enabling service..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME.service

echo -e "${GREEN}Setup complete!${NC}"
echo
echo "To start the service, run:"
echo -e "  ${YELLOW}systemctl start $SERVICE_NAME${NC}"
echo
echo "To check service status:"
echo -e "  ${YELLOW}systemctl status $SERVICE_NAME${NC}"
echo
echo "Dashboard will be available at:"
echo -e "  ${YELLOW}http://localhost:5000/monitor${NC}"
echo
echo -e "${YELLOW}IMPORTANT:${NC} Before starting the service, ensure you configure:"
echo "  - AWS credentials (using aws configure or instance role)"
echo "  - ALB Listener ARN in settings.conf"
echo "  - VPC ID in settings.conf"
echo "  - MCP servers in mcp.config.json"
echo
echo -e "${GREEN}Configuration files location:${NC}"
echo "  $INSTALL_DIR/settings.conf"
echo "  $INSTALL_DIR/mcp.config.json"
