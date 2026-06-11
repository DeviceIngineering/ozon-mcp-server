#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping Ozon MCP Server..."
docker compose down
echo "Done."
