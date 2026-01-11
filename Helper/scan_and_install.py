"""
DSUComfyCG - Workflow Scanner & Auto-Installer
Scans workflows/*.json for new files and installs missing nodes/models.
"""

import os
import sys
import json
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='[DSUComfyCG] %(message)s')
logger = logging.getLogger("ScanInstall")

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOWS_DIR = os.path.join(SCRIPT_DIR, "workflows")
CACHE_FILE = os.path.join(SCRIPT_DIR, "processed_workflows.txt")
COMFY_PATH = os.path.join(SCRIPT_DIR, "ComfyUI")
CUSTOM_NODES_PATH = os.path.join(COMFY_PATH, "custom_nodes")

# Node Database (expandable)
NODE_DB = {
    "IPAdapterApply": "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git",
    "IPAdapterPlus": "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git",
    "VHS_VideoCombine": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git",
    "VHS_LoadVideo": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git",
    "ControlNetApply": "https://github.com/Fannovel16/comfyui_controlnet_aux.git",
    "LTXVLoader": "https://github.com/Lightricks/ComfyUI-LTXVideo.git",
    "WanVideoSampler": "https://github.com/kijai/ComfyUI-WanVideoWrapper.git",
}

def load_cache():
    """Load list of already processed workflow files."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return set(line.strip() for line in f.readlines())
    return set()

def save_cache(processed):
    """Save processed workflow files to cache."""
    with open(CACHE_FILE, 'w') as f:
        for item in processed:
            f.write(item + '\n')

def parse_workflow(file_path):
    """Extract node types from a workflow JSON."""
    node_types = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        nodes = []
        if isinstance(data, dict):
            if "nodes" in data:
                nodes = data["nodes"]
            else:
                nodes = data.values()
        elif isinstance(data, list):
            nodes = data
        
        for node in nodes:
            if isinstance(node, dict) and "type" in node:
                node_types.add(node["type"])
    except Exception as e:
        logger.error(f"Failed to parse {file_path}: {e}")
    
    return node_types

def get_missing_nodes(node_types):
    """Find missing nodes that need to be installed."""
    missing = {}
    processed_urls = set()
    
    for node_type in node_types:
        if node_type in NODE_DB:
            url = NODE_DB[node_type]
            repo_name = url.split("/")[-1].replace(".git", "")
            node_dir = os.path.join(CUSTOM_NODES_PATH, repo_name)
            
            if not os.path.exists(node_dir):
                if url not in processed_urls:
                    missing[node_type] = url
                    processed_urls.add(url)
    
    return missing

def install_node(url):
    """Clone a node repository and install its requirements."""
    repo_name = url.split("/")[-1].replace(".git", "")
    target_path = os.path.join(CUSTOM_NODES_PATH, repo_name)
    
    if os.path.exists(target_path):
        logger.info(f"{repo_name} already exists")
        return True
    
    try:
        logger.info(f"Installing {repo_name}...")
        subprocess.check_call(["git", "clone", "--depth", "1", url, target_path])
        
        # Install requirements.txt if exists
        req_file = os.path.join(target_path, "requirements.txt")
        if os.path.exists(req_file) and os.path.getsize(req_file) > 0:
            python_exe = os.path.join(SCRIPT_DIR, "python_embeded", "python.exe")
            subprocess.check_call([python_exe, "-m", "uv", "pip", "install", "-r", req_file, "--no-cache"])
        
        # Run install.py if exists
        install_py = os.path.join(target_path, "install.py")
        if os.path.exists(install_py) and os.path.getsize(install_py) > 0:
            python_exe = os.path.join(SCRIPT_DIR, "python_embeded", "python.exe")
            subprocess.check_call([python_exe, install_py])
        
        logger.info(f"Installed {repo_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to install {repo_name}: {e}")
        return False

def main():
    # Create workflows folder if not exists
    if not os.path.exists(WORKFLOWS_DIR):
        os.makedirs(WORKFLOWS_DIR)
        logger.info("Created workflows folder")
        return
    
    # Load cache
    processed = load_cache()
    
    # Scan for new workflows
    all_node_types = set()
    new_files = []
    
    for filename in os.listdir(WORKFLOWS_DIR):
        if filename.endswith(".json"):
            if filename not in processed:
                new_files.append(filename)
                file_path = os.path.join(WORKFLOWS_DIR, filename)
                node_types = parse_workflow(file_path)
                all_node_types.update(node_types)
    
    if not new_files:
        logger.info("No new workflows found")
        return
    
    logger.info(f"Found {len(new_files)} new workflow(s)")
    
    # Find and install missing nodes
    missing = get_missing_nodes(all_node_types)
    
    if missing:
        logger.info(f"Installing {len(missing)} missing node(s)...")
        for node_type, url in missing.items():
            install_node(url)
    else:
        logger.info("All required nodes are already installed")
    
    # Update cache
    processed.update(new_files)
    save_cache(processed)
    logger.info("Workflow scan complete")

if __name__ == "__main__":
    main()
