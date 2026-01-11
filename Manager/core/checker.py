"""
DSUComfyCG Manager - Core Checker Module (v2 with Online DB)
"""

import os
import sys
import json
import subprocess
import logging
import requests
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[DSUComfyCG] %(message)s')
logger = logging.getLogger("Checker")

# Get base path
MANAGER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(MANAGER_DIR)
WORKFLOWS_DIR = os.path.join(BASE_DIR, "workflows")
COMFY_PATH = os.path.join(BASE_DIR, "ComfyUI")
CUSTOM_NODES_PATH = os.path.join(COMFY_PATH, "custom_nodes")
MODELS_PATH = os.path.join(COMFY_PATH, "models")
PYTHON_PATH = os.path.join(BASE_DIR, "python_embeded", "python.exe")
CACHE_DIR = os.path.join(MANAGER_DIR, "cache")

# URLs
NODE_DB_URL = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/extension-node-map.json"
WORKFLOWS_REPO_URL = "https://api.github.com/repos/jsdavid88-dsu/DSUComfyCG/contents/workflows"

# Ensure cache dir exists
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

# Global NODE_DB (loaded dynamically)
NODE_DB = {}
NODE_DB_CACHE_FILE = os.path.join(CACHE_DIR, "node_db_cache.json")

# Built-in nodes (never need installation)
BUILTIN_NODES = {
    "CheckpointLoaderSimple", "KSampler", "KSamplerAdvanced", "EmptyLatentImage",
    "CLIPTextEncode", "VAEDecode", "VAEEncode", "SaveImage", "LoadImage",
    "PreviewImage", "LoraLoader", "CLIPSetLastLayer", "ConditioningCombine",
    "ConditioningSetArea", "LatentUpscale", "LatentUpscaleBy", "ImageScale",
    "ImageScaleBy", "CLIPLoader", "DualCLIPLoader", "VAELoader", "UNETLoader",
    "ControlNetLoader", "ControlNetApplyAdvanced", "Note", "Reroute", "PrimitiveNode",
}


def fetch_node_db(force_refresh=False):
    """Fetch NODE_DB from ComfyUI-Manager's extension-node-map.json"""
    global NODE_DB
    
    # Check cache first
    if not force_refresh and os.path.exists(NODE_DB_CACHE_FILE):
        try:
            cache_age = os.path.getmtime(NODE_DB_CACHE_FILE)
            import time
            # Use cache if less than 24 hours old
            if time.time() - cache_age < 86400:
                with open(NODE_DB_CACHE_FILE, 'r', encoding='utf-8') as f:
                    NODE_DB = json.load(f)
                    logger.info(f"Loaded NODE_DB from cache ({len(NODE_DB)} entries)")
                    return True
        except:
            pass
    
    try:
        logger.info("Fetching NODE_DB from ComfyUI-Manager...")
        response = requests.get(NODE_DB_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # extension-node-map.json format: 
        # { "git_url": [["NodeType1", "NodeType2", ...], {"title_aux": "..."}], ... }
        NODE_DB = {}
        for git_url, node_info in data.items():
            if not isinstance(node_info, list) or len(node_info) < 1:
                continue
            
            # Get folder name from git URL
            folder_name = git_url.rstrip('/').split('/')[-1].replace('.git', '')
            
            # First element is list of node types
            node_types = node_info[0] if isinstance(node_info[0], list) else []
            
            for node_type in node_types:
                if isinstance(node_type, str):
                    NODE_DB[node_type] = (folder_name, git_url)
        
        # Save to cache
        with open(NODE_DB_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(NODE_DB, f)
        
        logger.info(f"Updated NODE_DB with {len(NODE_DB)} entries")
        return True
    except Exception as e:
        logger.error(f"Failed to fetch NODE_DB: {e}")
        # Try loading from cache as fallback
        if os.path.exists(NODE_DB_CACHE_FILE):
            try:
                with open(NODE_DB_CACHE_FILE, 'r', encoding='utf-8') as f:
                    NODE_DB = json.load(f)
                logger.info(f"Using cached NODE_DB ({len(NODE_DB)} entries)")
                return True
            except:
                pass
        return False


def fetch_workflow_list():
    """Fetch list of workflows from GitHub repo"""
    try:
        response = requests.get(WORKFLOWS_REPO_URL, timeout=15)
        response.raise_for_status()
        files = response.json()
        
        workflows = []
        for f in files:
            if f.get("name", "").endswith(".json"):
                workflows.append({
                    "name": f["name"],
                    "download_url": f.get("download_url"),
                    "sha": f.get("sha")
                })
        return workflows
    except Exception as e:
        logger.error(f"Failed to fetch workflow list: {e}")
        return []


def sync_workflows():
    """Sync workflows from GitHub to local folder"""
    Path(WORKFLOWS_DIR).mkdir(parents=True, exist_ok=True)
    
    remote_workflows = fetch_workflow_list()
    if not remote_workflows:
        return 0, 0
    
    synced = 0
    skipped = 0
    
    for wf in remote_workflows:
        local_path = os.path.join(WORKFLOWS_DIR, wf["name"])
        
        # Check if already exists (simple check, could use sha for smarter sync)
        if os.path.exists(local_path):
            skipped += 1
            continue
        
        # Download
        try:
            if wf.get("download_url"):
                response = requests.get(wf["download_url"], timeout=30)
                response.raise_for_status()
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                synced += 1
                logger.info(f"Downloaded: {wf['name']}")
        except Exception as e:
            logger.error(f"Failed to download {wf['name']}: {e}")
    
    return synced, skipped


def scan_workflows():
    """Scan workflows folder and return list of JSON files."""
    workflows = []
    if os.path.exists(WORKFLOWS_DIR):
        for filename in os.listdir(WORKFLOWS_DIR):
            if filename.endswith(".json"):
                workflows.append(filename)
    return sorted(workflows)


def parse_workflow(filename):
    """Parse a workflow JSON and extract node types and model names."""
    filepath = os.path.join(WORKFLOWS_DIR, filename)
    node_types = set()
    model_names = set()
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nodes = []
        if isinstance(data, dict):
            if "nodes" in data:
                nodes = data["nodes"]
            else:
                nodes = list(data.values())
        elif isinstance(data, list):
            nodes = data
        
        for node in nodes:
            if isinstance(node, dict):
                node_type = node.get("type")
                if node_type:
                    node_types.add(node_type)
                
                # Also check class_type for API format
                class_type = node.get("class_type")
                if class_type:
                    node_types.add(class_type)
                
                # Extract model names
                if "widgets_values" in node and node["widgets_values"]:
                    for val in node["widgets_values"]:
                        if isinstance(val, str):
                            lower = val.lower()
                            if lower.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.bin')):
                                model_names.add(val)
    except Exception as e:
        logger.error(f"Failed to parse {filename}: {e}")
    
    return list(node_types), list(model_names)


def check_node_installed(node_type):
    """Check if a node type is installed. Returns (installed, folder_name, git_url)."""
    # Check if builtin
    if node_type in BUILTIN_NODES:
        return True, "Builtin", None
    
    # Check in NODE_DB
    if node_type in NODE_DB:
        folder_name, git_url = NODE_DB[node_type]
        node_path = os.path.join(CUSTOM_NODES_PATH, folder_name)
        return os.path.exists(node_path), folder_name, git_url
    
    # Try to find by scanning custom_nodes folders
    if os.path.exists(CUSTOM_NODES_PATH):
        for folder in os.listdir(CUSTOM_NODES_PATH):
            # Simple heuristic: check if node_type appears in folder name
            if node_type.lower().replace('_', '') in folder.lower().replace('-', '').replace('_', ''):
                return True, folder, None
    
    return False, "Unknown", None


def check_model_installed(model_name):
    """Check if a model is installed."""
    if os.path.exists(MODELS_PATH):
        for root, dirs, files in os.walk(MODELS_PATH):
            if model_name in files:
                return True, "found", None
    return False, "unknown", None


def check_workflow_dependencies(filename):
    """Check all dependencies for a workflow."""
    node_types, model_names = parse_workflow(filename)
    
    nodes_status = []
    seen_folders = set()
    
    for nt in node_types:
        installed, folder, url = check_node_installed(nt)
        
        # Deduplicate by folder
        if folder not in seen_folders or folder == "Unknown":
            nodes_status.append({
                "type": nt,
                "folder": folder,
                "installed": installed,
                "url": url
            })
            if folder != "Unknown":
                seen_folders.add(folder)
    
    models_status = []
    seen_models = set()
    
    for mn in model_names:
        if mn in seen_models:
            continue
        seen_models.add(mn)
        
        installed, subfolder, url = check_model_installed(mn)
        models_status.append({
            "name": mn,
            "subfolder": subfolder,
            "installed": installed,
            "url": url
        })
    
    return {
        "nodes": nodes_status,
        "models": models_status
    }


def get_system_status():
    """Get system information."""
    status = {
        "comfyui_installed": os.path.exists(COMFY_PATH),
        "python_installed": os.path.exists(PYTHON_PATH),
        "python_version": None,
        "cuda_available": False,
        "gpu_name": None,
        "node_db_size": len(NODE_DB)
    }
    
    if status["python_installed"]:
        try:
            result = subprocess.run(
                [PYTHON_PATH, "--version"],
                capture_output=True, text=True, timeout=5
            )
            status["python_version"] = result.stdout.strip().replace("Python ", "")
        except:
            pass
    
    try:
        result = subprocess.run(
            [PYTHON_PATH, "-c", "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 1:
            status["cuda_available"] = lines[0].strip() == "True"
        if len(lines) >= 2 and lines[1].strip():
            status["gpu_name"] = lines[1].strip()
    except:
        pass
    
    return status


def install_node(git_url):
    """Install a custom node from git URL."""
    if not git_url:
        return False, "No URL provided"
    
    repo_name = git_url.rstrip('/').split("/")[-1].replace(".git", "")
    target_path = os.path.join(CUSTOM_NODES_PATH, repo_name)
    
    if os.path.exists(target_path):
        return True, f"{repo_name} already exists"
    
    try:
        subprocess.check_call(["git", "clone", "--depth", "1", git_url, target_path])
        
        # Install requirements
        req_file = os.path.join(target_path, "requirements.txt")
        if os.path.exists(req_file) and os.path.getsize(req_file) > 0:
            subprocess.check_call([PYTHON_PATH, "-m", "uv", "pip", "install", "-r", req_file, "--no-cache"])
        
        # Run install.py
        install_py = os.path.join(target_path, "install.py")
        if os.path.exists(install_py):
            subprocess.check_call([PYTHON_PATH, install_py])
        
        return True, f"Installed {repo_name}"
    except Exception as e:
        return False, str(e)


def run_comfyui():
    """Launch ComfyUI."""
    try:
        subprocess.Popen(
            [PYTHON_PATH, "-I", os.path.join(COMFY_PATH, "main.py"), "--windows-standalone-build"],
            cwd=BASE_DIR
        )
        return True
    except Exception as e:
        logger.error(f"Failed to start ComfyUI: {e}")
        return False


# Initialize NODE_DB on module load
fetch_node_db()
