#!/bin/bash
# Simple test script for the Ollama Hub API

SERVER_URL="${SERVER_URL:-http://localhost:8000}"

echo "=== Ollama Hub API Test Script ==="
echo "Server URL: $SERVER_URL"
echo ""

# Test 1: Health Check
echo "1. Testing Health Check..."
response=$(curl -s "$SERVER_URL/healthz")
echo "Response: $response"
echo ""

# Test 2: List Nodes
echo "2. Listing Registered Nodes..."
nodes=$(curl -s "$SERVER_URL/nodes")
node_count=$(echo "$nodes" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
echo "Found $node_count node(s)"
echo ""

if [ "$node_count" -eq 0 ]; then
    echo "⚠️  No nodes registered. Please start a client node first."
    exit 1
fi

# Test 3: Get Available Models
echo "3. Available Models:"
models=$(echo "$nodes" | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = set()
for node in data:
    models.update(node.get('models', []))
print(' '.join(sorted(models)) if models else 'None')
" 2>/dev/null)
echo "  $models"
echo ""

# Test 4: Submit a Job (if models available)
if [ "$models" != "None" ] && [ -n "$models" ]; then
    # Get first available model
    first_model=$(echo "$models" | awk '{print $1}')
    echo "4. Testing Job Submission with model: $first_model"
    echo "   Prompt: 'Hello, how are you?'"
    echo ""
    
    response=$(curl -s -X POST "$SERVER_URL/jobs" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"$first_model\",
            \"prompt\": \"Hello, how are you? Please respond briefly.\",
            \"stream\": false
        }")
    
    if echo "$response" | grep -q "response"; then
        echo "✅ Job submitted successfully!"
        echo "$response" | python3 -m json.tool 2>/dev/null | head -20
    else
        echo "❌ Job failed:"
        echo "$response" | python3 -m json.tool 2>/dev/null
    fi
else
    echo "4. ⚠️  No models available. Skipping job test."
    echo "   Please ensure Ollama is running and models are pulled on the node."
fi

echo ""
echo "=== Test Complete ==="

