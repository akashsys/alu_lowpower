#!/bin/bash
# Fixed version with parallel execution support
# Prevents race conditions when running multiple instances simultaneously

# Point to your Windows Docker Engine
export DOCKER_HOST=tcp://host.docker.internal:2375

# 2. State Management
STATE_FILE="./sources/.active_task_id"

# Generate unique container name using PID and random number
# This prevents conflicts when multiple instances run in parallel
CONTAINER_NAME="openlane_$$_$(uuidgen 2>/dev/null || echo ${RANDOM}${RANDOM})"

echo ">>> Using container: $CONTAINER_NAME"

# 3. Resume Check with high-resolution task ID
if [ -f "$STATE_FILE" ]; then
    TASK_ID=$(cat "$STATE_FILE")
    UNIQUE_DIR="/openlane/$TASK_ID"
    echo ">>> RESUMING: Iterating in existing directory $UNIQUE_DIR"
else
    # Generate unique task ID with nanosecond timestamp + PID + random
    # This prevents collisions even with simultaneous starts
    TIMESTAMP_NS=$(date +%s%N 2>/dev/null || echo $(date +%s)999999999)
    TASK_ID="task_${TIMESTAMP_NS}_$$_${RANDOM}${RANDOM}"
    UNIQUE_DIR="/openlane/$TASK_ID"
    echo "$TASK_ID" > "$STATE_FILE"
    echo ">>> STARTING NEW: Creating unique directory $UNIQUE_DIR"
fi

echo ">>> Task ID: $TASK_ID"
echo ">>> Unique directory: $UNIQUE_DIR"

# 4. Start unique container for this instance
if [ ! "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo ">>> Creating new container: $CONTAINER_NAME"
    docker run -d --name "$CONTAINER_NAME" efabless/openlane:latest tail -f /dev/null
    
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create container $CONTAINER_NAME"
        exit 1
    fi
    
    # Wait for container to be ready
    sleep 2
else
    echo ">>> Container $CONTAINER_NAME already running"
fi

# 5. INITIALIZATION & SYNC (Pushing local files directly into the container)
echo ">>> Creating unique task directory in container..."
docker exec "$CONTAINER_NAME" mkdir -p "$UNIQUE_DIR"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create directory $UNIQUE_DIR in container"
    exit 1
fi

echo ">>> Syncing all sources from host to Docker container..."
docker cp "./sources/." "$CONTAINER_NAME":"$UNIQUE_DIR/"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to sync sources to container"
    exit 1
fi

# ==============================================================================
# 6. EXECUTION & ITERATION
# ==============================================================================
echo ">>> STATUS: Synthesizing in $UNIQUE_DIR..."
if [ "$SKIP_SYNTH" = "1" ] && [ -f "./sources/netlist.v" ]; then
    echo ">>> ECO MODE: Skipping synthesis, using existing netlist.v..."
else
    echo ">>> STATUS: Synthesizing fresh netlist in $UNIQUE_DIR..."
    docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && yosys -s syn_script.ys" || exit 1
fi

echo ">>> STATUS: Generating Area Reports..."
docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && yosys -s area.ys"

if [ $? -ne 0 ]; then
    echo "ERROR: Area analysis failed"
    docker stop "$CONTAINER_NAME" 2>/dev/null
    docker rm "$CONTAINER_NAME" 2>/dev/null
    exit 1
fi

echo ">>> STATUS: Timing Analysis..."
docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && sta -no_init run_sta.tcl"

if [ $? -ne 0 ]; then
    echo "ERROR: Timing analysis failed"
    docker stop "$CONTAINER_NAME" 2>/dev/null
    docker rm "$CONTAINER_NAME" 2>/dev/null
    exit 1
fi

# Show reports
echo "------------------------------------------------------------"
echo "AREA REPORT:"
docker exec "$CONTAINER_NAME" cat "$UNIQUE_DIR/area_report.rpt"
echo "------------------------------------------------------------"
echo "TIMING REPORT:"
docker exec "$CONTAINER_NAME" cat "$UNIQUE_DIR/timing_report.rpt"
echo "------------------------------------------------------------"

# Copy back modified files to host
echo ">>> STATUS: Copying results back to host..."
docker cp "$CONTAINER_NAME":"$UNIQUE_DIR/elastic_credit_arbiter.v" "./sources/elastic_credit_arbiter.v"
docker cp "$CONTAINER_NAME":"$UNIQUE_DIR/netlist.v" "./sources/netlist.v" 2>/dev/null

