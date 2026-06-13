#!/bin/bash

# Deploy to various platforms

echo "CN31 Token Fetcher Deploy Script"

# Local deployment
deploy_local() {
    echo "Starting local server..."
    pip install -r requirements.txt
    python app.py
}

# Docker deployment
deploy_docker() {
    echo "Building Docker image..."
    docker build -t cn31-fetcher .
    docker run -d -p 8000:8000 --name cn31-fetcher cn31-fetcher
}

# Railway deployment
deploy_railway() {
    echo "Deploying to Railway..."
    railway login
    railway up
}

# Render deployment
deploy_render() {
    echo "Deploying to Render..."
    # Create render.yaml
    cat > render.yaml << EOF
services:
  - type: web
    name: cn31-fetcher
    runtime: python
    repo: https://github.com/YOUR_USERNAME/cn31-fetcher
    branch: main
    buildCommand: pip install -r requirements.txt
    startCommand: python app.py
    envVars:
      - key: PORT
        value: 8000
EOF
    echo "Push to GitHub and connect to Render"
}

case "$1" in
    local)
        deploy_local
        ;;
    docker)
        deploy_docker
        ;;
    railway)
        deploy_railway
        ;;
    render)
        deploy_render
        ;;
    *)
        echo "Usage: ./deploy.sh {local|docker|railway|render}"
        ;;
esac