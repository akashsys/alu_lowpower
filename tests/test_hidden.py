import os
import re
import subprocess
import pytest
from pathlib import Path
from cocotb_tools.runner import get_runner
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import uuid
import time
import tempfile
import shutil
import atexit

# --- WINDOWS DOCKER CONFIG ---
# Force use of the TCP bridge you enabled in Docker Desktop
os.environ["DOCKER_HOST"] = "tcp://localhost:2375"

if "ACTIVE_CONTAINER_ID" not in os.environ:
    os.environ["ACTIVE_CONTAINER_ID"] = f"openlane_{os.getpid()}_{uuid.uuid4().hex[:8]}"

CONTAINER_ID = os.environ["ACTIVE_CONTAINER_ID"]
def get_dynamic_container_path(state_file_override=None):
    """Get unique task path with high-resolution timestamp to prevent collisions"""
    if state_file_override:
        state_file = state_file_override
    else:
        # Check if we are in an isolated parallel job
        base_dir = os.getenv("ISOLATED_SOURCES")
        if base_dir:
            state_file = Path(base_dir).resolve() / ".task_dir"
        else:
            # Standard fallback
            test_dir = Path(__file__).resolve().parent
            state_file = test_dir.parent / "sources" / ".task_dir"
    
    if state_file.exists():
        path = state_file.read_text().strip()
        if path:
            return path
            
    # Generate unique path with nanosecond timestamp + PID + UUID
    # This prevents collisions even with simultaneous starts
    timestamp_ns = int(time.time() * 1e9)
    pid = os.getpid()
    unique_id = uuid.uuid4().hex[:8]
    task_id = f"task_{timestamp_ns}_{pid}_{unique_id}"
    
    # Write to state file for this process
    task_path = f"/openlane/{task_id}"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(task_path)
    
    return task_path


# ==============================================================================
# 1. THE PYTEST RUNNER
# ==============================================================================
def test_vlsi_signoff_runner():
    """Orchestrates sync and Cocotb simulation."""
    # os.environ["DOCKER_HOST"] = "tcp://127.0.0.1:2375"
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    
    sim = os.getenv("SIM", "icarus")
    
    # --- DYNAMIC PATH DISCOVERY ---
    # Look for the sandbox path exported by the bash script
    base_dir = os.getenv("ISOLATED_SOURCES")
    if base_dir:
        sources_dir = Path(base_dir).resolve()
        # In the sandbox, .task_dir is directly inside sources/
        state_file = sources_dir / ".task_dir"
    else:
        # Fallback for manual local runs
        proj_path = Path(__file__).resolve().parent.parent 
        sources_dir = proj_path / "sources"
        state_file = sources_dir / ".task_dir"

    # Resolve dynamic path for this specific agent task
    # (Pass the state_file path to your helper if needed)
    current_task_path = get_dynamic_container_path(state_file)

    # --- Step 1: Ensure unique container exists ---
    print(f"\n>>> Using unique container: {CONTAINER_ID}")
    print(f">>> Task path: {current_task_path}")
    
    # Check if this specific container exists
    result = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={CONTAINER_ID}"],
        capture_output=True,
        text=True
    )
    
    if not result.stdout.strip():
        print(f">>> Creating new container: {CONTAINER_ID}")
        subprocess.run([
            "docker", "run", "-d", 
            "--name", CONTAINER_ID,
            "efabless/openlane:latest",
            "tail", "-f", "/dev/null"
        ], check=True)
    
    # --- Step 2: Sync to Docker ---
    print(f"\nSyncing to Docker container {CONTAINER_ID} at {current_task_path}...")
    subprocess.run(["docker", "exec", CONTAINER_ID, "mkdir", "-p", current_task_path], check=True)
    subprocess.run(f"docker cp \"{sources_dir}/.\" {CONTAINER_ID}:{current_task_path}/", shell=True, check=True)

    # --- Step 3: Setup Cocotb Runner ---
    netlist_path = sources_dir / "netlist.v"
    rtl_path = sources_dir / "elastic_credit_arbiter.v"

    if not netlist_path.exists():
        print(">>> [INIT] Netlist not found. Generating initial baseline netlist...")
        # Execute the synthesis portion ONLY
        subprocess.run([
            "docker", "exec", CONTAINER_ID, "bash", "-c", 
            f"cd {current_task_path} && yosys -s syn_script.ys"
        ], check=True)
        # Pull it to host so the runner can build the simulation
        subprocess.run([
            "docker", "cp", f"{CONTAINER_ID}:{current_task_path}/netlist.v", str(netlist_path)
        ], check=True)
    else:
        print(">>> [SKIP] Netlist exists. Using current version for testing.")

    #sources = [netlist_path]
    sources = [rtl_path]
    runner = get_runner(sim)

    runner.build(
        sources=sources,
        hdl_toplevel="elastic_credit_arbiter",
        always=True,
        build_args=[
            f"-y{sources_dir}/cells/base",
            f"-y{sources_dir}/cells/strength", 
            f"-y{sources_dir}/models",          
            f"-I{sources_dir}/cells/base",      
            f"-I{sources_dir}/models",   
            "-Y.v",     
            "-grelative-include",
        ]
    )    

    runner.test(
        hdl_toplevel="elastic_credit_arbiter",
        test_module=Path(__file__).stem,
        extra_env={"ACTIVE_CONTAINER_ID": CONTAINER_ID}
    )

# ==============================================================================
# 2. THE COCOTB TESTS (VLSI Sign-off Checks)
# ==============================================================================

@cocotb.test()
async def test_wns_slack(dut):
    """Cocotb Test: Worst Negative Slack check via Dynamic Docker Path"""
    #os.environ["DOCKER_HOST"] = "tcp://127.0.0.1:2375"
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    current_task_path = get_dynamic_container_path()
    WNS_TARGET = 0
    
    # Create unique temp directory for this test instance (prevents file conflicts)
    test_tmpdir = tempfile.mkdtemp(prefix=f"test_timing_{os.getpid()}_")
    
    try:
        dut._log.info(f"Analyzing Timing in: {current_task_path}")
        dut._log.info(f"Using container: {CONTAINER_ID}")
        dut._log.info(f"Temp directory: {test_tmpdir}")

        # --- Step 1: Execute STA ---
        # We use the dynamic path resolved from .task_dir
        cmd = ["docker", "exec", CONTAINER_ID, "bash", "-c", 
               f"cd {current_task_path} && sta -no_init run_sta.tcl"]
        subprocess.run(cmd, check=True)

        # --- Step 2: Copy report to unique location ---
        timing_rpt = os.path.join(test_tmpdir, "timing_report.rpt")
        subprocess.run(
            f"docker cp {CONTAINER_ID}:{current_task_path}/timing_report.rpt \"{timing_rpt}\"", 
            shell=True, check=True
        )

        # --- Step 3: Parse and Validate ---
        with open(timing_rpt, "r") as f:
            report_content = f.read()

        all_slacks = re.findall(r"([-+]?[\d\.]+)\s+slack", report_content)

        if all_slacks:
            wns = min(float(s) for s in all_slacks)
            status_msg = f"WNS is {wns}ns (Target: >= {WNS_TARGET}ns)"
            
            if wns >= WNS_TARGET:
                dut._log.info(f"TIMING MET: {status_msg}")
            else:
                dut._log.error(f"TIMING VIOLATED: {status_msg}")

            assert wns >= WNS_TARGET, f"Timing check failed: {status_msg}"
        else:
            raise RuntimeError("Slack not found in report.")
    
    finally:
        # Cleanup temp directory
        shutil.rmtree(test_tmpdir, ignore_errors=True)

@cocotb.test()
async def test_area_constraint(dut):
    """Cocotb Test: Chip Area check via script.ys and report extraction"""
    os.environ["DOCKER_HOST"] = "tcp://host.docker.internal:2375"
    current_task_path = get_dynamic_container_path()
    AREA_CEILING = 10556.0
    
    # Create unique temp directory for this test instance (prevents file conflicts)
    test_tmpdir = tempfile.mkdtemp(prefix=f"test_area_{os.getpid()}_")
    
    try:
        dut._log.info(f"Analyzing Area in: {current_task_path}")
        dut._log.info(f"Using container: {CONTAINER_ID}")
        dut._log.info(f"Temp directory: {test_tmpdir}")

        # --- Step 1: Execute Yosys using the .ys script ---
        # This generates the area.rpt inside the container
        cmd = ["docker", "exec", CONTAINER_ID, "bash", "-c", 
               f"cd {current_task_path} && yosys area.ys"]
        subprocess.run(cmd, check=True)

        # --- Step 2: Copy report to unique location ---
        # Parity with timing_report.rpt logic
        area_rpt = os.path.join(test_tmpdir, "area.rpt")
        subprocess.run(
            f"docker cp {CONTAINER_ID}:{current_task_path}/area.rpt \"{area_rpt}\"", 
            shell=True, check=True
        )

        # --- Step 3: Parse and Validate ---
        with open(area_rpt, "r") as f:
            report_content = f.read()

        # Capture the area number
        area_match = re.search(r"Chip area.*:\s*([\d\.]+)", report_content)

        if area_match:
            current_area = float(area_match.group(1))
            current_area_rd = round(current_area, 3)
            status_msg = f"Area is {current_area_rd} um^2 (Target: <= {AREA_CEILING})"
            
            if current_area_rd <= AREA_CEILING:
                dut._log.info(f"AREA MET: {status_msg}")
            else:
                dut._log.error(f"AREA VIOLATED: {status_msg}")

            assert current_area_rd <= AREA_CEILING, f"Area check failed: {status_msg}"
        else:
            # Debugging aid: show what the file actually contains if parsing fails
            dut._log.error(f"Regex failed. Report snippet:\n{report_content[-200:]}")
            raise RuntimeError("Area data not found in area.rpt.")
    
    finally:
        # Cleanup temp directory
        shutil.rmtree(test_tmpdir, ignore_errors=True)



# ==============================================================================
# 3. FUNCTIONAL TESTS (Hardware Logic)
# ==============================================================================

async def reset_dut(dut):
    dut.rst_n.value = 0
    await Timer(10, unit="ns")
    dut.rst_n.value = 1

@cocotb.test()
async def test_1_fixed_priority(dut):
    """Functional Check 1: Fixed Priority (Port 0 > Port 3)."""
    clock = Clock(dut.clk, 3.2, unit="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # --- 1. Fixed Priority Check ---
    dut.packet_size.value = 0x10
    dut.request.value = 0b1001 
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.grant.value == 0b0001, f"Port 0 should win via fixed priority. Got {dut.grant.value}"
    dut._log.info("Fixed Priority Verified.")

@cocotb.test()
async def test_2a_starvation_escalation(dut):
    clock = Clock(dut.clk, 3.2, unit="ns") #define clk
    cocotb.start_soon(clock.start()) #start clk
    await reset_dut(dut) #reset applied

    dut.packet_size.value = 0x10 #packet value 16
    dut.request.value = 0b1001 #req is port 0 nd port3

    for _ in range(40):  # AGE_THRESH = 32
        await RisingEdge(dut.clk) 

    await RisingEdge(dut.clk) #sampling,eligiblity,spec calc,aging criteria- port0 port3 aged,high pri req activated
    await RisingEdge(dut.clk) #arbitration-high pre req is 1001,so port 0 wins
    await RisingEdge(dut.clk) #state updated
    await Timer(1, unit="ns")

    # Both aged → fixed priority → Port-0 must win
    assert dut.grant.value == 0b0001, (
        f"FAIL: Both aged → Port-0 must win. Got {dut.grant.value}"
    )

    dut._log.info("PASS: Both aged → Port-0 wins (fixed priority)")

#@cocotb.test()
#async def test_2b_starvation_escalation(dut):
 #   clock = Clock(dut.clk, 3.2, unit="ns") #define clk
  #  cocotb.start_soon(clock.start()) #start clk
    #await reset_dut(dut) #reset applied

    #dut.request.value = 0b1000 
    #for _ in range(40):
     #   await RisingEdge(dut.clk)

    # Step 2: Introduce a fresh request on Port 2
   # dut.packet_size.value = 0x10
    #dut.request.value = 0b1100 # Port 3 (Aged) + Port 2 (Normal)

    # Pipeline turnaround: 3 edges for stabilization after a request change
    #await RisingEdge(dut.clk) 
    #await RisingEdge(dut.clk)  
    #await RisingEdge(dut.clk)     
    #await Timer(1, unit="ns")

    #assert dut.grant.value == 0b1000, f"FAIL: Aged Port-3 must beat normal Port-2. Got {dut.grant.value}"
    #dut._log.info("PASS: Aging escalation verified (Aged beats Normal).")
    #dut._log.info("PASS: Aging escalation verified (aged beats normal)")


@cocotb.test()
async def test_3_elastic_credit_recovery(dut):
    """
    Functional Check 3 (Elastic Credit):
    - Grant must be BLOCKED immediately if credits are insufficient
    - Grant MUST eventually succeed after elastic refill
    """
    clock = Clock(dut.clk, 3.2, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Step 1: Drain credits aggressively
    dut.packet_size.value = 0x80
    dut.request.value = 0b0001   # Port 0

    # Consume credits
    for _ in range(3):
        await RisingEdge(dut.clk)

    # Step 2: Request more than remaining credit
    dut.packet_size.value = 0xF0
    dut.request.value = 0b0001

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Immediate denial expected
    assert dut.grant_valid.value == 0, \
        "Grant issued immediately despite insufficient credits"

    # Step 3: Wait for elastic refill
    dut.request.value = 0b0000
    for _ in range(50):
        await RisingEdge(dut.clk)

    # Step 4: Retry request
    dut.packet_size.value = 0x40
    dut.request.value = 0b0001

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Grant must now succeed
    assert dut.grant.value == 0b0001 and dut.grant_valid.value == 1, \
        "Elastic refill failed to recover credits"

    dut._log.info("Elastic Credit Recovery Verified.")


@cocotb.test()
async def test_4_elastic_increment(dut):
    """Functional Check 4: Elasticity (Credit Refill over time)."""
    clock = Clock(dut.clk, 3.2, unit="ns") 
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # --- PRE-CONDITION: Drain credits completely ---
    dut.packet_size.value = 0xFF 
    dut.request.value = 0b0001
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # --- 4. Elastic Increment Check ---
    dut.request.value = 0x0
    for _ in range(200): # Idle to allow refill
        await RisingEdge(dut.clk)

    dut.packet_size.value = 0x20 
    dut.request.value = 0b0001
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
 
    
    assert dut.grant.value == 0b0001 and dut.grant_valid.value == 1, f"Elastic refill failed. Got grant={dut.grant.value}"


# ==============================================================================
# 4. CLEANUP HANDLER
# ==============================================================================

def cleanup_container():
    """Cleanup this test's unique container"""
    print(f"\n>>> Cleaning up container: {CONTAINER_ID}")
    try:
        subprocess.run(
            ["docker", "stop", CONTAINER_ID], 
            stderr=subprocess.DEVNULL, 
            timeout=10,
            check=False
        )
        subprocess.run(
            ["docker", "rm", CONTAINER_ID], 
            stderr=subprocess.DEVNULL, 
            timeout=10,
            check=False
        )
        print(f">>> Container {CONTAINER_ID} cleaned up successfully")
    except Exception as e:
        print(f">>> Warning: Container cleanup failed: {e}")

# Register cleanup on exit
atexit.register(cleanup_container)