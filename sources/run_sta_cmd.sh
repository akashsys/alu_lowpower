# 1. Point to the Windows Host bridge
export DOCKER_HOST=tcp://host.docker.internal:2375

# 2. Run the STA tool inside the specialized container
docker exec openlane bash -c "cd /openlane/PHINITY && /openlane/bin/sta -no_init run_sta.tcl"

# 3. Bring the report back if needed
docker cp openlane:/openlane/PHINITY/timing_report.rpt ./timing_report.rpt