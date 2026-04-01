#!/bin/bash
# ============================================================
# Performance Test Runner
# Network Engineer: Israr Sadaq
# ============================================================

echo "========================================"
echo "Network Performance Test Runner"
echo "========================================"

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install requirements if needed
pip install iperf3 requests

# Run tests
python ../latency_framework.py --config ../configs/default.json --once

# If continuous monitoring is needed
# python ../latency_framework.py --config ../configs/default.json --daemon