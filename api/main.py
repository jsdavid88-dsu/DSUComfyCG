from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import os
import json

app = FastAPI(title="DSUComfyCG Modular API", version="1.0.0")

class WorkflowRequest(BaseModel):
    workflow_name: str
    prompt: dict
    client_id: str = "dsu_api_client"

@app.get("/")
async def root():
    return {"message": "DSUComfyCG Modular API is running", "status": "healthy"}

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

@app.post("/execute")
async def execute_workflow(request: WorkflowRequest):
    # TODO: Connect to ComfyUI websocket/API to trigger workflow
    return {"status": "received", "workflow": request.workflow_name}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8188)  # Bind to localhost only for security
