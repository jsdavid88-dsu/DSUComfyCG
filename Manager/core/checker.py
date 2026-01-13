"""
DSUComfyCG Manager - Core Checker Module (v5 - Fast NODE_DB + Direct Install)
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
CACHE_DIR = os.path.join(MANAGER_DIR, "cache")

# URLs
NODE_DB_URL = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/extension-node-map.json"
WORKFLOWS_REPO_URL = "https://api.github.com/repos/jsdavid88-dsu/DSUComfyCG/contents/workflows"

# Ensure cache dir exists
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

# Global NODE_DB (loaded dynamically)
NODE_DB = {}
NODE_DB_CACHE_FILE = os.path.join(CACHE_DIR, "node_db_cache.json")

# Model DB (from models_db.json)
MODEL_DB = {}
MODEL_DB_FILE = os.path.join(MANAGER_DIR, "models_db.json")
FOLDER_MAPPINGS = {}

# Built-in nodes
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
    "MarkdownNote",  # Built-in note node
}

# Fallback mappings for nodes not in ComfyUI-Manager DB
FALLBACK_NODE_DB = {
    # ComfyUI-WanAnimatePreprocess nodes
    "OnnxDetectionModelLoader": ("ComfyUI-WanAnimatePreprocess", "https://github.com/kijai/ComfyUI-WanAnimatePreprocess"),
    "PoseAndFaceDetection": ("ComfyUI-WanAnimatePreprocess", "https://github.com/kijai/ComfyUI-WanAnimatePreprocess"),
    "DrawViTPose": ("ComfyUI-WanAnimatePreprocess", "https://github.com/kijai/ComfyUI-WanAnimatePreprocess"),
    # KJNodes Get/Set nodes (different naming in workflow vs DB)
    "GetNode": ("ComfyUI-KJNodes", "https://github.com/kijai/ComfyUI-KJNodes"),
    "SetNode": ("ComfyUI-KJNodes", "https://github.com/kijai/ComfyUI-KJNodes"),
    # ComfyUI-Easy-Use nodes
    "easy getNode": ("ComfyUI-Easy-Use", "https://github.com/yolain/ComfyUI-Easy-Use"),
    "easy setNode": ("ComfyUI-Easy-Use", "https://github.com/yolain/ComfyUI-Easy-Use"),
    # comfyui-various nodes
    "Float-🔬": ("comfyui-various", "https://github.com/jamesWalker55/comfyui-various"),
    # LTX Video nodes
    "LTXVLoader": ("ComfyUI-LTXVideo", "https://github.com/Lightricks/ComfyUI-LTXVideo"),
    # SAM2 / Segment Anything 2 nodes
    "DownloadAndLoadSAM2Model": ("ComfyUI-segment-anything-2", "https://github.com/kijai/ComfyUI-segment-anything-2"),
    "Sam2Segmentation": ("ComfyUI-segment-anything-2", "https://github.com/kijai/ComfyUI-segment-anything-2"),
    "Sam2AutoSegmentation": ("ComfyUI-segment-anything-2", "https://github.com/kijai/ComfyUI-segment-anything-2"),
    "Sam2VideoSegmentation": ("ComfyUI-segment-anything-2", "https://github.com/kijai/ComfyUI-segment-anything-2"),
}


def fetch_node_db(force_refresh=False):
    """Fetch NODE_DB from ComfyUI-Manager's extension-node-map.json"""
    global NODE_DB
    
    # Check cache first
    if not force_refresh and os.path.exists(NODE_DB_CACHE_FILE):
        try:
            import time
            cache_age = os.path.getmtime(NODE_DB_CACHE_FILE)
            if time.time() - cache_age < 86400:  # 24 hours
                with open(NODE_DB_CACHE_FILE, 'r', encoding='utf-8') as f:
                    NODE_DB = json.load(f)
                    logger.info(f"Loaded NODE_DB from cache ({len(NODE_DB)} entries)")
                    return True
        except:
            pass
    
    if not requests:
        return False
    
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
            
            folder_name = git_url.rstrip('/').split('/')[-1].replace('.git', '')
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
                return True
            except:
                pass
        return False


def load_model_db():
    """Load MODEL_DB from models_db.json"""
    global MODEL_DB, FOLDER_MAPPINGS
    
    if not os.path.exists(MODEL_DB_FILE):
        logger.warning("models_db.json not found")
        return False
    
    try:
        with open(MODEL_DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        MODEL_DB = data.get("models", {})
        FOLDER_MAPPINGS = data.get("folder_mappings", {})
        logger.info(f"Loaded MODEL_DB with {len(MODEL_DB)} entries")
        return True
    except Exception as e:
        logger.error(f"Failed to load MODEL_DB: {e}")
        return False


def check_model_in_db(model_name):
    """Check if a model is in our MODEL_DB. Returns (in_db, info_dict)."""
    # Direct match
    if model_name in MODEL_DB:
        return True, MODEL_DB[model_name]
    
    # Try without path prefix (e.g., "Kijai_WAN/file.safetensors" -> "file.safetensors")
    basename = os.path.basename(model_name.replace("\\", "/"))
    if basename in MODEL_DB:
        return True, MODEL_DB[basename]
    
    # Try with path variations
    for key, info in MODEL_DB.items():
        if basename == os.path.basename(key):
            return True, info
    
    return False, None


def download_model(model_name, progress_callback=None):
    """Download a model from HuggingFace. Returns (success, message)."""
    if not requests:
        return False, "requests module not available"
    
    # Check if in our DB
    in_db, info = check_model_in_db(model_name)
    if not in_db:
        return False, f"Model '{model_name}' not found in MODEL_DB"
    
    url = info.get("url")
    folder_key = info.get("folder", "checkpoints")
    
    if not url:
        return False, "No download URL for this model"
    
    # Determine target path
    folder_path = FOLDER_MAPPINGS.get(folder_key, f"ComfyUI/models/{folder_key}")
    target_dir = os.path.join(BASE_DIR, folder_path)
    
    # Use original filename from URL if different
    filename = os.path.basename(model_name.replace("\\", "/"))
    target_path = os.path.join(target_dir, filename)
    
    if os.path.exists(target_path):
        return True, f"Model already exists: {filename}"
    
    # Create directory if needed
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        logger.info(f"Downloading {filename} from {url[:50]}...")
        
        # Use session for better redirect handling
        session = requests.Session()
        response = session.get(url, stream=True, timeout=60, allow_redirects=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        last_reported = 0
        
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Report progress (cap downloaded at total_size for display)
                    if progress_callback:
                        if total_size > 0:
                            display_downloaded = min(downloaded, total_size)
                            # Only update every 1MB to reduce UI overhead
                            if downloaded - last_reported >= 1024 * 1024:
                                progress_callback(display_downloaded, total_size)
                                last_reported = downloaded
                        else:
                            # Unknown size - just show downloaded
                            if downloaded - last_reported >= 1024 * 1024:
                                progress_callback(downloaded, 0)
                                last_reported = downloaded
        
        logger.info(f"Downloaded {filename} to {folder_key}/")
        return True, f"Downloaded {filename}"
    
    except Exception as e:
        # Clean up partial download
        if os.path.exists(target_path):
            os.remove(target_path)
        return False, str(e)


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
    """Check if a node type is installed. Returns (installed, folder_name, git_url)."""
    import re
    
    # Builtin check
    if node_type in BUILTIN_NODES:
        return True, "Builtin", None
    
    # Direct DB match
    if node_type in NODE_DB:
        folder_name, git_url = NODE_DB[node_type]
        node_path = os.path.join(CUSTOM_NODES_PATH, folder_name)
        return os.path.exists(node_path), folder_name, git_url
    
    # Fallback DB match (for nodes not in ComfyUI-Manager DB)
    if node_type in FALLBACK_NODE_DB:
        folder_name, git_url = FALLBACK_NODE_DB[node_type]
        node_path = os.path.join(CUSTOM_NODES_PATH, folder_name)
        return os.path.exists(node_path), folder_name, git_url
    
    # Normalized match (remove parentheses suffix like "(rgthree)")
    normalized = re.sub(r'\s*\([^)]+\)\s*$', '', node_type).strip()
    if normalized != node_type and normalized in NODE_DB:
        folder_name, git_url = NODE_DB[normalized]
        node_path = os.path.join(CUSTOM_NODES_PATH, folder_name)
        return os.path.exists(node_path), folder_name, git_url
    
    # Package hint from parentheses - search NODE_DB for matching folder
    match = re.search(r'\(([^)]+)\)', node_type)
    if match:
        package_hint = match.group(1).lower().replace('-', '').replace('_', '')
        
        # Search NODE_DB for folder containing this hint
        for k, v in NODE_DB.items():
            folder_name, git_url = v
            folder_lower = folder_name.lower().replace('-', '').replace('_', '')
            if package_hint in folder_lower:
                node_path = os.path.join(CUSTOM_NODES_PATH, folder_name)
                return os.path.exists(node_path), folder_name, git_url
        
        # Also check installed folders
        if os.path.exists(CUSTOM_NODES_PATH):
            for folder in os.listdir(CUSTOM_NODES_PATH):
                if package_hint in folder.lower().replace('-', '').replace('_', ''):
                    return True, folder, None
    
    # Heuristic folder scan (for already installed nodes not in DB)
    if os.path.exists(CUSTOM_NODES_PATH):
        search = node_type.lower().replace('_', '').replace(' ', '')
        for folder in os.listdir(CUSTOM_NODES_PATH):
            folder_lower = folder.lower().replace('-', '').replace('_', '')
            if search in folder_lower or folder_lower in search:
                return True, folder, None
    
    return False, "Unknown", None


def check_model_installed(model_name):
    """Check if a model is installed. Returns (installed, folder/status, download_url)."""
    # Get basename (without subfolder like Kijai_WAN/)
    basename = os.path.basename(model_name.replace("\\", "/"))
    
    if os.path.exists(MODELS_PATH):
        for root, dirs, files in os.walk(MODELS_PATH):
            # Check exact basename match
            if basename in files:
                return True, "found", None
            
            # Check if model_name (with subfolder) exists as exact path
            if model_name in files:
                return True, "found", None
            
            # Check partial match (for files that might have slightly different names)
            for f in files:
                if f.lower() == basename.lower():
                    return True, "found", None
    
    # Check if we have download URL in MODEL_DB
    in_db, info = check_model_in_db(model_name)
    if in_db:
        return False, info.get("folder", "unknown"), info.get("url")
    
    return False, "unknown", None


def check_workflow_dependencies(filename):
    """Check all dependencies for a workflow."""
    node_types, model_names = parse_workflow(filename)
    
    nodes_status = []
    seen_folders = set()
    
    for nt in node_types:
        installed, folder, url = check_node_installed(nt)
        
        if folder not in seen_folders or folder in ("Unknown", "Builtin"):
            nodes_status.append({
                "type": nt,
                "folder": folder,
                "installed": installed,
                "url": url
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
    """Install a custom node from git URL."""
    if not git_url:
        return False, "No URL provided"
    
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
                capture_output=True, encoding='utf-8', errors='replace'
            )
        
        # Run install.py if exists
        install_py = os.path.join(target_path, "install.py")
        if os.path.exists(install_py):
            subprocess.run(
                [PYTHON_PATH, install_py],
                capture_output=True, encoding='utf-8', errors='replace'
            )
        
        return True, f"Installed {repo_name}"
    except Exception as e:
        return False, str(e)


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
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5
            )
            status["python_version"] = result.stdout.strip().replace("Python ", "")
        except:
            pass
    
    try:
        result = subprocess.run(
            [PYTHON_PATH, "-c", "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10
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
                resp = requests.get(f["download_url"], timeout=30)
                resp.raise_for_status()
                with open(local_path, 'wb') as file:
                    file.write(resp.content)
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


# Initialize NODE_DB and MODEL_DB on module load
fetch_node_db()
load_model_db()
