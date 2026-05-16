#!/bin/bash
# Deploy Sovereign Swarm to Termux / Nothing Phone 2a
termux-change-repo && pkg update -y && pkg install -y python git curl
pip install sovereign-swarm-v2
mkdir -p ~/.config/sovereign-swarm
# Start DSL daemon on phone
curl -s http://127.0.0.1:18800/api/v1/status || (
  python3 -m sovereign_swarm.dsl.daemon &>
  echo "Daemon started on Nothing Phone 2a"
)
