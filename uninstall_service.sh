#!/bin/bash
# Script to uninstall the MCP Orchestrator systemd service and clean up

# Colors for prettier output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

print_header() {
    echo -e "\n${BLUE}${BOLD}=====================================================${NC}"
    echo -e "${BLUE}${BOLD} $1 ${NC}"
    echo -e "${BLUE}${BOLD}=====================================================${NC}\n"
}

print_step() {
    echo -e "${GREEN}[+] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[!] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root or with sudo"
    exit 1
fi

SERVICE_NAME="mcp-orchestrator"
INSTALL_DIR="/opt/mcp-orchestrator"

print_header "MCP Orchestrator Service Uninstaller"

# Stop the service if it's running
print_step "Stopping service (if running)..."
systemctl stop $SERVICE_NAME 2>/dev/null
systemctl status $SERVICE_NAME >/dev/null 2>&1
if [ $? -ne 4 ]; then
    print_step "Service was running and has been stopped."
else
    print_warning "Service was not running."
fi

# Disable the service
print_step "Disabling service..."
systemctl disable $SERVICE_NAME 2>/dev/null

# Remove the service file
print_step "Removing service file..."
if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    print_step "Service file removed."
else
    print_warning "Service file not found."
fi

# Reload systemd configuration
print_step "Reloading systemd configuration..."
systemctl daemon-reload

# Ask if installation directory should be removed
read -p "Remove installation directory ($INSTALL_DIR)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "Removing installation directory..."
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        print_step "Installation directory removed."
    else
        print_warning "Installation directory not found."
    fi
else
    print_step "Keeping installation directory."
    if [ -d "$INSTALL_DIR" ]; then
        print_step "You can find the previous configuration files in $INSTALL_DIR"
    fi
fi

# Ask if backup should be created
read -p "Create backup of configuration files before reinstalling? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    BACKUP_DIR="mcp_backup_$(date +%Y%m%d_%H%M%S)"
    print_step "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    
    if [ -f "$INSTALL_DIR/settings.conf" ]; then
        print_step "Backing up settings.conf..."
        cp "$INSTALL_DIR/settings.conf" "$BACKUP_DIR/"
    fi
    
    if [ -f "$INSTALL_DIR/mcp.config.json" ]; then
        print_step "Backing up mcp.config.json..."
        cp "$INSTALL_DIR/mcp.config.json" "$BACKUP_DIR/"
    fi
    
    print_step "Backup created in $BACKUP_DIR"
fi

print_header "Uninstallation Complete"
print_step "You can now reinstall the service with the new changes using:"
print_step "  sudo ./setup.sh"
print_step ""
print_step "If you created a backup, you may want to restore the configuration files after installation:"
print_step "  sudo cp $BACKUP_DIR/settings.conf /opt/mcp-orchestrator/"
print_step "  sudo cp $BACKUP_DIR/mcp.config.json /opt/mcp-orchestrator/"

exit 0
