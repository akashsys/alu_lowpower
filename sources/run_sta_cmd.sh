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

RUN_ID="job_${RANDOM}_$(date +%s)"
UNIQUE_SOURCES_DIR="./workspaces/$RUN_ID/sources"

echo ">>> Initializing isolated source sandbox: $UNIQUE_SOURCES_DIR"
mkdir -p "$UNIQUE_SOURCES_DIR"

# Copy original content into the sandbox
cp -r ./sources/. "$UNIQUE_SOURCES_DIR/"

# Update STATE_FILE to point to the sandbox
STATE_FILE="$UNIQUE_SOURCES_DIR/.task_dir"

if [ -f "$STATE_FILE" ]; then
    # ITERATION RUN: Read the existing directory name
    UNIQUE_DIR=$(cat "$STATE_FILE")
    echo "Syncing to existing workspace: $UNIQUE_DIR"
else
    # INITIAL RUN: Generate unique ID and save it
    CHAR=(A B C D E F G H I J K L M N O P Q R S T U V W X Y Z)
    RAND_LETTER=${CHAR[$RANDOM%26]}
    RAND_NUM=$((RANDOM % 100))
    UNIQUE_DIR="/openlane/task_${RAND_LETTER}_${RAND_NUM}_$RANDOM"
    
    echo "$UNIQUE_DIR" > "$STATE_FILE"
    echo "Provisioning new workspace: $UNIQUE_DIR"
    docker exec openlane mkdir -p $UNIQUE_DIR || exit 1
fi

# ==============================================================================
# 3. SYNCHRONIZE ISOLATED SOURCES TO CONTAINER
# ==============================================================================
# We copy from the UNIQUE sandbox, not the global ./sources
echo ">>> Syncing sandbox sources to container workspace: $UNIQUE_DIR"
docker cp "$UNIQUE_SOURCES_DIR/." openlane:$UNIQUE_DIR/ || exit 1

# ==============================================================================
# 4. SYNTHESIS STEP: RTL to Netlist
# ==============================================================================
# Check for the FORCE flag or missing netlist specifically in the sandbox
if [ -f "$UNIQUE_SOURCES_DIR/FORCE_RESYNTHESIS" ] || [ ! -f "$UNIQUE_SOURCES_DIR/netlist.v" ]; then
    echo ">>> STATUS: Starting RTL-to-Netlist Synthesis..."
    
    # Run Yosys inside the unique container directory
    docker exec openlane bash -c "cd $UNIQUE_DIR && yosys -s syn_script.ys" || exit 1
    
    # Copy the newly created netlist back to the ISOLATED Host sandbox
    # This ensures Run A doesn't overwrite Run B's netlist
    docker cp openlane:$UNIQUE_DIR/netlist.v "$UNIQUE_SOURCES_DIR/netlist.v"
    
    # Cleanup flag in the sandbox
    [ -f "$UNIQUE_SOURCES_DIR/FORCE_RESYNTHESIS" ] && rm "$UNIQUE_SOURCES_DIR/FORCE_RESYNTHESIS"
    echo ">>> SUCCESS: Netlist generated and synced to $UNIQUE_SOURCES_DIR/netlist.v"
else
    echo ">>> STATUS: Netlist exists in sandbox. Skipping synthesis to preserve ECO/Sizing changes."
fi

# ==============================================================================
# 5. FINAL SYNC: Push the Sandbox Netlist back to Container
# ==============================================================================
# This pushes the current netlist (whether freshly synthesized or agent-edited)
docker cp "$UNIQUE_SOURCES_DIR/netlist.v" openlane:$UNIQUE_DIR/netlist.v || exit 1

# ==============================================================================
# 6. RUN STATIC TIMING ANALYSIS (STA)
# ==============================================================================
echo ">>> STATUS: Running Static Timing Analysis..."
docker exec openlane bash -c "cd $UNIQUE_DIR && sta -no_init run_sta.tcl" || exit 1
docker exec openlane cat $UNIQUE_DIR/timing_report.rpt || exit 1

# ==============================================================================
# 7. RUN AREA ANALYSIS
# ==============================================================================
echo ">>> STATUS: Calculating Area..."
docker exec openlane bash -c "cd $UNIQUE_DIR && yosys area.ys" || exit 1
docker exec openlane cat $UNIQUE_DIR/area.rpt || exit 1

# ==============================================================================
# 8. TRIGGER PYTHON VALIDATION (Isolated)
# ==============================================================================
# Export the sandbox path so test_hidden.py knows where the RTL is
export ISOLATED_SOURCES="$UNIQUE_SOURCES_DIR"
pytest tests/test_hidden.py
