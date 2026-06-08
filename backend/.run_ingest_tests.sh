#!/usr/bin/env bash
cd /workspaces/FamilyOps_AI/backend
pytest -q tests/test_ingest.py > /tmp/ingest_test_output.txt 2>&1
printf "EXIT:%s\n" $? > /tmp/ingest_test_status.txt
