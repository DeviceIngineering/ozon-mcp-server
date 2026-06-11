#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Ozon MCP Server..."
docker compose up -d --build
echo "Done. Running at http://localhost:8000"
