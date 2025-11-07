#!/bin/bash
set -euo pipefail

# ============================================
# Configuration - Edit these values as needed
# ============================================
REQUIRED_MODELS="qwen2.5:7b"       # Comma-separated list of models to pull
NODE_PORT="8001"                   # Port for the node agent
OLLAMA_PORT="11434"                # Port for Ollama API
SKIP_MODEL_PULL="0"                # Set to "1" to skip model pulling
# ============================================

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Docker installation
check_docker() {
    log_info "Checking Docker installation..."
    
    if ! command_exists docker; then
        log_error "Docker is not installed!"
        log_info "Please install Docker first: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon is not running or you don't have permission!"
        log_info "Try: sudo systemctl start docker"
        log_info "Or add your user to docker group: sudo usermod -aG docker $USER"
        exit 1
    fi
    
    log_success "Docker is installed and running"
    
    # Check Docker Compose
    if command_exists docker-compose; then
        log_success "Docker Compose (standalone) is available"
    elif docker compose version >/dev/null 2>&1; then
        log_success "Docker Compose (plugin) is available"
    else
        log_error "Docker Compose is not available!"
        exit 1
    fi
}

# Check if Docker Compose command exists (handles both standalone and plugin)
docker_compose_cmd() {
    if command_exists docker-compose; then
        docker-compose "$@"
    else
        docker compose "$@"
    fi
}

# Check and install Ollama locally
check_ollama_installation() {
    log_info "Checking Ollama installation..."
    
    if command_exists ollama; then
        log_success "Ollama is already installed"
        ollama_version=$(ollama --version 2>/dev/null || echo "unknown")
        log_info "Ollama version: $ollama_version"
        return 0
    fi
    
    log_info "Ollama is not installed. Installing Ollama..."
    
    # Install Ollama using official install script
    if command_exists curl; then
        log_info "Downloading and installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
        if [ $? -eq 0 ]; then
            log_success "Ollama installed successfully"
        else
            log_error "Failed to install Ollama"
            exit 1
        fi
    else
        log_error "curl is required to install Ollama but not found!"
        log_info "Install curl: sudo apt-get install curl"
        log_info "Or install Ollama manually: https://ollama.com/download"
        exit 1
    fi
}

# Start Ollama service (systemd)
start_ollama_service() {
    log_info "Starting Ollama service..."
    
    # Check if Ollama service is already running
    if systemctl is-active --quiet ollama 2>/dev/null; then
        log_info "Ollama service is already running"
        return 0
    fi
    
    # Try to start Ollama service
    if systemctl start ollama 2>/dev/null; then
        log_success "Ollama service started"
    else
        log_warning "Could not start Ollama via systemd, trying to run in background..."
        # If systemd doesn't work, try running ollama serve in background
        if ! pgrep -f "ollama serve" >/dev/null; then
            nohup ollama serve > /tmp/ollama.log 2>&1 &
            sleep 2
            if pgrep -f "ollama serve" >/dev/null; then
                log_success "Ollama started in background"
            else
                log_error "Failed to start Ollama"
                exit 1
            fi
        else
            log_info "Ollama is already running"
        fi
    fi
}

# Configure UFW firewall
configure_ufw() {
    log_info "Configuring UFW firewall..."
    
    if ! command_exists ufw; then
        log_warning "UFW is not installed. Skipping firewall configuration."
        log_info "To install UFW: sudo apt-get install ufw"
        return 0
    fi
    
    # Check if UFW is active
    if ! sudo ufw status | grep -q "Status: active"; then
        log_warning "UFW is installed but not active"
        read -p "Do you want to enable UFW? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Enabling UFW..."
            echo "y" | sudo ufw --force enable
            log_success "UFW enabled"
        else
            log_warning "UFW not enabled. Firewall rules will not be applied."
            return 0
        fi
    fi
    
    # Allow Node Agent port (IPv4 & IPv6)
    # This port accepts incoming connections from the server hub
    if sudo ufw status | grep -q "${NODE_PORT}/tcp"; then
        log_info "Port ${NODE_PORT}/tcp (Node Agent) is already allowed"
    else
        log_info "Allowing port ${NODE_PORT}/tcp for Node Agent (IPv4 & IPv6)..."
        # UFW allow command automatically allows both IPv4 and IPv6
        sudo ufw allow ${NODE_PORT}/tcp comment 'Ollama Node Agent'
        log_success "Port ${NODE_PORT}/tcp allowed for Node Agent (IPv4 & IPv6)"
    fi
    
    # Allow Ollama API port (IPv4 & IPv6)
    # This port is used by the node agent to connect to local Ollama
    # Note: Since Ollama runs locally, this is mainly for completeness
    # and in case Ollama needs to be accessed from other machines
    if sudo ufw status | grep -q "${OLLAMA_PORT}/tcp"; then
        log_info "Port ${OLLAMA_PORT}/tcp (Ollama API) is already allowed"
    else
        log_info "Allowing port ${OLLAMA_PORT}/tcp for Ollama API (IPv4 & IPv6)..."
        # UFW allow command automatically allows both IPv4 and IPv6
        sudo ufw allow ${OLLAMA_PORT}/tcp comment 'Ollama API'
        log_success "Port ${OLLAMA_PORT}/tcp allowed for Ollama API (IPv4 & IPv6)"
    fi
    
    # Note: Outbound connections (e.g., to server hub on port 8000) are allowed by default in UFW
    # No explicit rule needed for client to connect to server
    
    # Display current firewall rules for our ports
    log_info "Current UFW status for configured ports:"
    sudo ufw status numbered | grep -E "(${NODE_PORT}|${OLLAMA_PORT})" || true
    
    # Verify IPv6 is enabled in UFW (UFW allows both IPv4 and IPv6 by default)
    if sudo ufw status | grep -q "IPv6"; then
        log_info "IPv6 support: Enabled (UFW allows both IPv4 and IPv6)"
    else
        log_info "IPv6 support: Enabled by default (UFW rules apply to both IPv4 and IPv6)"
    fi
    
    log_success "Firewall configuration complete"
    log_info "Note: Outbound connections (e.g., to server hub on port 8000) are allowed by default in UFW"
}


# Wait for Ollama to be ready
wait_for_ollama() {
    log_info "Waiting for Ollama API to be ready..."
    
    if ! command_exists curl; then
        log_error "curl is required but not found!"
        log_info "Install curl: sudo apt-get install curl"
        exit 1
    fi
    
    local max_attempts=30
    local attempt=0
    local ollama_url="http://localhost:${OLLAMA_PORT}"
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s -f "${ollama_url}/api/tags" >/dev/null 2>&1; then
            log_success "Ollama API is ready!"
            return 0
        fi
        
        attempt=$((attempt + 1))
        if [ $((attempt % 5)) -eq 0 ]; then
            log_info "Still waiting... (${attempt}/${max_attempts})"
        fi
        sleep 2
    done
    
    log_error "Ollama API did not become ready after $((max_attempts * 2)) seconds"
    log_info "Check Ollama service: sudo systemctl status ollama"
    log_info "Or check if Ollama is running: pgrep -f 'ollama serve'"
    exit 1
}

# Pull required models
pull_models() {
    if [ "$SKIP_MODEL_PULL" = "1" ]; then
        log_info "Skipping model pull (SKIP_MODEL_PULL=1)"
        return 0
    fi
    
    if [ -z "$REQUIRED_MODELS" ]; then
        log_info "No models specified (REQUIRED_MODELS is empty)"
        return 0
    fi
    
    if ! command_exists curl; then
        log_error "curl is required for model pulling but not found!"
        log_info "Install curl: sudo apt-get install curl"
        return 1
    fi
    
    log_info "Checking and pulling required models..."
    
    # Get list of available models
    local available_models
    available_models=$(curl -s "http://localhost:${OLLAMA_PORT}/api/tags" 2>/dev/null | \
        grep -o '"name":"[^"]*"' | sed 's/"name":"\([^"]*\)"/\1/' || echo "")
    
    # Split REQUIRED_MODELS by comma
    IFS=',' read -ra MODEL_ARRAY <<< "$REQUIRED_MODELS"
    
    for model in "${MODEL_ARRAY[@]}"; do
        model=$(echo "$model" | xargs) # Trim whitespace
        
        if [ -z "$model" ]; then
            continue
        fi
        
        # Check if model already exists (fuzzy match - model name might have tags)
        local model_exists=0
        if [ -n "$available_models" ]; then
            while IFS= read -r available; do
                if [ "$available" = "$model" ] || [[ "$available" == "${model}:"* ]]; then
                    model_exists=1
                    break
                fi
            done <<< "$available_models"
        fi
        
        if [ "$model_exists" -eq 1 ]; then
            log_success "Model '${model}' is already available"
            continue
        fi
        
        log_info "Pulling model '${model}' (this may take a while)..."
        log_info "  Progress will be shown below..."
        
        # Pull model using Ollama API (streaming endpoint)
        # The API returns JSON lines with status updates
        local pull_success=0
        local last_status=""
        
        while IFS= read -r line; do
            if [ -z "$line" ]; then
                continue
            fi
            
            # Parse status from JSON line
            local status
            status=$(echo "$line" | grep -o '"status":"[^"]*"' | sed 's/"status":"\([^"]*\)"/\1/' || echo "")
            
            if [ -n "$status" ] && [ "$status" != "$last_status" ]; then
                echo "    Status: $status"
                last_status="$status"
                
                if [ "$status" = "success" ]; then
                    pull_success=1
                fi
            fi
        done < <(curl -s -N -X POST "http://localhost:${OLLAMA_PORT}/api/pull" \
            -H "Content-Type: application/json" \
            -d "{\"name\": \"${model}\"}" 2>&1)
        
        if [ "$pull_success" -eq 1 ]; then
            log_success "Model '${model}' pulled successfully"
        else
            log_warning "Model '${model}' pull completed (check status above)"
        fi
        
        # Wait a moment before next model
        sleep 1
    done
    
    log_success "Model pull process completed"
}

# Verify setup
verify_setup() {
    log_info "Verifying setup..."
    
    # Check Ollama is running
    if ! pgrep -f "ollama serve" >/dev/null && ! systemctl is-active --quiet ollama 2>/dev/null; then
        log_error "Ollama service is not running!"
        log_info "Try: sudo systemctl start ollama"
        log_info "Or run: ollama serve"
        return 1
    fi
    log_success "Ollama service is running"
    
    # Check Ollama API is accessible
    if ! command_exists curl; then
        log_warning "curl not found, skipping API check"
    elif ! curl -s -f "http://localhost:${OLLAMA_PORT}/api/tags" >/dev/null 2>&1; then
        log_error "Ollama API is not accessible!"
        return 1
    else
        log_success "Ollama API is accessible"
        
        # List available models
        log_info "Available models:"
        local models
        models=$(curl -s "http://localhost:${OLLAMA_PORT}/api/tags" 2>/dev/null | \
            grep -o '"name":"[^"]*"' | sed 's/"name":"\([^"]*\)"/\1/' || echo "none")
        if [ -z "$models" ] || [ "$models" = "none" ]; then
            log_warning "No models found. You may need to pull models manually."
        else
            echo "$models" | while read -r model; do
                if [ -n "$model" ]; then
                    echo "  - $model"
                fi
            done
        fi
    fi
    
    # Check UFW if installed
    if command_exists ufw && sudo ufw status | grep -q "Status: active"; then
        log_info "UFW is active and configured"
    fi
    
    log_success "Setup verification complete!"
}

# Main execution
main() {
    echo "=========================================="
    echo "  Ollama Node Client Setup Script"
    echo "=========================================="
    echo ""
    
    log_info "Configuration:"
    echo "  - Required Models: ${REQUIRED_MODELS}"
    echo "  - Node Port: ${NODE_PORT}"
    echo "  - Ollama Port: ${OLLAMA_PORT}"
    if [ "$SKIP_MODEL_PULL" = "1" ]; then
        echo "  - Model Pull: SKIPPED"
    else
        echo "  - Model Pull: ENABLED"
    fi
    echo ""
    
    check_docker
    check_ollama_installation
    configure_ufw
    start_ollama_service
    wait_for_ollama
    pull_models
    verify_setup
    
    echo ""
    echo "=========================================="
    log_success "Setup completed successfully!"
    echo "=========================================="
    echo ""
    log_info "Next steps:"
    echo "  1. Set SERVER_URL environment variable:"
    echo "     export SERVER_URL=\"http://<hub-ip>:8000\""
    echo ""
    echo "  2. Set NODE_ID (optional):"
    echo "     export NODE_ID=\"node-$(hostname)\""
    echo ""
    echo "  3. Start the node agent:"
    echo "     docker compose up -d"
    echo ""
    echo "  4. Verify Ollama is running:"
    echo "     ollama list"
    echo ""
    log_info "To view logs: docker compose logs -f node"
    log_info "To stop: docker compose down"
    log_info "Note: Ollama runs locally (not in Docker) and must be running for the node to work"
}

# Run main function
main "$@"

