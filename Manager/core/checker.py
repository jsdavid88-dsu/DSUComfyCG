"""
DSUComfyCG Manager - Core Checker Module (v4 - Using ComfyUI-Manager CLI)
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

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
CM_CLI_PATH = os.path.join(CUSTOM_NODES_PATH, "ComfyUI-Manager", "cm-cli.py")

# GitHub API for workflow sync
WORKFLOWS_REPO_URL = "https://api.github.com/repos/jsdavid88-dsu/DSUComfyCG/contents/workflows"

# Built-in nodes (never need installation)
BUILTIN_NODES = {
    "CheckpointLoaderSimple", "KSampler", "KSamplerAdvanced", "EmptyLatentImage",
    "CLIPTextEncode", "VAEDecode", "VAEEncode", "SaveImage", "LoadImage",
    "PreviewImage", "LoraLoader", "CLIPSetLastLayer", "ConditioningCombine",
    "ConditioningSetArea", "LatentUpscale", "LatentUpscaleBy", "ImageScale",
    "ImageScaleBy", "CLIPLoader", "DualCLIPLoader", "VAELoader", "UNETLoader",
    "ControlNetLoader", "ControlNetApplyAdvanced", "Note", "Reroute", "PrimitiveNode",
    "SetLatentNoiseMask", "LatentComposite", "MaskToImage", "ImageToMask",
    "SolidMask", "InvertMask", "CropMask", "FeatherMask", "GrowMask",
    "ConditioningSetMask", "ConditioningConcat", "CLIPVisionLoader", "CLIPVisionEncode",
    "unCLIPConditioning", "GLIGENLoader", "GLIGENTextBoxApply", "InpaintModelConditioning",
    "ControlNetApply", "LoadImageMask", "ImagePadForOutpaint", "ImageCompositeMasked",
    "MaskComposite", "ImageBlend", "PorterDuffImageComposite", "SplitImageWithAlpha",
    "JoinImageWithAlpha", "ImageBatch", "RebatchLatents", "RebatchImages",
}


def run_cm_cli(command, *args):
    """Run ComfyUI-Manager CLI command."""
    if not os.path.exists(CM_CLI_PATH):
        logger.error("ComfyUI-Manager not found!")
        return None, "ComfyUI-Manager not installed"
    
    cmd = [PYTHON_PATH, CM_CLI_PATH, command] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=BASE_DIR,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return None, "Command timed out"
    except Exception as e:
        return None, str(e)


def get_installed_nodes():
    """Get list of installed custom nodes using cm-cli."""
    stdout, stderr = run_cm_cli("show", "installed")
    if stdout:
        # Parse the output
        installed = []
        for line in stdout.strip().split('\n'):
            if line.strip() and not line.startswith('#'):
                installed.append(line.strip())
        return installed
    return []


def find_node_package(node_type):
    """Find which package provides a node type using cm-cli."""
    # Try searching for the node
    stdout, stderr = run_cm_cli("show", "node", node_type)
    if stdout and "not found" not in stdout.lower():
        # Parse package info from output
        for line in stdout.strip().split('\n'):
            if 'http' in line.lower() or 'github' in line.lower():
                return line.strip()
    return None


def install_node_by_url(git_url):
    """Install a node package using cm-cli."""
    stdout, stderr = run_cm_cli("install", git_url)
    if stderr and "error" in stderr.lower():
        return False, stderr
    return True, stdout or "Installed successfully"


def check_missing_nodes_for_workflow(workflow_path):
    """Use cm-cli to check missing nodes for a workflow."""
    if not os.path.exists(workflow_path):
        return []
    
    stdout, stderr = run_cm_cli("deps-in-workflow", "--workflow", workflow_path)
    
    missing = []
    if stdout:
        # Parse missing nodes from output
        in_missing_section = False
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if 'missing' in line.lower():
                in_missing_section = True
                continue
            if in_missing_section and line:
                if line.startswith('-') or line.startswith('*'):
                    missing.append(line.lstrip('-* ').strip())
                elif ':' in line:
                    # Format: "NodeType: package_url"
                    parts = line.split(':', 1)
                    missing.append({
                        "node": parts[0].strip(),
                        "package": parts[1].strip() if len(parts) > 1 else None
                    })
    
    return missing


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
                node_type = node.get("type") or node.get("class_type")
                if node_type:
                    node_types.add(node_type)
                
                # Extract model names
                widgets = node.get("widgets_values") or []
                for val in widgets:
                    if isinstance(val, str):
                        lower = val.lower()
                        if lower.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.gguf')):
                            model_names.add(val)
    except Exception as e:
        logger.error(f"Failed to parse {filename}: {e}")
    
    return list(node_types), list(model_names)


def check_node_installed(node_type):
    """Check if a node type is installed. Returns (installed, folder_name, install_cmd)."""
    import re
    
    # Check if builtin
    if node_type in BUILTIN_NODES:
        return True, "Builtin", None
    
    # Normalize name (remove parentheses suffix)
    normalized = re.sub(r'\s*\([^)]+\)\s*$', '', node_type).strip()
    
    # Try to find package using cm-cli
    package_url = find_node_package(normalized)
    if package_url:
        folder_name = package_url.rstrip('/').split('/')[-1].replace('.git', '')
        node_path = os.path.join(CUSTOM_NODES_PATH, folder_name)
        return os.path.exists(node_path), folder_name, package_url
    
    # Fallback: scan custom_nodes folders
    if os.path.exists(CUSTOM_NODES_PATH):
        search_term = normalized.lower().replace('_', '').replace(' ', '')
        for folder in os.listdir(CUSTOM_NODES_PATH):
            folder_lower = folder.lower().replace('-', '').replace('_', '')
            if search_term in folder_lower or folder_lower in search_term:
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
        installed, folder, install_cmd = check_node_installed(nt)
        
        # Deduplicate by folder
        if folder not in seen_folders or folder in ("Unknown", "Builtin"):
            nodes_status.append({
                "type": nt,
                "folder": folder,
                "installed": installed,
                "url": install_cmd
            })
            if folder not in ("Unknown", "Builtin"):
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


def install_node(git_url):
    """Install a custom node."""
    if not git_url:
        return False, "No URL provided"
    
    # Use cm-cli if available
    if os.path.exists(CM_CLI_PATH):
        return install_node_by_url(git_url)
    
    # Fallback to direct git clone
    repo_name = git_url.rstrip('/').split("/")[-1].replace(".git", "")
    target_path = os.path.join(CUSTOM_NODES_PATH, repo_name)
    
    if os.path.exists(target_path):
        return True, f"{repo_name} already exists"
    
    try:
        subprocess.check_call(
            ["git", "clone", "--depth", "1", git_url, target_path],
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )
        
        # Install requirements
        req_file = os.path.join(target_path, "requirements.txt")
        if os.path.exists(req_file) and os.path.getsize(req_file) > 0:
            subprocess.run(
                [PYTHON_PATH, "-m", "pip", "install", "-r", req_file, "--quiet"],
                capture_output=True
            )
        
        return True, f"Installed {repo_name}"
    except Exception as e:
        return False, str(e)


def install_missing_for_workflow(workflow_file):
    """Install all missing nodes for a workflow using cm-cli."""
    if not os.path.exists(CM_CLI_PATH):
        return False, "ComfyUI-Manager not found"
    
    workflow_path = os.path.join(WORKFLOWS_DIR, workflow_file)
    stdout, stderr = run_cm_cli("install-deps", "--workflow", workflow_path)
    
    if stderr and "error" in stderr.lower():
        return False, stderr
    return True, stdout or "Dependencies installed"


def get_system_status():
    """Get system information."""
    status = {
        "comfyui_installed": os.path.exists(COMFY_PATH),
        "python_installed": os.path.exists(PYTHON_PATH),
        "cm_cli_available": os.path.exists(CM_CLI_PATH),
        "python_version": None,
        "cuda_available": False,
        "gpu_name": None,
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


def sync_workflows():
    """Sync workflows from GitHub to local folder."""
    if not requests:
        return 0, 0
    
    Path(WORKFLOWS_DIR).mkdir(parents=True, exist_ok=True)
    
    try:
        response = requests.get(WORKFLOWS_REPO_URL, timeout=15)
        response.raise_for_status()
        files = response.json()
    except:
        return 0, 0
    
    synced = 0
    skipped = 0
    
    for f in files:
        if not f.get("name", "").endswith(".json"):
            continue
        
        local_path = os.path.join(WORKFLOWS_DIR, f["name"])
        
        if os.path.exists(local_path):
            skipped += 1
            continue
        
        try:
            if f.get("download_url"):
                response = requests.get(f["download_url"], timeout=30)
                response.raise_for_status()
                with open(local_path, 'wb') as file:
                    file.write(response.content)
                synced += 1
        except:
            pass
    
    return synced, skipped


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
