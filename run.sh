#!/bin/bash
set -e

# Load sensitive values from .env if it exists
if [ -f .env ]; then
  set -a
  source <(grep -v '^#' .env | grep -v '^$' | sed 's/^/export /')
  set +a
fi

# Start main app container
echo "🚀 Starting main app container..."
docker compose -f docker-compose.yaml up -d --force-recreate --build app

# Wait for container to be fully up
echo "⏳ Waiting for container to be ready..."
sleep 3

# Generate a secure auth configuration
echo "🔐 Generating secure authentication..."
docker run --rm amir20/dozzle:latest generate "$DOZZLE_USER" --password "$DOZZLE_PASS" --user-filter "$DOZZLE_FILTER" > users.yml

# Create a temporary compose file for Dozzle with restricted access
cat > docker-compose.logs.yaml <<EOF
services:
  logs:
    image: amir20/dozzle:latest
    container_name: verbex-api-wrapper-logs
    ports:
      - "$DOZZLE_PORT:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./users.yml:/data/users.yml:ro
    environment:
      - DOZZLE_AUTH_PROVIDER=simple
      - DOZZLE_ENABLE_ACTIONS=false
      - DOZZLE_ENABLE_SHELL=false
    command: --auth-provider simple
EOF

# Start Dozzle
echo "📡 Starting Dozzle with secure authentication..."
docker compose -f docker-compose.logs.yaml up -d logs

echo "✅ All services are up!"
echo "🌐 View logs at: http://localhost:$DOZZLE_PORT"
echo "🔑 Login credentials:"
echo "   Username: $DOZZLE_USER"
echo "   Password: $DOZZLE_PASS"
echo "📝 Note: Only logs for 'verbex-api-wrapper' container are accessible"

# Cleanup function to stop Dozzle and remove the logs compose file
cleanup_logs() {
  echo "🛑 Stopping Dozzle logs container..."
  docker compose -f docker-compose.logs.yaml down
  echo "🧹 Removing temporary files..."
  rm -f docker-compose.logs.yaml users.yml
  echo "✅ Cleanup complete."
}

echo ""
echo "To stop Dozzle and clean up, run:"
echo "  bash -c 'source run.sh; cleanup_logs'"
