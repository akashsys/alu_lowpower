#!/bin/bash
# 1. Point to your Windows Docker Engine
export DOCKER_HOST=tcp://host.docker.internal:2375

# 2. State Management
STATE_FILE="./sources/.active_task_id"
CONTAINER_NAME="openlane"

# 3. Resume Check
if [ -f "$STATE_FILE" ]; then
    TASK_ID=$(cat "$STATE_FILE")
    echo ">>> RESUMING: Task ID $TASK_ID"
else
    TASK_ID="task_$(date +%s)"
    echo "$TASK_ID" > "$STATE_FILE"
    echo ">>> STARTING NEW: $TASK_ID"
fi
UNIQUE_DIR="/openlane/$TASK_ID"

# 4. Start the Container with a Volume Mount
# We map your local 'sources' folder to a fixed path in the container
if [ ! "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo ">>> Initializing Docker Container with Volume Mount..."
    docker run -d \
      --name "$CONTAINER_NAME" \
      -v "$(pwd)/sources:/host_sync" \
      efabless/openlane:latest tail -f /dev/null
fi

# 5. Connect the Unique Directory to the Synchronized Volume
# This ensures Yosys/STA run in $UNIQUE_DIR but write to your Windows folder
docker exec "$CONTAINER_NAME" mkdir -p "/openlane"
docker exec "$CONTAINER_NAME" ln -sfn "/host_sync" "$UNIQUE_DIR"

# 6. EXECUTION
echo ">>> STATUS: Running Synthesis in $UNIQUE_DIR..."
# Note: Because of the mount, the container is now reading/writing YOUR Windows files
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

echo ">>> SUCCESS: Volume Sync Active. Check sources/elastic_credit_arbiter.v on Windows."