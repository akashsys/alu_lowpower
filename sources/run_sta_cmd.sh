#!/bin/bash
# Smart ECO workflow with TIMEOUT PROTECTION
# - Re-synthesizes when RTL is modified
# - Skips synthesis when only netlist (ECO) is modified
# - Supports parallel runs with unique containers per workspace
# - TIMEOUT SAFETY: Synthesis has 180s timeout, falls back to fast mode

# REMOVED: Windows-specific DOCKER_HOST TCP bridge. 
# Linux defaults to the local Unix socket /var/run/docker.sock automatically.

# Configuration
SYNTHESIS_TIMEOUT=180  # 3 minutes for synthesis
STA_TIMEOUT=60         # 1 minute for STA
AREA_TIMEOUT=30        # 30 seconds for area analysis

# State files
STATE_FILE="./sources/.active_task_id"
CONTAINER_FILE="./sources/.container_name"
RTL_FILE="./sources/elastic_credit_arbiter.v"
NETLIST_FILE="./sources/netlist.v"

# ==============================================================================
# CONTAINER MANAGEMENT (Reuse same container for same workspace)
# ==============================================================================

if [ -f "$CONTAINER_FILE" ]; then
    # Resume: Use existing container
    CONTAINER_NAME=$(cat "$CONTAINER_FILE")
    echo ">>> RESUMING: Using existing container: $CONTAINER_NAME"
    
    # Check if container still exists
    if [ ! "$(docker ps -a -q -f name=$CONTAINER_NAME)" ]; then
        echo ">>> WARNING: Previous container $CONTAINER_NAME not found. Creating new one."
        CONTAINER_NAME="openlane_$$_$(uuidgen 2>/dev/null || echo ${RANDOM}${RANDOM})"
        echo "$CONTAINER_NAME" > "$CONTAINER_FILE"
        docker run -d --name "$CONTAINER_NAME" efabless/openlane:latest tail -f /dev/null
        sleep 2
    else
        # Container exists, make sure it's running
        if [ ! "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
            echo ">>> Starting existing container: $CONTAINER_NAME"
            docker start "$CONTAINER_NAME"
            sleep 1
        else
            echo ">>> Container $CONTAINER_NAME already running"
        fi
    fi
else
    # First run: Create new container
    CONTAINER_NAME="openlane_$$_$(uuidgen 2>/dev/null || echo ${RANDOM}${RANDOM})"
    echo "$CONTAINER_NAME" > "$CONTAINER_FILE"
    echo ">>> FIRST RUN: Creating new container: $CONTAINER_NAME"
    docker run -d --name "$CONTAINER_NAME" efabless/openlane:latest tail -f /dev/null
    
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create container"
        exit 1
    fi
    sleep 2
fi

# ==============================================================================
# DIRECTORY MANAGEMENT (Reuse same directory for iterative work)
# ==============================================================================

if [ -f "$STATE_FILE" ]; then
    # Resume: Use existing directory
    TASK_ID=$(cat "$STATE_FILE")
    UNIQUE_DIR="/openlane/$TASK_ID"
    echo ">>> RESUMING: Using existing directory $UNIQUE_DIR"
else
    # First run: Create new directory
    TIMESTAMP_NS=$(date +%s%N 2>/dev/null || echo $(date +%s)999999999)
    TASK_ID="task_${TIMESTAMP_NS}_$$_${RANDOM}${RANDOM}"
    UNIQUE_DIR="/openlane/$TASK_ID"
    echo "$TASK_ID" > "$STATE_FILE"
    echo ">>> FIRST RUN: Creating new directory $UNIQUE_DIR"
fi

echo ">>> Task ID: $TASK_ID"
echo ">>> Container: $CONTAINER_NAME"
echo ">>> Directory: $UNIQUE_DIR"

# ==============================================================================
# SMART SYNTHESIS DECISION
# ==============================================================================

SHOULD_SYNTHESIZE=false

if [ ! -f "$NETLIST_FILE" ]; then
    echo ">>> DECISION: Netlist not found → SYNTHESIZE"
    SHOULD_SYNTHESIZE=true
elif [ "$RTL_FILE" -nt "$NETLIST_FILE" ]; then
    echo ">>> DECISION: RTL modified after netlist → RE-SYNTHESIZE"
    echo "    RTL file: $RTL_FILE"
    echo "    Netlist:  $NETLIST_FILE"
    echo "    RTL is newer, regenerating netlist from RTL"
    SHOULD_SYNTHESIZE=true
else
    echo ">>> DECISION: Netlist is current → SKIP SYNTHESIS (ECO mode)"
    echo "    Netlist: $NETLIST_FILE (newer or same as RTL)"
    echo "    Using existing netlist with any ECO modifications"
    SHOULD_SYNTHESIZE=false
fi

# ==============================================================================
# SYNC FILES TO CONTAINER
# ==============================================================================

echo ">>> Syncing sources to container..."
docker exec "$CONTAINER_NAME" mkdir -p "$UNIQUE_DIR" 2>/dev/null
docker cp "./sources/." "$CONTAINER_NAME":"$UNIQUE_DIR/"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to sync sources"
    exit 1
fi

# ==============================================================================
# SYNTHESIS WITH TIMEOUT PROTECTION (Conditional based on smart decision)
# ==============================================================================

if [ "$SHOULD_SYNTHESIZE" = true ]; then
    echo ""
    echo "============================================================"
    echo "RUNNING SYNTHESIS (Timeout: ${SYNTHESIS_TIMEOUT}s)"
    echo "============================================================"
    
    # Try optimized synthesis first (with timeout)
    echo ">>> Attempting optimized synthesis..."
    timeout $SYNTHESIS_TIMEOUT docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && yosys -s syn_script.ys" 2>&1
    SYNTH_EXIT=$?
    
    if [ $SYNTH_EXIT -eq 124 ]; then
        # Timeout occurred
        echo ""
        echo "⚠️  WARNING: Optimized synthesis timed out after ${SYNTHESIS_TIMEOUT}s"
        echo ">>> Falling back to FAST synthesis mode (no timing optimization)..."
        echo ""
        
        # Fall back to fast synthesis
        timeout $SYNTHESIS_TIMEOUT docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && yosys -s syn_script_fast.ys" 2>&1
        SYNTH_EXIT=$?
        
        if [ $SYNTH_EXIT -eq 124 ]; then
            echo "ERROR: Even fast synthesis timed out. RTL may have elaboration issues."
            echo "Check for:"
            echo "  - Infinite loops in combinational logic"
            echo "  - Very deep logic nesting"
            echo "  - Large arrays or memories"
            exit 1
        elif [ $SYNTH_EXIT -ne 0 ]; then
            echo "ERROR: Fast synthesis failed with exit code $SYNTH_EXIT"
            exit 1
        fi
        
        echo "✓ Fast synthesis completed (may not meet timing, use ECO to fix)"
    elif [ $SYNTH_EXIT -ne 0 ]; then
        echo "ERROR: Synthesis failed with exit code $SYNTH_EXIT"
        exit 1
    else
        echo "✓ Optimized synthesis completed"
    fi
    
    # Copy fresh netlist to host for potential ECO
    echo ">>> Copying fresh netlist to host..."
    docker cp "$CONTAINER_NAME":"$UNIQUE_DIR/netlist.v" "./sources/netlist.v"
    
    # Update netlist timestamp to be newer than RTL
    touch "./sources/netlist.v"
    
    echo ">>> Synthesis complete. Netlist ready for ECO modifications."
else
    echo ""
    echo "============================================================"
    echo "SKIPPING SYNTHESIS (ECO Mode Active)"
    echo "============================================================"
    echo "Using existing netlist from: $NETLIST_FILE"
    echo ""
    echo "If you made ECO changes with eco_fix.py, they are preserved."
    echo "If you want to re-synthesize from RTL, run:"
    echo "  touch $RTL_FILE  (or modify the RTL file)"
fi

# ==============================================================================
# AREA ANALYSIS WITH TIMEOUT (Always run on current netlist)
# ==============================================================================

echo ""
echo ">>> STATUS: Analyzing area on current netlist (Timeout: ${AREA_TIMEOUT}s)..."
timeout $AREA_TIMEOUT docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && yosys -s area.ys" 2>&1 | tail -20

if [ ${PIPESTATUS[0]} -eq 124 ]; then
    echo "⚠️  WARNING: Area analysis timed out"
elif [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "ERROR: Area analysis failed"
    exit 1
fi

# ==============================================================================
# TIMING ANALYSIS WITH TIMEOUT (Always run on current netlist)
# ==============================================================================

echo ">>> STATUS: Running STA on current netlist (Timeout: ${STA_TIMEOUT}s)..."
timeout $STA_TIMEOUT docker exec "$CONTAINER_NAME" bash -c "cd $UNIQUE_DIR && sta -no_init run_sta.tcl" 2>&1

if [ $? -eq 124 ]; then
    echo "⚠️  WARNING: STA timed out after ${STA_TIMEOUT}s"
elif [ $? -ne 0 ]; then
    echo "ERROR: Timing analysis failed"
    exit 1
fi

# ==============================================================================
# SHOW REPORTS
# ==============================================================================

echo ""
echo "============================================================"
echo "AREA REPORT:"
echo "============================================================"
docker exec "$CONTAINER_NAME" cat "$UNIQUE_DIR/area_report.rpt" 2>/dev/null || echo "Area report not found"

echo ""
echo "============================================================"
echo "TIMING REPORT:"
echo "============================================================"
docker exec "$CONTAINER_NAME" cat "$UNIQUE_DIR/timing_report.rpt" 2>/dev/null || echo "Timing report not found"
echo "============================================================"

# ==============================================================================
# COPY RESULTS BACK TO HOST
# ==============================================================================

echo ""
echo ">>> STATUS: Copying results back to host..."

# Always copy netlist (may have been updated)
docker cp "$CONTAINER_NAME":"$UNIQUE_DIR/netlist.v" "./sources/netlist.v" 2>/dev/null

# Copy reports to workspace root for easy access
docker cp "$CONTAINER_NAME":"$UNIQUE_DIR/timing_report.rpt" "./timing_report.rpt" 2>/dev/null
docker cp "$CONTAINER_NAME":"$UNIQUE_DIR/area_report.rpt" "./area_report.rpt" 2>/dev/null

# ==============================================================================
# SUMMARY & NEXT STEPS
# ==============================================================================

echo ""
echo "============================================================"
echo "SESSION SUMMARY"
echo "============================================================"
echo "Container: $CONTAINER_NAME (persistent)"
echo "Directory: $UNIQUE_DIR (persistent)"
echo "State: Saved in $STATE_FILE and $CONTAINER_FILE"
echo ""

if [ "$SHOULD_SYNTHESIZE" = true ]; then
    echo "Mode: SYNTHESIS (Fresh netlist generated)"
    echo ""
    echo "Next steps:"
    echo "  1. Check timing report above"
    echo "  2. If timing violated, apply ECO fixes:"
    echo "      python sources/eco_fix.py --instance _XXXX_ --new_cell sky130_...._1"
    echo "  3. Run this script again (will use ECO mode)"
else
    echo "Mode: ECO (Working with existing netlist)"
    echo ""
    echo "Next steps:"
    echo "  - Apply more ECO fixes if needed"
    echo "  - To re-synthesize from RTL: touch $RTL_FILE"
fi
echo "============================================================"