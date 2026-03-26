"""
DSUComfyCG Manager - Core Checker Module (v6 - Enhanced Search + aria2 + Model Browser)
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

import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    import yaml
except ImportError:
    yaml = None

# New enhanced modules
from core.fuzzy_matcher import enhanced_model_search, CONFIDENCE_EXACT
from core.search_engines import search_civitai, search_tavily, get_api_key, load_settings
from core.aria2_downloader import smart_download, is_aria2_available
from importlib.metadata import version, PackageNotFoundError
try:
    from packaging import specifiers, version as packaging_version
except ImportError:
    specifiers = None
    packaging_version = None

logging.basicConfig(level=logging.INFO, format='[DSUComfyCG] %(message)s')
logger = logging.getLogger("Checker")

# Get base path
MANAGER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(MANAGER_DIR)
WORKFLOWS_DIR = os.path.join(BASE_DIR, "workflows")
# --- Multi-Instance Environment Management ---
ENVS_FILE = os.path.join(MANAGER_DIR, "data", "envs.json")
ACTIVE_ENV_ID = "env_default"
ENVIRONMENTS = {}

def load_envs():
    global ENVIRONMENTS, ACTIVE_ENV_ID
    if os.path.exists(ENVS_FILE):
        try:
            with open(ENVS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                ENVIRONMENTS = data.get("environments", {})
                ACTIVE_ENV_ID = data.get("active_env_id", "env_default")
        except Exception as e:
            logger.error(f"Failed to load envs.json: {e}")
            
    if "env_default" not in ENVIRONMENTS:
        ENVIRONMENTS["env_default"] = {
            "name": "Default ComfyUI",
            "type": "production",
            "path": os.path.join(BASE_DIR, "ComfyUI").replace("\\", "/"),
            "memo": "Default built-in installation"
        }

def save_envs():
    try:
        data = {
            "active_env_id": ACTIVE_ENV_ID,
            "environments": ENVIRONMENTS
        }
        os.makedirs(os.path.dirname(ENVS_FILE), exist_ok=True)
        with open(ENVS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save envs.json: {e}")

def get_active_env():
    return ENVIRONMENTS.get(ACTIVE_ENV_ID, ENVIRONMENTS.get("env_default", {}))

def set_active_env(env_id):
    global ACTIVE_ENV_ID
    if env_id in ENVIRONMENTS:
        ACTIVE_ENV_ID = env_id
        save_envs()
        read_extra_model_paths() # Reload extra tracking for new environment
        return True
    return False

def add_environment(env_id, name, type_desc, path, memo=""):
    if env_id in ENVIRONMENTS:
        return False, "Environment ID already exists"
    
    ENVIRONMENTS[env_id] = {
        "name": name,
        "type": type_desc,
        "path": path.replace("\\", "/"),
        "memo": memo
    }
    save_envs()
    return True, "Environment added"

def remove_environment(env_id):
    if env_id == "env_default":
        return False, "Cannot delete default environment"
        
    if env_id in ENVIRONMENTS:
        del ENVIRONMENTS[env_id]
        if ACTIVE_ENV_ID == env_id:
            set_active_env("env_default")
        else:
            save_envs()
        return True, "Environment removed"
    return False, "Environment not found"

def update_environment_memo(env_id, memo):
    if env_id in ENVIRONMENTS:
        ENVIRONMENTS[env_id]["memo"] = memo
        save_envs()
        return True
    return False

def update_environment_field(env_id, field, value):
    if env_id in ENVIRONMENTS:
        ENVIRONMENTS[env_id][field] = value
        save_envs()
        return True
    return False

def duplicate_environment(env_id):
    if env_id not in ENVIRONMENTS:
        return False, "Source environment not found"
        
    src = ENVIRONMENTS[env_id]
    import random, string, re
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', src.get('name', 'env'))
    new_id = f"env_{safe_name.lower()}_copy_{''.join(random.choices(string.ascii_lowercase + string.digits, k=4))}"
    new_name = src.get('name', 'Env') + " (Copy)"
    new_path = src.get('path', '') + f"_copy_{random.randint(100,999)}"
    
    ENVIRONMENTS[new_id] = {
        "name": new_name,
        "type": src.get("type", "sandbox"),
        "path": new_path.replace("\\", "/"),
        "memo": src.get("memo", "") + " (Cloned)"
    }
    save_envs()
    return True, f"Environment cloned successfully!\nNew path: {new_path}\nPlease click Install on the new row to set it up."

def get_comfy_path():
    env = get_active_env()
    return env.get("path", os.path.join(BASE_DIR, "ComfyUI").replace("\\", "/"))

def get_custom_nodes_path():
    return os.path.join(get_comfy_path(), "custom_nodes").replace("\\", "/")

def get_models_path():
    return os.path.join(get_comfy_path(), "models").replace("\\", "/")

def get_python_path():
    """Find a suitable Python for running ComfyUI.
    Search order:
    1. Explicit python_path from env config
    2. python_embeded inside the ComfyUI env folder (reference project layout)
    3. venv inside the ComfyUI env folder
    4. python_embeded at project root (DSUComfyCG level)
    5. System python
    """
    env = get_active_env()
    
    # 1) Explicit path from environment config
    if "python_path" in env and env["python_path"]:
        p = env["python_path"]
        if os.path.exists(p):
            return p
    
    comfy_path = env.get("path", os.path.join(BASE_DIR, "ComfyUI"))
    comfy_parent = os.path.dirname(comfy_path)
    
    # 2) python_embeded next to ComfyUI folder (reference project layout)
    embedded_next = os.path.join(comfy_parent, "python_embeded", "python.exe")
    if os.path.exists(embedded_next):
        return embedded_next.replace("\\", "/")
    
    # 3) venv inside ComfyUI folder
    venv_py = os.path.join(comfy_path, "venv", "Scripts", "python.exe")
    if os.path.exists(venv_py):
        return venv_py.replace("\\", "/")
    
    # 4) python_embeded at project root
    root_embedded = os.path.join(BASE_DIR, "python_embeded", "python.exe")
    if os.path.exists(root_embedded):
        return root_embedded.replace("\\", "/")
    
    # 5) Fallback to system python
    import shutil
    sys_py = shutil.which("python")
    if sys_py:
        return sys_py
    
    # Absolute fallback (may not exist)
    return os.path.join(BASE_DIR, "python_embeded", "python.exe").replace("\\", "/")

load_envs()
# -----------------------------------------------
CACHE_DIR = os.path.join(MANAGER_DIR, "cache")

# Local Data Files (Version Controlled)
DATA_DIR = os.path.join(MANAGER_DIR, "data")
NODE_DB_FILE = os.path.join(DATA_DIR, "extension-node-map.json")
MODEL_LIST_FILE = os.path.join(DATA_DIR, "model-list.json")

# Fallback URLs (in case local files missing)
NODE_DB_URL = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/extension-node-map.json"
MODEL_LIST_URL = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/model-list.json"
WORKFLOWS_REPO_URL = "https://api.github.com/repos/jsdavid88-dsu/DSUComfyCG/contents/workflows"

# Ensure cache dir exists
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

# Global NODE_DB (loaded dynamically)
NODE_DB = {}
NODE_DB_CACHE_FILE = os.path.join(CACHE_DIR, "node_db_cache.json")

# Model DB (from models_db.json)
MODEL_DB = {}
MODEL_DB_FILE = os.path.join(MANAGER_DIR, "models_db.json")

# External Model DB (from ComfyUI-Manager)
EXT_MODEL_DB = {}
EXT_MODEL_DB_CACHE_FILE = os.path.join(CACHE_DIR, "model_list_cache.json")

FOLDER_MAPPINGS = {}
EXTRA_MODEL_PATHS = {}  # From extra_model_paths.yaml

# Embedded model URLs found in workflows (name -> {url, directory, source})
EMBEDDED_MODEL_URLS = {}

# NOT_FOUND cache - models that couldn't be found (avoid re-searching)
NOT_FOUND_CACHE = set()
NOT_FOUND_CACHE_FILE = os.path.join(CACHE_DIR, "not_found_cache.json")

# Model usage tracking (model_name -> [workflow_list])
MODEL_USAGE_CACHE = {}
MODEL_USAGE_CACHE_FILE = os.path.join(CACHE_DIR, "model_usage_cache.json")

# ... (Built-in nodes skipped for brevity) ...

def fetch_ext_model_db():
    """Load external model DB (Version Controlled)."""
    global EXT_MODEL_DB
    
    # 1. Try loading from local repo file (Highest priority for version control)
    if os.path.exists(MODEL_LIST_FILE):
        try:
            with open(MODEL_LIST_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                EXT_MODEL_DB = data.get("models", [])
                logger.info(f"Loaded EXT_MODEL_DB from local repo ({len(EXT_MODEL_DB)} entries)")
                return  # Success, use local file
        except Exception as e:
            logger.warning(f"Failed to load local EXT_MODEL_DB: {e}")

    # 2. Try loading from cache
    if os.path.exists(EXT_MODEL_DB_CACHE_FILE):
        try:
            with open(EXT_MODEL_DB_CACHE_FILE, 'r', encoding='utf-8') as f:
                EXT_MODEL_DB = json.load(f).get("models", [])
                logger.info(f"Loaded EXT_MODEL_DB from cache ({len(EXT_MODEL_DB)} entries)")
        except Exception as e:
            logger.warning(f"Failed to load EXT_MODEL_DB cache: {e}")
    
    # 3. Fetch from GitHub (Fallback)
    if not requests:
        return

    try:
        logger.info("Fetching external model list from URL...")
        response = requests.get(MODEL_LIST_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            EXT_MODEL_DB = data.get("models", [])
            # Save to cache
            with open(EXT_MODEL_DB_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.info(f"Updated EXT_MODEL_DB from URL ({len(EXT_MODEL_DB)} entries)")
    except Exception as e:
        logger.warning(f"Failed to fetch external model list: {e}")


# --- Models Path Manager --- #
def read_extra_model_paths():
    global EXTRA_MODEL_PATHS
    EXTRA_MODEL_PATHS = {}
    yaml_path = os.path.join(get_comfy_path(), 'extra_model_paths.yaml')
    if not os.path.isfile(yaml_path):
        return EXTRA_MODEL_PATHS
    try:
        import yaml
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if data:
            for conf_name, conf in data.items():
                if isinstance(conf, dict) and 'base_path' in conf:
                    base = conf['base_path']
                    for mtype, paths in conf.items():
                        if mtype == 'base_path': continue
                        if isinstance(paths, str): paths = [paths]
                        for p in paths:
                            full_path = p if os.path.isabs(p) else os.path.join(base, p)
                            EXTRA_MODEL_PATHS.setdefault(mtype, []).append(full_path.replace('\\\\', '/'))
    except Exception as e:
        logger.warning(f'Failed to read extra paths: {e}')
    return EXTRA_MODEL_PATHS

def write_extra_model_paths(paths_dict):
    yaml_path = os.path.join(get_comfy_path(), 'extra_model_paths.yaml')
    try:
        import yaml
        config = {'dsucomfycg_shared': {'base_path': '.'}}
        for k, v in paths_dict.items():
            config['dsucomfycg_shared'][k] = v
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False)
        read_extra_model_paths() # Reload
        return True
    except Exception as e:
        logger.error(f'Failed to write extra paths: {e}')
        return False

def check_model_in_db(model_name):
    """Check if a model is in our MODEL_DB or External DB. Returns (in_db, info_dict).
    
    Enhanced search priority chain (v6):
    0. EMBEDDED_MODEL_URLS (from workflow properties.models) - Most accurate
    1. Local MODEL_DB (models_db.json) - Exact match
    2. External MODEL_DB (model-list.json) - Exact match
    3. Fuzzy Match in DB (70% threshold) - NEW
    4. Alternative Format Names in DB - NEW
    5. HuggingFace API Search (existing)
    6. CivitAI API Search - NEW
    7. Tavily AI Search (optional) - NEW
    """
    logger.info(f"[Model Check] Looking for: {model_name}")
    basename = os.path.basename(model_name.replace("\\", "/"))
    
    # Skip NOT_FOUND cache
    if basename in NOT_FOUND_CACHE:
        logger.info(f"[Model Check] ✗ In NOT_FOUND cache: {basename}")
        return False, None
    
    # 0. Check EMBEDDED_MODEL_URLS (from workflow)
    if basename in EMBEDDED_MODEL_URLS:
        info = EMBEDDED_MODEL_URLS[basename]
        logger.info(f"[Model Check] ✓ Found in EMBEDDED_MODEL_URLS: {info['url'][:50]}...")
        return True, {
            "url": info["url"],
            "folder": info["directory"],
            "description": f"Embedded in workflow",
            "source": "embedded",
            "_confidence": CONFIDENCE_EXACT,
            "_method": "embedded"
        }
    
    # 1. Local MODEL_DB Check (exact)
    if model_name in MODEL_DB:
        logger.info(f"[Model Check] ✓ Direct match in MODEL_DB")
        info = dict(MODEL_DB[model_name])
        info["_confidence"] = CONFIDENCE_EXACT
        info["_method"] = "exact"
        return True, info
    
    if basename in MODEL_DB:
        logger.info(f"[Model Check] ✓ Basename match in MODEL_DB: {basename}")
        info = dict(MODEL_DB[basename])
        info["_confidence"] = CONFIDENCE_EXACT
        info["_method"] = "exact"
        return True, info
    
    for key, val in MODEL_DB.items():
        if basename == os.path.basename(key):
            logger.info(f"[Model Check] ✓ Key basename match in MODEL_DB: {key}")
            info = dict(val)
            info["_confidence"] = CONFIDENCE_EXACT
            info["_method"] = "exact"
            return True, info
            
    # 2. External MODEL_DB Check (exact)
    if EXT_MODEL_DB:
        for model in EXT_MODEL_DB:
            if model.get("filename") == basename:
                logger.info(f"[Model Check] ✓ Found in EXT_MODEL_DB: {model['name']}")
                return True, {
                    "url": model.get("url"),
                    "filename": model.get("filename"),
                    "folder": model.get("type", "checkpoints"),
                    "description": f"{model.get('name')} (External)",
                    "_confidence": CONFIDENCE_EXACT,
                    "_method": "exact"
                }
            if model.get("name") == basename:
                logger.info(f"[Model Check] ✓ Found in EXT_MODEL_DB (by name): {model['name']}")
                return True, {
                    "url": model.get("url"),
                    "filename": model.get("filename"),
                    "folder": model.get("type", "checkpoints"),
                    "description": f"{model.get('name')} (External)",
                    "_confidence": CONFIDENCE_EXACT,
                    "_method": "exact"
                }

    # 3-4. Fuzzy Match + Alternative Format Names (NEW)
    settings = load_settings()
    fuzzy_threshold = settings.get("search", {}).get("fuzzy_threshold", 0.70)
    
    found, info, confidence, method = enhanced_model_search(
        model_name, MODEL_DB, EXT_MODEL_DB, fuzzy_threshold
    )
    if found:
        logger.info(f"[Model Check] ✓ Enhanced match ({method}, {confidence*100:.0f}%): {model_name}")
        return True, info

    logger.info(f"[Model Check] Not in DBs, searching external APIs...")
    
    # 5. HuggingFace Search (existing)
    repo_id, filename = search_huggingface(model_name)
    if repo_id and filename:
        logger.info(f"[Model Check] ✓ Found on HuggingFace: {repo_id}/{filename}")
        return True, {
            "repo_id": repo_id,
            "filename": filename,
            "folder": guess_model_folder(basename),
            "description": f"Auto-found on HuggingFace",
            "_confidence": 0.85,
            "_method": "huggingface"
        }
    
    # 6. CivitAI Search (NEW)
    enable_civitai = settings.get("search", {}).get("enable_civitai", True)
    if enable_civitai:
        civitai_key = get_api_key("civitai_api_key")
        url, civitai_info = search_civitai(model_name, civitai_key)
        if url and civitai_info:
            civitai_info["folder"] = civitai_info.get("folder", guess_model_folder(basename))
            civitai_info.setdefault("_confidence", 0.75)
            civitai_info["_method"] = "civitai"
            return True, civitai_info
    
    # 7. Tavily AI Search (NEW, optional)
    enable_tavily = settings.get("search", {}).get("enable_tavily", True)
    if enable_tavily:
        tavily_key = get_api_key("tavily_api_key")
        if tavily_key:
            url, tavily_info = search_tavily(model_name, tavily_key)
            if url and tavily_info:
                tavily_info["folder"] = tavily_info.get("folder", guess_model_folder(basename))
                tavily_info.setdefault("_confidence", 0.60)
                tavily_info["_method"] = "tavily"
                return True, tavily_info
    
    # Cache as not found
    NOT_FOUND_CACHE.add(basename)
    _save_not_found_cache()
    
    logger.info(f"[Model Check] ✗ Not found anywhere: {model_name}")
    return False, None


def _save_not_found_cache():
    """Persist NOT_FOUND_CACHE to disk."""
    try:
        with open(NOT_FOUND_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(NOT_FOUND_CACHE), f)
    except Exception:
        pass


def _load_not_found_cache():
    """Load NOT_FOUND_CACHE from disk."""
    global NOT_FOUND_CACHE
    if os.path.exists(NOT_FOUND_CACHE_FILE):
        try:
            with open(NOT_FOUND_CACHE_FILE, 'r', encoding='utf-8') as f:
                NOT_FOUND_CACHE = set(json.load(f))
        except Exception:
            NOT_FOUND_CACHE = set()


def clear_not_found_cache():
    """Clear the NOT_FOUND cache so models are re-searched."""
    global NOT_FOUND_CACHE
    NOT_FOUND_CACHE = set()
    if os.path.exists(NOT_FOUND_CACHE_FILE):
        os.remove(NOT_FOUND_CACHE_FILE)
    logger.info("[Cache] NOT_FOUND cache cleared")



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
    # rgthree nodes
    "Any Switch (rgthree)": ("rgthree-comfy", "https://github.com/rgthree/rgthree-comfy"),
    "Fast Groups Bypasser (rgthree)": ("rgthree-comfy", "https://github.com/rgthree/rgthree-comfy"),
    "Label (rgthree)": ("rgthree-comfy", "https://github.com/rgthree/rgthree-comfy"),
    "Context (rgthree)": ("rgthree-comfy", "https://github.com/rgthree/rgthree-comfy"),
    "Seed (rgthree)": ("rgthree-comfy", "https://github.com/rgthree/rgthree-comfy"),
    "Power Lora Loader (rgthree)": ("rgthree-comfy", "https://github.com/rgthree/rgthree-comfy"),
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


def save_url_to_model_db(model_name, url, folder):
    """Save a user-provided URL to models_db.json for future use.
    
    Args:
        model_name: Filename of the model
        url: Download URL
        folder: Target folder (e.g., 'checkpoints', 'vae')
    
    Returns:
        (success, message)
    """
    global MODEL_DB
    
    try:
        # Load current data
        with open(MODEL_DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        models = data.get("models", {})
        
        # Add new entry
        basename = os.path.basename(model_name.replace("\\", "/"))
        models[basename] = {
            "url": url,
            "folder": folder,
            "description": f"User-added: {basename}",
            "source": "user_input"
        }
        
        data["models"] = models
        
        # Save back
        with open(MODEL_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        # Update in-memory DB
        MODEL_DB[basename] = models[basename]
        
        logger.info(f"[MODEL_DB] Saved user URL for: {basename}")
        return True, f"Added {basename} to models_db.json"
        
    except Exception as e:
        logger.error(f"Failed to save URL to MODEL_DB: {e}")
        return False, str(e)


def search_huggingface(model_name):
    """Search HuggingFace for a model by name. Returns (repo_id, filename) or (None, None).
    
    Strategy:
    1. Search priority repos (Comfy-Org, Kijai) for EXACT filename match
    2. Search by general model name
    3. Use EXACT match first, then partial match as last resort
    """
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        
        basename = os.path.basename(model_name.replace("\\", "/"))
        
        # Priority repos to search first (common ComfyUI model sources)
        PRIORITY_REPOS = [
            "Comfy-Org/Qwen-Image_ComfyUI",
            "Comfy-Org/Qwen-Image-Edit_ComfyUI",
            "Comfy-Org/Wan_2.1_ComfyUI",
            "Kijai/WanVideo_comfy",
            "Kijai/WanVideo_comfy_fp8_scaled",
            "Kijai/flux-fp8",
            "Kijai/QwenImage_experimental",
            "Lightricks/LTX-Video",
            "wavespeed/misc",
            "facebook/sam2.1-hiera-base-plus",
            "stabilityai/stable-diffusion-xl-base-1.0",
        ]
        
        logger.info(f"Searching HuggingFace for: {basename}")
        
        # Step 1: Search priority repos for EXACT filename match
        for repo_id in PRIORITY_REPOS:
            try:
                files = api.list_repo_files(repo_id)
                for f in files:
                    file_basename = os.path.basename(f)
                    # EXACT match only
                    if file_basename.lower() == basename.lower():
                        logger.info(f"Found EXACT match in priority repo: {repo_id}/{f}")
                        return repo_id, f
            except:
                continue
        
        # Step 2: General search by model name
        search_term = basename.replace(".safetensors", "").replace(".ckpt", "").replace(".pth", "")
        search_term = search_term.replace("_", " ").replace("-", " ")[:40]
        
        logger.info(f"Priority repos: no exact match. Searching models: {search_term}")
        
        results = list(api.list_models(search=search_term, limit=15))
        
        if not results:
            short_term = search_term.split()[0] if " " in search_term else search_term[:15]
            results = list(api.list_models(search=short_term, limit=15))
        
        # Step 2a: EXACT filename match in search results
        for model in results:
            try:
                files = api.list_repo_files(model.id)
                for f in files:
                    file_basename = os.path.basename(f)
                    if file_basename.lower() == basename.lower():
                        logger.info(f"Found EXACT match: {model.id}/{f}")
                        return model.id, f
            except:
                continue
        
        # Step 2b: Partial match (only if no exact match found)
        # Disabled - partial matching causes wrong file downloads
        # for model in results:
        #     ...
        
        logger.info(f"No match found for: {basename}")
        return None, None
        
    except ImportError:
        logger.debug("huggingface_hub not installed, cannot search")
        return None, None
    except Exception as e:
        logger.debug(f"HuggingFace search failed: {e}")
        return None, None


def guess_model_folder(filename):
    """Guess the appropriate folder for a model based on its name."""
    lower = filename.lower()
    if "vae" in lower:
        return "vae"
    elif "clip" in lower:
        return "clip"
    elif "lora" in lower:
        return "loras"
    elif "controlnet" in lower:
        return "controlnet"
    elif "unet" in lower or "diffusion" in lower:
        return "diffusion_models"
    elif "llm" in lower or "qwen" in lower or "t5" in lower:
        return "LLM"
    elif ".gguf" in lower:
        return "diffusion_models"
    else:
        return "checkpoints"



def download_chunk(url, start, end, target_path, session, file_lock):
    """Download a specific range of a file with thread-safe file writing."""
    headers = {"Range": f"bytes={start}-{end}"}
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            
            with file_lock:
                with open(target_path, "r+b") as f:
                    f.seek(start)
                    f.write(response.content)
            return True
        except Exception as e:
            logger.warning(f"Chunk download failed ({start}-{end}), attempt {attempt+1}/{max_retries}: {e}")
            if attempt == max_retries - 1:
                logger.error(f"Chunk download permanently failed ({start}-{end})")
                return False
    return False

def download_model_parallel(url, target_path, total_size, progress_callback=None, threads=4):
    """Download a model using multiple threads (Range headers) with proper locking."""
    if not requests:
        return False, "requests not available"

    # Initialize file with zeros
    try:
        with open(target_path, "wb") as f:
            f.truncate(total_size)
    except Exception as e:
        return False, f"Failed to initialize file: {e}"

    chunk_size = total_size // threads
    ranges = []
    for i in range(threads):
        start = i * chunk_size
        end = (start + chunk_size - 1) if i < threads - 1 else total_size - 1
        ranges.append((start, end))

    file_lock = threading.Lock()
    session = requests.Session()
    
    # Check if range is supported
    try:
        head = session.head(url, allow_redirects=True, timeout=10)
        if head.headers.get('Accept-Ranges') != 'bytes' and 'content-range' not in head.headers:
            logger.info("Server does not support Range headers, falling back to sequential.")
            return False, "Range not supported"
    except Exception as e:
        logger.debug(f"HEAD request failed, attempting parallel anyway: {e}")

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        for i, (start, end) in enumerate(ranges):
            futures.append(executor.submit(download_chunk, url, start, end, target_path, session, file_lock))
        
        results = [f.result() for f in futures]
    
    if all(results):
        # Notify completion
        if progress_callback:
            progress_callback(total_size, total_size)
        return True, "Download successful"
    else:
        # Clean up on failure
        try:
            if os.path.exists(target_path):
                os.remove(target_path)
        except Exception:
            pass
        return False, "One or more chunks failed to download"

def download_model(model_name, progress_callback=None):
    """Download a model from HuggingFace or direct URL.
    
    Download priority (v6):
    1. huggingface_hub (if repo_id available)
    2. aria2c (if available and URL present) - NEW
    3. Built-in parallel download (if >50MB)
    4. Sequential download (fallback)
    """
    # Check if in our DB
    in_db, info = check_model_in_db(model_name)
    if not in_db:
        return False, f"Model '{model_name}' not found in MODEL_DB"
    
    folder_key = info.get("folder", "checkpoints")
    folder_path = FOLDER_MAPPINGS.get(folder_key, f"ComfyUI/models/{folder_key}")
    # Also check EXTRA_MODEL_PATHS
    if folder_key in EXTRA_MODEL_PATHS and len(EXTRA_MODEL_PATHS[folder_key]) > 0:
        folder_path = EXTRA_MODEL_PATHS[folder_key][0]
    target_dir = os.path.join(BASE_DIR, folder_path) if not os.path.isabs(folder_path) else folder_path
    filename = os.path.basename(model_name.replace("\\", "/"))
    target_path = os.path.join(target_dir, filename)
    
    # Check if file already exists and is valid (>1MB)
    MIN_FILE_SIZE = 1024 * 1024
    if os.path.exists(target_path):
        file_size = os.path.getsize(target_path)
        if file_size > MIN_FILE_SIZE:
            return True, f"Already exists: {filename} ({file_size // (1024*1024)}MB)"
        else:
            logger.warning(f"Removing incomplete file: {filename} ({file_size} bytes)")
            os.remove(target_path)
    
    # Create directory if needed
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    
    url = info.get("url")
    # If using huggingface_hub, we use their built-in download
    repo_id = info.get("repo_id")
    hf_filename = info.get("filename") or info.get("hf_filename")
    
    if repo_id and hf_filename:
        try:
            from huggingface_hub import hf_hub_download
            logger.info(f"Downloading {filename} via huggingface_hub...")
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=hf_filename,
                local_dir=target_dir,
                local_dir_use_symlinks=False
            )
            return True, f"Downloaded {filename}"
        except Exception as e:
            logger.warning(f"huggingface_hub failed: {e}, trying direct URL...")

    if not url:
        return False, "No download URL available"
    
    # --- NEW: Try aria2c first ---
    settings = load_settings()
    use_aria2 = settings.get("download", {}).get("use_aria2", True)
    
    if use_aria2 and is_aria2_available():
        logger.info(f"Attempting aria2 download for {filename}...")
        headers = {}
        hf_token = get_api_key("hf_token")
        if hf_token and "huggingface.co" in url:
            headers["Authorization"] = f"Bearer {hf_token}"
        
        success, msg = smart_download(url, target_path, progress_callback, headers or None)
        if success:
            return True, f"Downloaded {filename} (aria2)"
        else:
            logger.warning(f"aria2 failed: {msg}. Falling back to built-in downloader.")
    
    if not requests:
        return False, "requests module not available"
    
    try:
        logger.info(f"Downloading {filename}...")
        session = requests.Session()
        response = session.get(url, stream=True, timeout=60, allow_redirects=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        # Parallel download if > 50MB
        if total_size > 50 * 1024 * 1024:
            logger.info(f"Large file ({total_size // (1024*1024)}MB), attempting parallel download...")
            success, msg = download_model_parallel(url, target_path, total_size, progress_callback)
            if success:
                return True, f"Downloaded {filename} (Parallel)"
            else:
                logger.warning(f"Parallel download failed: {msg}. Falling back to sequential.")

        # Sequential fallback
        downloaded = 0
        last_reported = 0
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        if downloaded - last_reported >= 1024 * 1024:
                            progress_callback(downloaded, total_size)
                            last_reported = downloaded
        
        return True, f"Downloaded {filename}"
    
    except Exception as e:
        if os.path.exists(target_path):
            os.remove(target_path)
        return False, f"Error: {str(e)}"


def scan_workflows():
    """Scan workflows folder and return list of JSON files."""
    workflows = []
    if os.path.exists(WORKFLOWS_DIR):
        for filename in os.listdir(WORKFLOWS_DIR):
            if filename.endswith(".json"):
                workflows.append(filename)
    return sorted(workflows)


def parse_workflow(filename):
    """Parse a workflow JSON and extract node types, model names, and embedded URLs."""
    filepath = os.path.join(WORKFLOWS_DIR, filename)
    node_types = set()
    model_names = set()
    
    # Global dict to store embedded model info (url + directory)
    global EMBEDDED_MODEL_URLS
    
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
                
                # Extract widgets_values for model names
                widgets = node.get("widgets_values") or []
                for val in widgets:
                    if isinstance(val, str):
                        lower = val.lower()
                        if lower.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.gguf')):
                            model_names.add(val)
                
                # Extract embedded model URLs from properties.models
                props = node.get("properties", {})
                if "models" in props and isinstance(props["models"], list):
                    for model_info in props["models"]:
                        if isinstance(model_info, dict):
                            name = model_info.get("name", "")
                            url = model_info.get("url", "")
                            directory = model_info.get("directory", "checkpoints")
                            if name and url:
                                EMBEDDED_MODEL_URLS[name] = {
                                    "url": url,
                                    "directory": directory,
                                    "source": "workflow"
                                }
                                logger.info(f"[Parse] Found embedded URL for: {name} → {directory}")
                                
    except Exception as e:
        logger.error(f"Failed to parse {filename}: {e}")
    
    return list(node_types), list(model_names)


def check_node_installed(node_type):
    """Check if a node type is installed. Returns (installed, folder_name, git_url)."""
    import re
    
    # Skip UUID-like nodes (subgraphs/workflow groups)
    # Pattern: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    if re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', node_type):
        return True, "Builtin", None  # Treat as built-in (skip)
    
    # Builtin check
    if node_type in BUILTIN_NODES:
        return True, "Builtin", None
    
    # Direct DB match
    if node_type in NODE_DB:
        folder_name, git_url = NODE_DB[node_type]
        node_path = os.path.join(get_custom_nodes_path(), folder_name)
        return os.path.exists(node_path), folder_name, git_url
    
    # Fallback DB match (for nodes not in ComfyUI-Manager DB)
    if node_type in FALLBACK_NODE_DB:
        folder_name, git_url = FALLBACK_NODE_DB[node_type]
        node_path = os.path.join(get_custom_nodes_path(), folder_name)
        return os.path.exists(node_path), folder_name, git_url
    
    # Normalized match (remove parentheses suffix like "(rgthree)")
    normalized = re.sub(r'\s*\([^)]+\)\s*$', '', node_type).strip()
    if normalized != node_type and normalized in NODE_DB:
        folder_name, git_url = NODE_DB[normalized]
        node_path = os.path.join(get_custom_nodes_path(), folder_name)
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
                node_path = os.path.join(get_custom_nodes_path(), folder_name)
                return os.path.exists(node_path), folder_name, git_url
        
        # Also check installed folders
        if os.path.exists(get_custom_nodes_path()):
            for folder in os.listdir(get_custom_nodes_path()):
                if package_hint in folder.lower().replace('-', '').replace('_', ''):
                    return True, folder, None
    
    # Heuristic folder scan (for already installed nodes not in DB)
    if os.path.exists(get_custom_nodes_path()):
        search = node_type.lower().replace('_', '').replace(' ', '')
        for folder in os.listdir(get_custom_nodes_path()):
            folder_lower = folder.lower().replace('-', '').replace('_', '')
            if search in folder_lower or folder_lower in search:
                return True, folder, None
    
    return False, "Unknown", None


def check_model_installed(model_name):
    """Check if a model is installed. Returns (installed, folder/status, download_url).
    
    Now also searches extra_model_paths.yaml directories.
    """
    # Get basename (without subfolder like Kijai_WAN/)
    basename = os.path.basename(model_name.replace("\\", "/"))
    
    # Search all model directories (including extra paths)
    search_paths = [get_models_path()]
    for extra_path in EXTRA_MODEL_PATHS.values():
        if os.path.isabs(extra_path):
            search_paths.append(extra_path)
        else:
            search_paths.append(os.path.join(BASE_DIR, extra_path))
    
    for search_path in search_paths:
        if not os.path.exists(search_path):
            continue
        for root, dirs, files in os.walk(search_path):
            # Check exact basename match
            if basename in files:
                return True, "found", None
            
            # Check if model_name (with subfolder) exists as exact path
            if model_name in files:
                return True, "found", None
            
            # Check case-insensitive match
            for f in files:
                if f.lower() == basename.lower():
                    return True, "found", None
    
    # Check if we have info in MODEL_DB (or from enhanced search)
    in_db, info = check_model_in_db(model_name)
    if in_db:
        return False, info.get("folder", "available"), info
    
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


def analyze_requirements(req_path):
    """Parse a requirements.txt file and return a list of (package, specifier) tuples."""
    requirements = []
    if not os.path.exists(req_path):
        return requirements
        
    try:
        with open(req_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Simple parser for "pkg>=1.0.0" or "pkg==1.0.0"
                # Exclude URL-based requirements for now
                if '://' in line:
                    continue
                
                # Split on common specifiers
                parts = re.split(r'[<>=!~]', line, 1)
                pkg_name = parts[0].strip().replace('_', '-') # Normalize package name
                spec = line[len(parts[0]):].strip()
                requirements.append((pkg_name, spec))
    except Exception as e:
        logger.error(f"Error parsing requirements: {e}")
        
    return requirements

def check_dependency_conflicts(requirements):
    """Check if any of the given requirements conflict with currently installed packages.
    
    Returns a list of conflict messages.
    """
    conflicts = []
    # Import these dynamically to avoid circular dependencies or unnecessary imports
    try:
        from packaging import version as packaging_version
        from packaging import specifiers
        from importlib.metadata import version, PackageNotFoundError
    except ImportError:
        logger.warning("packaging or importlib.metadata module not available, skipping conflict check")
        return conflicts

    for pkg, spec in requirements:
        try:
            current_ver = version(pkg)
            if not spec:
                continue
                
            spec_obj = specifiers.SpecifierSet(spec)
            ver_obj = packaging_version.parse(current_ver)
            
            if ver_obj not in spec_obj:
                conflicts.append(f"Conflict: {pkg} (Installed: {current_ver}, Required: {spec})")
        except PackageNotFoundError:
            # Package not installed, no conflict (it will be installed)
            continue
        except Exception as e:
            logger.debug(f"Error checking {pkg}: {e}")
            
    return conflicts

def snapshot_packages():
    """Take a snapshot of currently installed packages for potential rollback."""
    try:
        result = subprocess.run([get_python_path(), "-m", "pip", "freeze"], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            packages = {}
            for line in result.stdout.strip().split('\n'):
                if '==' in line:
                    name, ver = line.split('==')
                    packages[name.lower()] = ver
            return packages
    except Exception as e:
        logger.warning(f"Failed to snapshot packages: {e}")
    return {}

def restore_packages(snapshot, changed_packages):
    """Attempt to restore packages to their snapshot versions.
    
    Args:
        snapshot: Dict of {package_name: version} from before install
        changed_packages: List of package names that were changed
    """
    restored_count = 0
    for pkg in changed_packages:
        pkg_lower = pkg.lower()
        if pkg_lower in snapshot:
            old_ver = snapshot[pkg_lower]
            logger.info(f"Rolling back {pkg} to {old_ver}...")
            try:
                subprocess.run(
                    [get_python_path(), "-m", "pip", "install", f"{pkg}=={old_ver}", "--quiet"],
                    capture_output=True, timeout=120
                )
                restored_count += 1
            except Exception as e:
                logger.warning(f"Failed to restore {pkg}: {e}")
    return restored_count

def install_node(git_url, enable_rollback=True):
    """Install a custom node by cloning its git repository.
    
    Args:
        git_url: URL of the git repository
        enable_rollback: If True, attempt to restore packages on severe conflict
    """
    if not git_url:
        return False, "No URL provided", None

    folder_name = git_url.rstrip('/').split('/')[-1].replace('.git', '')
    target_path = os.path.join(get_custom_nodes_path(), folder_name)

    if os.path.exists(target_path):
        return True, f"Already installed at {folder_name}", None

    # Take snapshot before installation for potential rollback
    pre_snapshot = snapshot_packages() if enable_rollback else {}
    conflicts = []

    try:
        logger.info(f"Cloning {git_url} into {folder_name}...")
        subprocess.check_call(["git", "clone", git_url, target_path])
        
        # Dependency analysis
        req_path = os.path.join(target_path, "requirements.txt")
        if os.path.exists(req_path):
            requirements = analyze_requirements(req_path)
            conflicts = check_dependency_conflicts(requirements)
            
            if conflicts:
                msg = "\n".join(conflicts)
                logger.warning(f"Dependency conflicts detected for {folder_name}:\n{msg}")
            
            logger.info(f"Installing dependencies for {folder_name}...")
            subprocess.check_call([get_python_path(), "-m", "pip", "install", "-r", req_path])
            
            # Post-install check
            try:
                logger.info(f"Verifying environment health...")
                check_res = subprocess.run([get_python_path(), "-m", "pip", "check"], capture_output=True, text=True)
                if check_res.returncode != 0:
                    broken_msg = check_res.stdout.strip()
                    logger.warning(f"Environment has broken dependencies:\n{broken_msg}")
                    conflicts.append(f"Post-install: {broken_msg[:100]}")
                    
                    # Auto-rollback if enabled and severe breakage detected
                    if enable_rollback and pre_snapshot:
                        # Parse which packages were changed
                        post_snapshot = snapshot_packages()
                        changed = []
                        for pkg, ver in post_snapshot.items():
                            if pkg in pre_snapshot and pre_snapshot[pkg] != ver:
                                changed.append(pkg)
                        
                        if changed:
                            logger.info(f"Attempting rollback of {len(changed)} changed packages...")
                            restored = restore_packages(pre_snapshot, changed)
                            if restored > 0:
                                conflicts.append(f"Rolled back {restored} package(s) to restore stability.")
            except Exception as e:
                logger.debug(f"Post-install check failed: {e}")
        
        # Look for install.py
        install_script = os.path.join(target_path, "install.py")
        if os.path.exists(install_script):
            logger.info(f"Running install.py for {folder_name}...")
            subprocess.check_call([get_python_path(), install_script])
            
        warning_msg = "\n".join(conflicts) if conflicts else None
        return True, f"Successfully installed {folder_name}", warning_msg
    except Exception as e:
        logger.error(f"Failed to install {folder_name}: {e}")
        # Clean up failed clone
        if os.path.exists(target_path):
            try:
                import shutil
                shutil.rmtree(target_path)
            except Exception:
                pass
        return False, str(e), None


def get_system_status():
    """Get system information."""
    status = {
        "comfy_installed": os.path.exists(get_comfy_path()) and os.path.exists(os.path.join(get_comfy_path(), "main.py")),
        "python_installed": os.path.exists(get_python_path()),
        "python_version": None,
        "cuda_available": False,
        "gpu_name": None,
        "node_db_size": len(NODE_DB)
    }
    
    if status["python_installed"]:
        try:
            result = subprocess.run(
                [get_python_path(), "--version"],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5
            )
            status["python_version"] = result.stdout.strip().replace("Python ", "")
        except:
            pass
    
    try:
        result = subprocess.run(
            [get_python_path(), "-c", "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
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
    python_path = get_python_path()
    comfy_main = os.path.join(get_comfy_path(), "main.py")
    
    if not os.path.exists(python_path):
        logger.error(f"Python not found at: {python_path}")
        logger.error("ComfyUI requires a Python with PyTorch installed.")
        logger.error("Please install Python+PyTorch via the reference project or manually.")
        return False, f"Python을 찾을 수 없습니다: {python_path}\n\nComfyUI를 실행하려면 PyTorch가 설치된 Python이 필요합니다.\n\n해결 방법:\n1. Help/Settings 탭에서 Python 경로를 직접 지정하거나\n2. ComfyUI-Easy-Install로 설치한 python_embeded 폴더를 이 프로젝트 폴더에 복사하세요."
    
    if not os.path.exists(comfy_main):
        logger.error(f"ComfyUI main.py not found at: {comfy_main}")
        return False, f"ComfyUI main.py를 찾을 수 없습니다: {comfy_main}"
    
    try:
        subprocess.Popen(
            [python_path, "-I", comfy_main, "--windows-standalone-build"],
            cwd=os.path.dirname(get_comfy_path())
        )
        return True, "ComfyUI가 시작되었습니다!"
    except Exception as e:
        err_msg = f"Failed to start ComfyUI: {e}"
        logger.error(err_msg)
        return False, err_msg


def install_comfyui(progress_cb=None):
    """
    Clones the ComfyUI repository if it doesn't exist into get_comfy_path().
    Returns (success, message).
    """
    if os.path.exists(get_comfy_path()) and os.path.exists(os.path.join(get_comfy_path(), "main.py")):
        return True, "ComfyUI is already installed."
        
    try:
        if progress_cb:
            progress_cb("Cloning ComfyUI repository from github...")
            
        logger.info(f"Cloning ComfyUI into {get_comfy_path()}")
        os.makedirs(os.path.dirname(get_comfy_path()), exist_ok=True)
        process = subprocess.Popen(
            ["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", get_comfy_path()],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            if progress_cb:
                progress_cb("ComfyUI repository cloned successfully. Copying default workflows...")
                
            import shutil
            source_workflows = os.path.join(BASE_DIR, "workflows")
            target_workflows = os.path.join(get_comfy_path(), "user", "default", "workflows")
            if os.path.exists(source_workflows):
                try:
                    os.makedirs(target_workflows, exist_ok=True)
                    for item in os.listdir(source_workflows):
                        if item.endswith(".json"):
                            src = os.path.join(source_workflows, item)
                            dst = os.path.join(target_workflows, item)
                            shutil.copy2(src, dst)
                    logger.info(f"Copied built-in workflows to {target_workflows}")
                except Exception as cw_err:
                    logger.error(f"Failed to copy workflows: {cw_err}")
                
            return True, "Successfully installed ComfyUI with default workflows."
        else:
            err_msg = f"Git clone failed:\n{stderr}"
            logger.error(err_msg)
            return False, err_msg
            
    except Exception as e:
        err_msg = f"Failed to clone ComfyUI: {e}"
        logger.error(err_msg)
        return False, err_msg


# =============================================================================
# Version Control & Update System
# =============================================================================

VERSION_FILE = os.path.join(BASE_DIR, "version.txt")
VERSION_URL = "https://raw.githubusercontent.com/jsdavid88-dsu/DSUComfyCG/main/version.txt"


def get_local_version():
    """Get local app version from version.txt."""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r') as f:
                return f.read().strip()
        return "0.0.0"
    except:
        return "0.0.0"


def get_remote_version():
    """Get latest version from GitHub."""
    if not requests:
        return None, "requests module not available"
    
    try:
        response = requests.get(VERSION_URL, timeout=10)
        if response.status_code == 200:
            return response.text.strip(), None
        return None, f"HTTP {response.status_code}"
    except Exception as e:
        return None, str(e)


def compare_versions(local, remote):
    """Compare version strings. Returns: 1 if remote > local, 0 if equal, -1 if local > remote."""
    try:
        local_parts = [int(x) for x in local.split('.')]
        remote_parts = [int(x) for x in remote.split('.')]
        
        # Pad to same length
        while len(local_parts) < len(remote_parts):
            local_parts.append(0)
        while len(remote_parts) < len(local_parts):
            remote_parts.append(0)
        
        for l, r in zip(local_parts, remote_parts):
            if r > l:
                return 1
            elif l > r:
                return -1
        return 0
    except:
        return 0


def check_for_updates():
    """Check if updates are available. Returns (update_available, local_version, remote_version, error)."""
    local_version = get_local_version()
    remote_version, error = get_remote_version()
    
    if error:
        return False, local_version, None, error
    
    if compare_versions(local_version, remote_version) > 0:
        return True, local_version, remote_version, None
    
    return False, local_version, remote_version, None


def perform_update():
    """Perform git pull to update the app. Returns (success, message)."""
    try:
        # Check if git is available
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            cwd=BASE_DIR
        )
        if result.returncode != 0:
            return False, "Git is not installed"
        
        # Perform git pull
        logger.info("Updating from GitHub...")
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True,
            text=True,
            cwd=BASE_DIR
        )
        
        if result.returncode == 0:
            new_version = get_local_version()
            logger.info(f"Updated to version {new_version}")
            return True, f"Updated to v{new_version}. Please restart the app."
        else:
            error_msg = result.stderr or result.stdout
            return False, f"Git pull failed: {error_msg}"
    
    except Exception as e:
        return False, f"Update failed: {str(e)}"


# =============================================================================
# System Status Report Functions
# =============================================================================

def check_comfyui_version():
    """Check ComfyUI current vs latest version.
    
    Returns dict: {
        "installed": bool,
        "current_commit": str,
        "latest_commit": str,
        "update_available": bool,
        "commits_behind": int,
        "error": str or None
    }
    """
    result = {
        "installed": os.path.exists(get_comfy_path()),
        "current_commit": None,
        "latest_commit": None,
        "update_available": False,
        "commits_behind": 0,
        "error": None
    }
    
    if not result["installed"]:
        result["error"] = "ComfyUI not installed"
        return result
    
    git_dir = os.path.join(get_comfy_path(), ".git")
    if not os.path.exists(git_dir):
        result["error"] = "Not a git repository"
        return result
    
    try:
        # Fetch latest (don't pull, just fetch)
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True, cwd=get_comfy_path(), timeout=30
        )
        
        # Get current commit
        current = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=get_comfy_path()
        )
        result["current_commit"] = current.stdout.strip()
        
        # Get remote latest commit
        remote = subprocess.run(
            ["git", "rev-parse", "--short", "origin/master"],
            capture_output=True, text=True, cwd=get_comfy_path()
        )
        if remote.returncode != 0:
            # Try origin/main instead
            remote = subprocess.run(
                ["git", "rev-parse", "--short", "origin/main"],
                capture_output=True, text=True, cwd=get_comfy_path()
            )
        result["latest_commit"] = remote.stdout.strip()
        
        # Count commits behind
        behind = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/master"],
            capture_output=True, text=True, cwd=get_comfy_path()
        )
        if behind.returncode != 0:
            behind = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..origin/main"],
                capture_output=True, text=True, cwd=get_comfy_path()
            )
        
        try:
            result["commits_behind"] = int(behind.stdout.strip())
        except:
            result["commits_behind"] = 0
        
        result["update_available"] = result["commits_behind"] > 0
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def check_custom_nodes_updates():
    """Check all custom nodes for available updates.
    
    Returns list of dicts: [{
        "name": str,
        "path": str,
        "has_git": bool,
        "update_available": bool,
        "commits_behind": int,
        "error": str or None
    }]
    """
    results = []
    
    if not os.path.exists(get_custom_nodes_path()):
        return results
    
    for node_name in os.listdir(get_custom_nodes_path()):
        node_path = os.path.join(get_custom_nodes_path(), node_name)
        
        if not os.path.isdir(node_path):
            continue
        
        node_info = {
            "name": node_name,
            "path": node_path,
            "has_git": False,
            "update_available": False,
            "commits_behind": 0,
            "error": None
        }
        
        git_dir = os.path.join(node_path, ".git")
        if not os.path.exists(git_dir):
            results.append(node_info)
            continue
        
        node_info["has_git"] = True
        
        try:
            # Fetch (quick, just headers)
            subprocess.run(
                ["git", "fetch", "origin", "--depth=1"],
                capture_output=True, cwd=node_path, timeout=15
            )
            
            # Check if behind
            status = subprocess.run(
                ["git", "status", "-uno"],
                capture_output=True, text=True, cwd=node_path
            )
            
            if "Your branch is behind" in status.stdout:
                node_info["update_available"] = True
                # Try to extract number
                import re
                match = re.search(r"by (\d+) commit", status.stdout)
                if match:
                    node_info["commits_behind"] = int(match.group(1))
                else:
                    node_info["commits_behind"] = 1
            
        except Exception as e:
            node_info["error"] = str(e)
        
        results.append(node_info)
    
    return results


def update_comfyui():
    """Update ComfyUI via git pull. Returns (success, message)."""
    if not os.path.exists(get_comfy_path()):
        return False, "ComfyUI not installed"
    
    try:
        logger.info("Updating ComfyUI...")
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True, text=True, cwd=get_comfy_path(), timeout=120
        )
        
        if result.returncode == 0:
            return True, "ComfyUI updated successfully"
        else:
            return False, result.stderr or result.stdout
    except Exception as e:
        return False, str(e)


def update_custom_node(node_name):
    """Update a single custom node. Returns (success, message)."""
    node_path = os.path.join(get_custom_nodes_path(), node_name)
    
    if not os.path.exists(node_path):
        return False, f"Node {node_name} not found"
    
    try:
        logger.info(f"Updating {node_name}...")
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True, text=True, cwd=node_path, timeout=60
        )
        
        if result.returncode == 0:
            return True, f"{node_name} updated"
        else:
            return False, result.stderr or result.stdout
    except Exception as e:
        return False, str(e)


def update_all_custom_nodes():
    """Update all custom nodes. Returns (success_count, fail_count, results)."""
    nodes = check_custom_nodes_updates()
    updatable = [n for n in nodes if n["update_available"]]
    
    success_count = 0
    fail_count = 0
    results = []
    
    for node in updatable:
        success, msg = update_custom_node(node["name"])
        results.append({"name": node["name"], "success": success, "message": msg})
        if success:
            success_count += 1
        else:
            fail_count += 1
    
    return success_count, fail_count, results


def get_system_health_report():
    """Get comprehensive system health report.
    
    Returns dict with all system status information.
    """
    report = {
        "comfyui": check_comfyui_version(),
        "custom_nodes": {
            "total": 0,
            "updatable": 0,
            "nodes": []
        },
        "models": {
            "total": len(MODEL_DB),
            "missing": 0  # Would need to scan
        },
        "manager_version": get_local_version()
    }
    
    # Custom nodes summary
    nodes = check_custom_nodes_updates()
    report["custom_nodes"]["total"] = len(nodes)
    report["custom_nodes"]["updatable"] = len([n for n in nodes if n["update_available"]])
    report["custom_nodes"]["nodes"] = nodes
    
    return report


# =============================================================================
# extra_model_paths.yaml Support
# =============================================================================

def load_extra_model_paths():
    """Load extra model paths from ComfyUI's extra_model_paths.yaml."""
    global EXTRA_MODEL_PATHS
    
    yaml_path = os.path.join(get_comfy_path(), "extra_model_paths.yaml")
    if not os.path.exists(yaml_path):
        return
    
    if not yaml:
        logger.debug("PyYAML not installed, cannot load extra_model_paths.yaml")
        return
    
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not isinstance(data, dict):
            return
        
        for config_name, paths in data.items():
            if not isinstance(paths, dict):
                continue
            base_path = paths.get("base_path", "")
            for key, path in paths.items():
                if key in ("base_path", "is_default"):
                    continue
                if base_path and not os.path.isabs(path):
                    full_path = os.path.join(base_path, path)
                else:
                    full_path = path
                
                if key not in EXTRA_MODEL_PATHS:
                    EXTRA_MODEL_PATHS[key] = full_path
                    logger.info(f"[ExtraPath] {key} → {full_path}")
        
        logger.info(f"Loaded {len(EXTRA_MODEL_PATHS)} extra model paths")
    except Exception as e:
        logger.warning(f"Failed to load extra_model_paths.yaml: {e}")


# =============================================================================
# Batch Workflow Scanning & Model Usage Tracking
# =============================================================================

def scan_all_workflows_for_models():
    """Scan ALL workflows to build model usage history.
    
    Scans both DSUComfyCG workflows/ and ComfyUI user workflows.
    
    Returns:
        dict: {model_name: [workflow_list]}
    """
    global MODEL_USAGE_CACHE
    usage = {}  # model_name -> [workflow_files]
    
    # Directories to scan
    scan_dirs = [WORKFLOWS_DIR]
    
    # ComfyUI user data workflows
    comfy_user_dir = os.path.join(get_comfy_path(), "user", "default", "workflows")
    if os.path.exists(comfy_user_dir):
        scan_dirs.append(comfy_user_dir)
    
    # ComfyUI input directory (sometimes has workflows)
    comfy_input_dir = os.path.join(get_comfy_path(), "input")
    if os.path.exists(comfy_input_dir):
        scan_dirs.append(comfy_input_dir)
    
    total_workflows = 0
    
    for scan_dir in scan_dirs:
        if not os.path.exists(scan_dir):
            continue
        
        for root, dirs, files in os.walk(scan_dir):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                
                filepath = os.path.join(root, fname)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Quick check: does it look like a workflow?
                    if not isinstance(data, dict):
                        continue
                    if "nodes" not in data and "last_node_id" not in data:
                        continue
                    
                    total_workflows += 1
                    rel_path = os.path.relpath(filepath, BASE_DIR)
                    
                    # Extract model names from nodes
                    nodes = data.get("nodes", [])
                    if not isinstance(nodes, list):
                        nodes = list(data.values()) if isinstance(data, dict) else []
                    
                    for node in nodes:
                        if not isinstance(node, dict):
                            continue
                        widgets = node.get("widgets_values") or []
                        for val in widgets:
                            if isinstance(val, str):
                                lower = val.lower()
                                if lower.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.gguf')):
                                    basename = os.path.basename(val.replace("\\", "/"))
                                    if basename not in usage:
                                        usage[basename] = []
                                    if rel_path not in usage[basename]:
                                        usage[basename].append(rel_path)
                
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                except Exception:
                    continue
    
    logger.info(f"[Scan] Scanned {total_workflows} workflows, found {len(usage)} unique models")
    
    # Save to cache
    MODEL_USAGE_CACHE = usage
    try:
        with open(MODEL_USAGE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(usage, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to save usage cache: {e}")
    
    return usage


def load_model_usage_cache():
    """Load model usage cache from disk."""
    global MODEL_USAGE_CACHE
    if os.path.exists(MODEL_USAGE_CACHE_FILE):
        try:
            with open(MODEL_USAGE_CACHE_FILE, 'r', encoding='utf-8') as f:
                MODEL_USAGE_CACHE = json.load(f)
            return MODEL_USAGE_CACHE
        except Exception:
            pass
    return {}


def get_all_installed_models():
    """Get a list of all installed models with metadata.
    
    Returns:
        list of dicts: [{name, path, folder, size_bytes, modified_time}, ...]
    """
    models = []
    
    # Search primary models path
    search_paths = [(get_models_path(), "")]
    
    # Add extra model paths
    for key, extra_path in EXTRA_MODEL_PATHS.items():
        if os.path.isabs(extra_path):
            search_paths.append((extra_path, f"[{key}] "))
        else:
            search_paths.append((os.path.join(BASE_DIR, extra_path), f"[{key}] "))
    
    MODEL_EXTENSIONS = {'.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.gguf'}
    
    for search_path, prefix in search_paths:
        if not os.path.exists(search_path):
            continue
        
        for root, dirs, files in os.walk(search_path):
            folder = os.path.relpath(root, search_path).replace("\\", "/")
            if folder == ".":
                folder = os.path.basename(root)
            
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in MODEL_EXTENSIONS:
                    continue
                
                full_path = os.path.join(root, fname)
                try:
                    stat = os.stat(full_path)
                    models.append({
                        "name": fname,
                        "path": full_path,
                        "folder": f"{prefix}{folder}",
                        "size_bytes": stat.st_size,
                        "modified_time": stat.st_mtime,
                    })
                except Exception:
                    continue
    
    return models


def get_unused_models():
    """Get list of installed models not used in any workflow.
    
    Requires scan_all_workflows_for_models() or load_model_usage_cache() to have been called.
    
    Returns:
        list of model dicts that are installed but not referenced by any workflow.
    """
    usage = MODEL_USAGE_CACHE or load_model_usage_cache()
    all_models = get_all_installed_models()
    
    unused = []
    for model in all_models:
        if model["name"] not in usage:
            unused.append(model)
    
    return unused


# Initialize NODE_DB and MODEL_DB on module load
fetch_node_db()
load_model_db()
fetch_ext_model_db()
load_extra_model_paths()
_load_not_found_cache()
load_model_usage_cache()
