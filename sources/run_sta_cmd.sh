# 1. Point to the Windows Host bridge
export DOCKER_HOST=tcp://host.docker.internal:2375

# 2. Connection Retry (3 attempts)
CONNECTED=false
for i in {1..3}; do
    if docker ps > /dev/null 2>&1; then
        CONNECTED=true
        break
    fi
    echo "Waiting for Docker daemon... attempt $i/3"
    sleep 2
done

if [ "$CONNECTED" = false ]; then
    echo "CRITICAL ERROR: Docker Daemon unreachable at $DOCKER_HOST"
    exit 1
fi

#!/bin/bash

# 1. Connectivity
export DOCKER_HOST=tcp://host.docker.internal:2375

# 2. State Management (The "Memory" of the task)
STATE_FILE="./sources/.active_task_id"
CONTAINER_NAME="openlane_main"  # The name of the virtual "box"

# 3. Resume Check
if [ -f "$STATE_FILE" ]; then
    TASK_ID=$(cat "$STATE_FILE")
    UNIQUE_DIR="/openlane/$TASK_ID"
    echo ">>> RESUMING: Iterating in existing directory $UNIQUE_DIR"
    INIT_REQUIRED=false
else
    # NEW TASK: Generate a unique folder name
    TASK_ID="task_$(date +%s)"
    UNIQUE_DIR="/openlane/$TASK_ID"
    echo "$TASK_ID" > "$STATE_FILE"
    echo ">>> STARTING NEW: Creating unique directory $UNIQUE_DIR"
    INIT_REQUIRED=true
fi

# 4. Start the "Box" (Container) if it's not running
if [ ! "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    # Mount your Windows sources to a bridge called /openlane_mnt
    docker run -d --name "$CONTAINER_NAME" -v "${PWD}/sources:/openlane_mnt" efabless/openlane:latest tail -f /dev/null
fi

# 5. INITIALIZATION (Only runs once for a new task)
if [ "$INIT_REQUIRED" = true ]; then
    # Create the unique folder INSIDE /openlane
    docker exec "$CONTAINER_NAME" mkdir -p "$UNIQUE_DIR"
    
    # Copy all starting files from Windows (via the bridge) into the folder
    docker exec "$CONTAINER_NAME" bash -c "cp /openlane_mnt/*.v /openlane_mnt/*.ys /openlane_mnt/*.tcl $UNIQUE_DIR/ 2>/dev/null"
fi

# ==============================================================================
# 6. EXECUTION & ITERATION (The Loop)
# ==============================================================================
# Sync only the RTL change if the agent edited the file on Windows
echo ">>> Syncing latest RTL into $UNIQUE_DIR..."
docker exec "$CONTAINER_NAME" bash -c "cp /openlane_mnt/elastic_credit_arbiter.v $UNIQUE_DIR/"

echo ">>> STATUS: Synthesizing in $UNIQUE_DIR..."
docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && yosys -s syn_script.ys" || exit 1

echo ">>> STATUS: Timing Analysis..."
docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && sta -no_init run_sta.tcl" || exit 1

# Show reports
docker exec "$CONTAINER_NAME" cat "$UNIQUE_DIR/timing_report.rpt"