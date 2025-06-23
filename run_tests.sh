#!/bin/bash
# Interactive Test Runner for MCP Orchestrator
# This script interactively asks the user which tests to run

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

# Ask for yes/no confirmation
ask_yes_no() {
    local prompt="$1"
    local answer
    while true; do
        read -p "${prompt} (y/n) " answer
        case $answer in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Please answer yes (y) or no (n).";;
        esac
    done
}

# Check if we're in the right directory
if [ ! -d "orchestrator" ] || [ ! -d "test" ]; then
    print_error "This script must be run from the project root directory."
    exit 1
fi

# Track test results
ALL_PASSED=true
RESULTS=()
VENV_DIR="venv_test"
DO_CLEANUP=true

print_header "MCP Orchestrator Test Runner"

# Ask user which tests to run
echo "Which tests would you like to run?"
echo "1. All tests (dependency, orchestrator, deployment)"
echo "2. Only unit tests (dependency, orchestrator)"
echo "3. Only deployment test"
echo "4. Only dependency test"
echo "5. Exit"
read -p "Enter your choice [1-5]: " test_choice

case $test_choice in
    1)
        RUN_DEPENDENCY=true
        RUN_ORCHESTRATOR=true
        RUN_DEPLOYMENT=true
        ;;
    2)
        RUN_DEPENDENCY=true
        RUN_ORCHESTRATOR=true
        RUN_DEPLOYMENT=false
        ;;
    3)
        RUN_DEPENDENCY=false
        RUN_ORCHESTRATOR=false
        RUN_DEPLOYMENT=true
        ;;
    4)
        RUN_DEPENDENCY=true
        RUN_ORCHESTRATOR=false
        RUN_DEPLOYMENT=false
        ;;
    5)
        echo "Exiting..."
        exit 0
        ;;
    *)
        print_error "Invalid choice. Exiting..."
        exit 1
        ;;
esac

# Ask about cleanup
ask_yes_no "Clean up test environment after completion?" && DO_CLEANUP=true || DO_CLEANUP=false

# Create a virtual environment for testing if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    print_header "Creating virtual environment"
    python3 -m venv $VENV_DIR
    if [ $? -ne 0 ]; then
        print_error "Failed to create virtual environment."
        print_warning "Make sure you have python3-venv installed:"
        print_warning "  - For Debian/Ubuntu: sudo apt install python3-venv python3-full"
        print_warning "  - For RHEL/CentOS: sudo yum install python3-pip"
        exit 1
    fi
fi

# Activate virtual environment
print_header "Activating virtual environment"
source $VENV_DIR/bin/activate

# Install requirements
print_header "Installing requirements"
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    print_error "Failed to install requirements."
    deactivate
    exit 1
fi

# Run dependency checks if selected
if [ "$RUN_DEPENDENCY" = true ]; then
    print_header "Running dependency tests"
    python test/test_dependencies.py
    DEP_STATUS=$?

    if [ $DEP_STATUS -eq 0 ]; then
        RESULTS+=("Dependency Tests: ${GREEN}PASSED${NC}")
    else
        RESULTS+=("Dependency Tests: ${RED}FAILED${NC}")
        ALL_PASSED=false
    fi
else
    RESULTS+=("Dependency Tests: ${YELLOW}SKIPPED${NC}")
fi

# Run orchestrator tests if selected
if [ "$RUN_ORCHESTRATOR" = true ]; then
    print_header "Running orchestrator tests"
    python test/test_orchestrator.py
    ORCH_STATUS=$?

    if [ $ORCH_STATUS -eq 0 ]; then
        RESULTS+=("Orchestrator Tests: ${GREEN}PASSED${NC}")
    else
        RESULTS+=("Orchestrator Tests: ${RED}FAILED${NC}")
        ALL_PASSED=false
    fi
else
    RESULTS+=("Orchestrator Tests: ${YELLOW}SKIPPED${NC}")
fi

# Deactivate virtual environment
deactivate

# Run deployment test if selected
if [ "$RUN_DEPLOYMENT" = true ]; then
    print_header "Running deployment test"
    ./test/test_deployment.sh
    DEPLOY_STATUS=$?

    if [ $DEPLOY_STATUS -eq 0 ]; then
        RESULTS+=("Deployment Test: ${GREEN}PASSED${NC}")
    else
        RESULTS+=("Deployment Test: ${RED}FAILED${NC}")
        ALL_PASSED=false
    fi
else
    RESULTS+=("Deployment Test: ${YELLOW}SKIPPED${NC}")
fi

# Clean up the virtual environment if requested
if [ "$DO_CLEANUP" = true ]; then
    print_header "Cleaning up test environment"
    if [ -d "$VENV_DIR" ]; then
        print_step "Removing virtual environment..."
        rm -rf $VENV_DIR
        print_step "Virtual environment removed."
    else
        print_warning "No virtual environment to clean up."
    fi
else
    print_warning "Skipping cleanup as requested. Virtual environment remains at: $VENV_DIR"
fi

# Print results
print_header "Test Results Summary"
for result in "${RESULTS[@]}"; do
    echo -e "$result"
done

# Print overall result
if [ "$ALL_PASSED" = true ]; then
    print_header "${GREEN}All executed tests passed!${NC}"
    exit 0
else
    print_header "${RED}Some tests failed!${NC}"
    exit 1
fi
