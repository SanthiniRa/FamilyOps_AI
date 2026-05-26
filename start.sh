#!/bin/bash
# Start both backend and frontend

echo "Starting FamilyOps AI Platform..."

# Start backend in background
cd backend && python -m uvicorn main:app --host localhost --port 8000 --reload &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID) on http://localhost:8000"

# Wait for backend to be ready
sleep 2

# Start frontend
cd ../frontend && npm run dev
