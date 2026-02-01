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

STATE_FILE="./sources/.task_dir"

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

# 3. Synchronize initial scripts and RTL to container
# This is necessary so Yosys has access to syn_script.ys and the .v file
docker cp ./sources/. openlane:$UNIQUE_DIR/ || exit 1

# 4. SYNTHESIS STEP: RTL to Netlist
# Triggers if the FORCE_RESYNTHESIS flag exists OR if netlist.v is missing (first run)
if [ -f "./sources/FORCE_RESYNTHESIS" ] || [ ! -f "./sources/netlist.v" ]; then
    echo ">>> STATUS: Starting RTL-to-Netlist Synthesis..."
    
    # Run Yosys inside the container
    docker exec openlane bash -c "cd $UNIQUE_DIR && yosys -s syn_script.ys" || exit 1
    
    # Copy the newly created netlist back to the Host (Windows)
    # This allows the agent to see and edit the netlist locally.
    docker cp openlane:$UNIQUE_DIR/netlist.v ./sources/netlist.v
    
    # Cleanup flag on Host
    [ -f "./sources/FORCE_RESYNTHESIS" ] && rm "./sources/FORCE_RESYNTHESIS"
    echo ">>> SUCCESS: Netlist generated and synced to ./sources/netlist.v"
else
    echo ">>> STATUS: Netlist exists. Skipping synthesis to preserve ECO/Sizing changes."
fi

# 5. FINAL SYNC: Push the netlist (either fresh or agent-edited) back to container
docker cp ./sources/netlist.v openlane:$UNIQUE_DIR/netlist.v || exit 1

# 6. Run Static Timing Analysis (STA)
echo ">>> STATUS: Running Static Timing Analysis..."
docker exec openlane bash -c "cd $UNIQUE_DIR && sta -no_init run_sta.tcl" || exit 1
docker exec openlane cat $UNIQUE_DIR/timing_report.rpt || exit 1

# 7. Run Area Analysis
echo ">>> STATUS: Calculating Area..."
docker exec openlane bash -c "cd $UNIQUE_DIR && yosys area.ys" || exit 1
docker exec openlane cat $UNIQUE_DIR/area.rpt || exit 1


