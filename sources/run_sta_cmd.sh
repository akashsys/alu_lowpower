#!/bin/bash
# Point to your Windows Docker Engine
export DOCKER_HOST=tcp://host.docker.internal:2375

# 2. State Management
STATE_FILE="./sources/.active_task_id"
CONTAINER_NAME="openlane"

# 3. Resume Check
if [ -f "$STATE_FILE" ]; then
    TASK_ID=$(cat "$STATE_FILE")
    UNIQUE_DIR="/openlane/$TASK_ID"
    echo ">>> RESUMING: Iterating in existing directory $UNIQUE_DIR"
else
    TASK_ID="task_$(date +%s)"
    UNIQUE_DIR="/openlane/$TASK_ID"
    echo "$TASK_ID" > "$STATE_FILE"
    echo ">>> STARTING NEW: Creating unique directory $UNIQUE_DIR"
fi

# 4. Start the "Box" without volume mounts (Clean Start)
if [ ! "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    # Removed -v mounting to fix the "No such file" errors
    docker run -d --name "$CONTAINER_NAME" efabless/openlane:latest tail -f /dev/null
fi

# 5. INITIALIZATION & SYNC (Pushing local files directly into the container)
# We use 'mkdir' and 'docker cp' instead of relying on /openlane_mnt
docker exec "$CONTAINER_NAME" mkdir -p "$UNIQUE_DIR"
echo ">>> Syncing all sources from host to Docker container..."
docker cp "./sources/." "$CONTAINER_NAME":"$UNIQUE_DIR/"

# ==============================================================================
# 6. EXECUTION & ITERATION
# ==============================================================================
# We no longer 'cp' from /openlane_mnt; we just run the tools in $UNIQUE_DIR
echo ">>> STATUS: Synthesizing in $UNIQUE_DIR..."
docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && yosys -s syn_script.ys" || exit 1

echo ">>> STATUS: Generating Area Reports..."
docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && yosys -s area.ys" || exit 1

echo ">>> STATUS: Timing Analysis..."
docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && sta -no_init run_sta.tcl" || exit 1

# Show reports
echo "------------------------------------------------------------"
echo "AREA REPORT:"
docker exec "$CONTAINER_NAME" cat "$UNIQUE_DIR/area_report.rpt"
echo "------------------------------------------------------------"
echo "TIMING REPORT:"
docker exec "$CONTAINER_NAME" cat "$UNIQUE_DIR/timing_report.rpt"
docker cp "$CONTAINER_NAME":"$UNIQUE_DIR/elastic_credit_arbiter.v" "./sources/elastic_credit_arbiter.v"