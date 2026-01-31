# 1. Point to the Windows Host bridge
#export DOCKER_HOST=tcp://127.0.0.1:2375
export DOCKER_HOST=tcp://host.docker.internal:2375

# 1. Connection Retry (3 attempts)
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
    # INITIAL RUN: Generate unique ID (e.g., task_G_54) and save it
    CHAR=(A B C D E F G H I J K L M N O P Q R S T U V W X Y Z)
    RAND_LETTER=${CHAR[$RANDOM%26]}
    RAND_NUM=$((RANDOM % 100))
    UNIQUE_DIR="/openlane/task_${RAND_LETTER}_${RAND_NUM}_$RANDOM"
    
    echo "$UNIQUE_DIR" > "$STATE_FILE"
    echo "Provisioning new workspace: $UNIQUE_DIR"
    docker exec openlane mkdir -p $UNIQUE_DIR || exit 1
fi


# 3. Create the destination folder inside the container
docker exec openlane mkdir -p $UNIQUE_DIR || exit 1

# 4.Copy from host 'sources/' to container
# This ensures each run starts with a fresh baseline netlist
docker cp ./sources/. openlane:$UNIQUE_DIR/ || exit 1

# 5. Run OpenSTA inside that isolated folder
docker exec openlane bash -c "cd $UNIQUE_DIR && sta -no_init run_sta.tcl"|| exit 1
docker exec openlane cat $UNIQUE_DIR/timing_report.rpt || exit 1

docker exec openlane bash -c "cd $UNIQUE_DIR && yosys area.ys" || exit 1
docker exec openlane cat $UNIQUE_DIR/area.rpt || exit 1



