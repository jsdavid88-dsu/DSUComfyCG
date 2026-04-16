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
REPO_ROOT = os.path.dirname(SCRIPT_DIR)  # DSUComfyCG/ (one level up from Helper/)
PROJECT_ROOT = REPO_ROOT  # kept for backward compat within this file

# Setup portable git (prepend git_portable/cmd to PATH if present)
git_portable = os.path.join(REPO_ROOT, "git_portable", "cmd")
if os.path.isdir(git_portable):
    os.environ["PATH"] = git_portable + os.pathsep + os.environ.get("PATH", "")

# Allow importing Manager.core.checker for active env + git fallback.
# Mirror Manager/main.py which does: sys.path.insert(0, MANAGER_DIR)
_MANAGER_DIR = os.path.join(REPO_ROOT, "Manager")
if _MANAGER_DIR not in sys.path:
    sys.path.insert(0, _MANAGER_DIR)

def _resolve_comfy_path():
    """Resolve ComfyUI path from active env via Manager.core.checker.
    Falls back to failing loudly rather than silently creating empty folders."""
    try:
        from core.checker import get_active_env  # type: ignore
        env = get_active_env() or {}
        env_path = env.get("path", "")
        if env_path:
            # env path may be relative to REPO_ROOT or absolute
            full = env_path if os.path.isabs(env_path) else os.path.join(REPO_ROOT, env_path)
            full = os.path.normpath(full)
            if os.path.isdir(full):
                return full
            logger.error(f"Active ComfyUI env path does not exist: {full}")
        else:
            logger.error("Active ComfyUI env has no 'path' field.")
    except Exception as e:
        logger.error(f"Could not import Manager.core.checker to resolve active env: {e}")
    logger.error("Active ComfyUI env not found. Run Manager first.")
    return None

WORKFLOWS_DIR = os.path.join(REPO_ROOT, "workflows")
CACHE_FILE = os.path.join(SCRIPT_DIR, "processed_workflows.txt")
COMFY_PATH = _resolve_comfy_path()
CUSTOM_NODES_PATH = os.path.join(COMFY_PATH, "custom_nodes") if COMFY_PATH else None

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
    if not CUSTOM_NODES_PATH:
        logger.error("CUSTOM_NODES_PATH unresolved; cannot determine missing nodes.")
        return missing

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

def _find_python_exe():
    """Find python executable: check all envs, then root python_embeded."""
    # Try to find active env from envs.json
    envs_json = os.path.join(PROJECT_ROOT, "Manager", "data", "envs.json")
    if os.path.exists(envs_json):
        try:
            with open(envs_json, 'r', encoding='utf-8') as f:
                envs_data = json.load(f)
            for env_id, env_info in envs_data.items():
                py_path = env_info.get("python_path", "")
                if py_path:
                    full = os.path.join(PROJECT_ROOT, py_path) if not os.path.isabs(py_path) else py_path
                    if os.path.exists(full):
                        return full
        except Exception:
            pass
    # Fallback: scan envs/ directory
    envs_dir = os.path.join(PROJECT_ROOT, "envs")
    if os.path.isdir(envs_dir):
        for env_name in os.listdir(envs_dir):
            candidate = os.path.join(envs_dir, env_name, "python_embeded", "python.exe")
            if os.path.exists(candidate):
                return candidate
    # Last fallback: root python_embeded
    root_py = os.path.join(PROJECT_ROOT, "python_embeded", "python.exe")
    if os.path.exists(root_py):
        return root_py
    return None

def _ensure_git_available():
    """Ensure git is on PATH; fall back to Manager's ensure_git_installed() if import succeeds."""
    import shutil
    if shutil.which("git"):
        return True
    try:
        from core.checker import ensure_git_installed  # type: ignore
        ok, msg = ensure_git_installed()
        logger.info(f"ensure_git_installed: {msg}")
        return ok
    except Exception as e:
        logger.error(f"Git not found and Manager.core.checker import failed: {e}")
        return False

def install_node(url):
    """Clone a node repository and install its requirements."""
    if not CUSTOM_NODES_PATH:
        logger.error("CUSTOM_NODES_PATH unresolved; cannot install node.")
        return False
    repo_name = url.split("/")[-1].replace(".git", "")
    target_path = os.path.join(CUSTOM_NODES_PATH, repo_name)

    if os.path.exists(target_path):
        logger.info(f"{repo_name} already exists")
        return True

    if not _ensure_git_available():
        logger.error(f"Skipping {repo_name}: git unavailable.")
        return False

    try:
        logger.info(f"Installing {repo_name}...")
        subprocess.check_call(["git", "clone", "--depth", "1", "--", url, target_path])

        python_exe = _find_python_exe()
        if not python_exe:
            logger.warning("Python executable not found, skipping dependency install")
            return True

        # Install requirements.txt if exists
        req_file = os.path.join(target_path, "requirements.txt")
        if os.path.exists(req_file) and os.path.getsize(req_file) > 0:
            subprocess.check_call([python_exe, "-m", "uv", "pip", "install", "-r", req_file, "--no-cache"])

        # Run install.py if exists
        install_py = os.path.join(target_path, "install.py")
        if os.path.exists(install_py) and os.path.getsize(install_py) > 0:
            subprocess.check_call([python_exe, install_py])
        
        logger.info(f"Installed {repo_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to install {repo_name}: {e}")
        return False

def main():
    # Fail loudly if workflows folder missing (don't silently create empty folder)
    if not os.path.isdir(WORKFLOWS_DIR):
        logger.error(f"Workflows folder not found at: {WORKFLOWS_DIR}")
        logger.error("Expected <repo-root>/workflows/. Nothing to scan.")
        return

    # Fail loudly if ComfyUI env unresolved (get_missing_nodes / install_node would be no-ops)
    if not COMFY_PATH or not CUSTOM_NODES_PATH:
        logger.error("Active ComfyUI env not found. Run Manager first.")
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
