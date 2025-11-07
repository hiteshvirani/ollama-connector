#!/bin/bash
set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Get the node port
NODE_PORT=${NODE_PORT:-8001}
CLOUDFLARE_URL=""

# Function to cleanup cloudflared on exit
cleanup() {
    if [ -n "${CLOUDFLARE_PID:-}" ]; then
        log_info "Stopping Cloudflare tunnel (PID: $CLOUDFLARE_PID)..."
        kill $CLOUDFLARE_PID 2>/dev/null || true
        wait $CLOUDFLARE_PID 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# Check if cloudflared is installed
if ! command -v cloudflared >/dev/null 2>&1; then
    log_error "cloudflared is not installed!"
    log_info "Installing cloudflared..."
    
    # Install cloudflared for Linux x86_64
    ARCH=$(uname -m)
    if [ "$ARCH" = "x86_64" ]; then
        ARCH="amd64"
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        ARCH="arm64"
    else
        log_error "Unsupported architecture: $ARCH"
        exit 1
    fi
    
    # Download and install cloudflared
    CLOUDFLARED_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}"
    curl -L -o /usr/local/bin/cloudflared "$CLOUDFLARED_URL" || {
        log_error "Failed to download cloudflared"
        exit 1
    }
    chmod +x /usr/local/bin/cloudflared
    log_success "cloudflared installed successfully"
fi

# Start Cloudflare tunnel in the background
log_info "Starting Cloudflare tunnel for port $NODE_PORT..."

# Create a temporary file to capture cloudflared output
TEMP_OUTPUT=$(mktemp)
trap "rm -f $TEMP_OUTPUT" EXIT

# Start cloudflared and capture output
# Use 127.0.0.1 instead of localhost to ensure proper binding
cloudflared tunnel --url "http://127.0.0.1:${NODE_PORT}" > "$TEMP_OUTPUT" 2>&1 &
CLOUDFLARE_PID=$!

# Wait for tunnel URL to be generated (max 30 seconds)
log_info "Waiting for Cloudflare tunnel to be ready..."
MAX_WAIT=30
WAIT_COUNT=0
TUNNEL_READY=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    # Check if cloudflared process is still running
    if ! kill -0 $CLOUDFLARE_PID 2>/dev/null; then
        log_error "cloudflared process died unexpectedly"
        cat "$TEMP_OUTPUT" || true
        exit 1
    fi
    
    # Try to extract URL from output
    if grep -q "https://.*trycloudflare.com" "$TEMP_OUTPUT" 2>/dev/null; then
        CLOUDFLARE_URL=$(grep -o "https://[^ ]*\.trycloudflare\.com" "$TEMP_OUTPUT" | head -1)
        if [ -n "$CLOUDFLARE_URL" ]; then
            TUNNEL_READY=1
            break
        fi
    fi
    
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    
    # Show progress every 5 seconds
    if [ $((WAIT_COUNT % 5)) -eq 0 ]; then
        log_info "Still waiting for tunnel... (${WAIT_COUNT}/${MAX_WAIT}s)"
    fi
done

if [ $TUNNEL_READY -eq 0 ]; then
    log_error "Failed to get Cloudflare tunnel URL after ${MAX_WAIT} seconds"
    log_info "cloudflared output:"
    cat "$TEMP_OUTPUT" || true
    log_warning "Continuing without Cloudflare tunnel..."
    CLOUDFLARE_URL=""
else
    log_success "Cloudflare tunnel ready: $CLOUDFLARE_URL"
    export CLOUDFLARE_URL
    log_info "CLOUDFLARE_URL environment variable set: $CLOUDFLARE_URL"
fi

# Start the FastAPI application with the environment variable
log_info "Starting Ollama node agent on port $NODE_PORT..."
if [ -n "$CLOUDFLARE_URL" ]; then
    log_info "Using Cloudflare URL: $CLOUDFLARE_URL"
    export CLOUDFLARE_URL
    # Write to a file that Python can read, as a backup method
    echo "$CLOUDFLARE_URL" > /tmp/cloudflare_url.txt
fi

# Always export CLOUDFLARE_URL (even if empty) so Python can read it
export CLOUDFLARE_URL
exec uvicorn agent:app --host 0.0.0.0 --port "$NODE_PORT"

