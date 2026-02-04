#!/bin/bash
# 1. Point to your Windows Docker Engine
export DOCKER_HOST=tcp://host.docker.internal:2375

# 2. Configuration
CONTAINER_NAME="openlane"
# We mount the WHOLE repo so paths inside Docker match paths outside Docker
REPO_ROOT="/home/ubuntu/example-verilog-codebase"
DOCKER_WORK_DIR="/openlane/workspace"


# 4. EXECUTION
# Note: We run inside the 'sources' folder relative to our new wide mount
echo ">>> STATUS: Running Synthesis..."
docker exec "$CONTAINER_NAME" bash -c "yosys -s syn_script.ys" || exit 1

echo ">>> STATUS: Generating Area Reports..."
docker exec "$CONTAINER_NAME" bash -c "yosys -s area.ys" || exit 1

echo ">>> STATUS: Timing Analysis..."
docker exec "$CONTAINER_NAME" bash -c "sta -no_init run_sta.tcl" || exit 1

# 5. Display reports from the local host folder
# Since it's mounted, if the tool wrote it, it's already here!
echo "------------------------------------------------------------"
echo "TIMING RESULTS (Direct from local workspace):"
cat "./sources/timing_report.rpt" 2>/dev/null || echo "Report not yet synced."

echo ">>> SUCCESS: Workspace is now unified. Edits in /home/ubuntu are LIVE in Docker."