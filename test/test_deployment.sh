#!/bin/bash
# Test deployment script to simulate installation without affecting the system
# This helps identify installation and configuration issues before actual deployment

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

# Create a temporary directory for testing
TEMP_DIR=$(mktemp -d)

cleanup() {
    print_step "Cleaning up temporary directory..."
    rm -rf "$TEMP_DIR"
}

# Set up trap to clean up on exit
trap cleanup EXIT

print_header "MCP Orchestrator Deployment Test"
print_step "Using temporary directory: $TEMP_DIR"

# Get the project directory (where this script is located)
PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
print_step "Project directory: $PROJECT_DIR"

# Check Python version
print_step "Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1)
echo "    $PYTHON_VERSION"

# Check for python3-venv
print_step "Checking for Python virtual environment support..."
if python3 -m venv --help > /dev/null 2>&1; then
    echo "    Python venv support is available"
else
    print_error "Python venv support is not available. Install python3-venv and python3-full."
    exit 1
fi

# Create a virtual environment
print_step "Creating virtual environment..."
python3 -m venv "$TEMP_DIR/venv"
if [ $? -ne 0 ]; then
    print_error "Failed to create virtual environment."
    exit 1
fi

# Activate virtual environment
print_step "Activating virtual environment..."
source "$TEMP_DIR/venv/bin/activate"

# Copy project files to temp directory
print_step "Copying project files..."
mkdir -p "$TEMP_DIR/mcp-orchestrator"
cp -r "$PROJECT_DIR/orchestrator" "$TEMP_DIR/mcp-orchestrator/"
cp "$PROJECT_DIR/requirements.txt" "$TEMP_DIR/mcp-orchestrator/"
cp "$PROJECT_DIR/service.template" "$TEMP_DIR/mcp-orchestrator/"
cp "$PROJECT_DIR/setup.sh" "$TEMP_DIR/mcp-orchestrator/"
cp "$PROJECT_DIR/mcp.config.json" "$TEMP_DIR/mcp-orchestrator/"
cp "$PROJECT_DIR/settings.conf" "$TEMP_DIR/mcp-orchestrator/"

# Install requirements
print_step "Installing requirements..."
pip install -r "$TEMP_DIR/mcp-orchestrator/requirements.txt"
if [ $? -ne 0 ]; then
    print_error "Failed to install requirements."
    exit 1
fi

# Test importing key modules
print_step "Testing import of key modules..."
MODULES_TO_TEST=(docker boto3 flask yaml configparser requests dotenv tenacity)
FAILED_IMPORTS=0

for module in "${MODULES_TO_TEST[@]}"; do
    if ! python3 -c "import $module" 2>/dev/null; then
        print_error "Failed to import $module"
        FAILED_IMPORTS=$((FAILED_IMPORTS+1))
    else
        echo "    Successfully imported $module"
    fi
done

if [ $FAILED_IMPORTS -gt 0 ]; then
    print_error "$FAILED_IMPORTS modules failed to import."
    exit 1
fi

# Test systemd service file generation
print_step "Testing systemd service file generation..."
INSTALL_DIR="$TEMP_DIR/mcp-orchestrator"
USER=$(whoami)
PYTHON_PATH="$TEMP_DIR/venv/bin/python3"

sed -e "s|%INSTALL_DIR%|$INSTALL_DIR|g" \
    -e "s|%USER%|$USER|g" \
    -e "s|%PYTHON_PATH%|$PYTHON_PATH|g" \
    "$INSTALL_DIR/service.template" > "$TEMP_DIR/mcp-orchestrator.service"

# Check that the service file was generated
if [ ! -f "$TEMP_DIR/mcp-orchestrator.service" ]; then
    print_error "Failed to generate systemd service file."
    exit 1
fi

print_step "Generated systemd service file content:"
echo "-----------------"
cat "$TEMP_DIR/mcp-orchestrator.service"
echo "-----------------"

# Test launching the main script with minimal arguments
print_step "Testing main script launch (with --help argument)..."
cd "$TEMP_DIR"
"$PYTHON_PATH" "$INSTALL_DIR/orchestrator/main.py" --help
if [ $? -ne 0 ]; then
    print_error "Failed to run main script with --help argument."
    exit 1
fi

# Test config loading
print_step "Testing config loading..."
cat > "$TEMP_DIR/test_config.py" << EOF
from orchestrator.config_manager import ConfigManager

# Initialize ConfigManager
config_manager = ConfigManager(
    mcp_config_path='$INSTALL_DIR/mcp.config.json',
    settings_path='$INSTALL_DIR/settings.conf'
)

# Test loading config
config_manager.load_config()

# Test getting settings
aws_region = config_manager.get_setting('aws', 'region')
print(f"AWS region from config: {aws_region}")

# Test getting MCP servers
mcp_servers = config_manager.get_mcp_servers()
print(f"Found {len(mcp_servers)} MCP servers in config")
for server_id, config in mcp_servers.items():
    print(f"  {server_id}: {'enabled' if not config.get('disabled', False) else 'disabled'}")
EOF

"$PYTHON_PATH" "$TEMP_DIR/test_config.py"
if [ $? -ne 0 ]; then
    print_error "Failed to test config loading."
    exit 1
fi

# Deactivate virtual environment
deactivate

print_header "Deployment Test Summary"
print_step "Python environment: ${GREEN}OK${NC}"
print_step "Requirements installation: ${GREEN}OK${NC}"
print_step "Module imports: ${GREEN}OK${NC}"
print_step "Service file generation: ${GREEN}OK${NC}"
print_step "Main script launch: ${GREEN}OK${NC}"
print_step "Config loading: ${GREEN}OK${NC}"

print_header "Deployment Test Passed!"
print_step "The MCP Orchestrator should deploy correctly on this system."
print_step "For actual deployment, run the setup.sh script."

exit 0
