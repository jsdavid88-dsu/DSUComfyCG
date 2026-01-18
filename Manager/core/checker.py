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

# Embedded model URLs found in workflows (name -> {url, directory, source})
EMBEDDED_MODEL_URLS = {}

# NOT_FOUND cache - models that couldn't be found (avoid re-searching)
NOT_FOUND_CACHE = set()
NOT_FOUND_CACHE_FILE = os.path.join(CACHE_DIR, "not_found_cache.json")

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


def check_model_in_db(model_name):
    """Check if a model is in our MODEL_DB or External DB. Returns (in_db, info_dict).
    
    Priority:
    0. EMBEDDED_MODEL_URLS (from workflow properties.models) - Most accurate
    1. Local MODEL_DB (models_db.json) - High priority (we control this)
    2. External MODEL_DB (model-list.json) - Secondary (thousands of models)
    3. HuggingFace Search - Last resort
    """
    logger.info(f"[Model Check] Looking for: {model_name}")
    basename = os.path.basename(model_name.replace("\\", "/"))
    
    # 0. Check EMBEDDED_MODEL_URLS (from workflow)
    if basename in EMBEDDED_MODEL_URLS:
        info = EMBEDDED_MODEL_URLS[basename]
        logger.info(f"[Model Check] ✓ Found in EMBEDDED_MODEL_URLS: {info['url'][:50]}...")
        return True, {
            "url": info["url"],
            "folder": info["directory"],
            "description": f"Embedded in workflow",
            "source": "embedded"
        }
    
    # 1. Local MODEL_DB Check
    if model_name in MODEL_DB:
        logger.info(f"[Model Check] ✓ Direct match in MODEL_DB")
        return True, MODEL_DB[model_name]
    
    if basename in MODEL_DB:
        logger.info(f"[Model Check] ✓ Basename match in MODEL_DB: {basename}")
        return True, MODEL_DB[basename]
    
    for key, info in MODEL_DB.items():
        if basename == os.path.basename(key):
            logger.info(f"[Model Check] ✓ Key basename match in MODEL_DB: {key}")
            return True, info
            
    # 2. External MODEL_DB Check (ComfyUI-Manager list)
    # The external list is a list of dicts, not a dict of keys. We need to search it.
    # Structure: {"name": "foo.ckpt", "url": "...", "filename": "..."}
    if EXT_MODEL_DB:
        for model in EXT_MODEL_DB:
            # Check filename match
            if model.get("filename") == basename:
                logger.info(f"[Model Check] ✓ Found in EXT_MODEL_DB: {model['name']}")
                return True, {
                    "url": model.get("url"),
                    "filename": model.get("filename"),
                    "folder": model.get("type", "checkpoints"), # Map types if needed
                    "description": f"{model.get('name')} (External)"
                }
            # Check name match
            if model.get("name") == basename:
                logger.info(f"[Model Check] ✓ Found in EXT_MODEL_DB (by name): {model['name']}")
                return True, {
                    "url": model.get("url"),
                    "filename": model.get("filename"),
                    "folder": model.get("type", "checkpoints"),
                    "description": f"{model.get('name')} (External)"
                }

    logger.info(f"[Model Check] Not in DBs, searching HuggingFace...")
    
    # 3. Fallback: Search HuggingFace
    repo_id, filename = search_huggingface(model_name)
    if repo_id and filename:
        logger.info(f"[Model Check] ✓ Found on HuggingFace: {repo_id}/{filename}")
        return True, {
            "repo_id": repo_id,
            "filename": filename,
            "folder": guess_model_folder(basename),
            "description": f"Auto-found on HuggingFace"
        }
    
    logger.info(f"[Model Check] ✗ Not found anywhere: {model_name}")
    return False, None



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


def check_model_in_db(model_name):
    """Check if a model is in our MODEL_DB. Returns (in_db, info_dict).
    
    Falls back to HuggingFace search if not found in local DB.
    """
    logger.info(f"[Model Check] Looking for: {model_name}")
    
    # Direct match
    if model_name in MODEL_DB:
        logger.info(f"[Model Check] ✓ Direct match in MODEL_DB")
        return True, MODEL_DB[model_name]
    
    # Try without path prefix (e.g., "Kijai_WAN/file.safetensors" -> "file.safetensors")
    basename = os.path.basename(model_name.replace("\\", "/"))
    if basename in MODEL_DB:
        logger.info(f"[Model Check] ✓ Basename match: {basename}")
        return True, MODEL_DB[basename]
    
    # Try with path variations
    for key, info in MODEL_DB.items():
        if basename == os.path.basename(key):
            logger.info(f"[Model Check] ✓ Key basename match: {key}")
            return True, info
    
    logger.info(f"[Model Check] Not in MODEL_DB, searching HuggingFace...")
    
    # Fallback: Search HuggingFace
    repo_id, filename = search_huggingface(model_name)
    if repo_id and filename:
        logger.info(f"[Model Check] ✓ Found on HuggingFace: {repo_id}/{filename}")
        # Create a dynamic entry
        return True, {
            "repo_id": repo_id,
            "filename": filename,
            "folder": guess_model_folder(basename),
            "description": f"Auto-found on HuggingFace"
        }
    
    logger.info(f"[Model Check] ✗ Not found anywhere: {model_name}")
    return False, None


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



def download_model(model_name, progress_callback=None):
    """Download a model from HuggingFace using huggingface_hub library.
    
    Falls back to direct URL download if huggingface_hub is not available.
    Returns (success, message).
    """
    # Check if in our DB
    in_db, info = check_model_in_db(model_name)
    if not in_db:
        return False, f"Model '{model_name}' not found in MODEL_DB"
    
    folder_key = info.get("folder", "checkpoints")
    folder_path = FOLDER_MAPPINGS.get(folder_key, f"ComfyUI/models/{folder_key}")
    target_dir = os.path.join(BASE_DIR, folder_path)
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
    
    # Try huggingface_hub first (preferred method)
    repo_id = info.get("repo_id")
    hf_filename = info.get("filename") or info.get("hf_filename")
    
    if repo_id and hf_filename:
        try:
            from huggingface_hub import hf_hub_download
            logger.info(f"Downloading {filename} via huggingface_hub...")
            logger.info(f"Repo: {repo_id}, File: {hf_filename}")
            
            # Download to target directory
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=hf_filename,
                local_dir=target_dir,
                local_dir_use_symlinks=False
            )
            
            # Move to correct location if needed (hf_hub might create subdirs)
            actual_file = os.path.join(target_dir, filename)
            if local_path != actual_file and os.path.exists(local_path):
                import shutil
                shutil.move(local_path, actual_file)
            
            if os.path.exists(target_path):
                actual_size = os.path.getsize(target_path)
                logger.info(f"Downloaded {filename} ({actual_size // (1024*1024)}MB)")
                return True, f"Downloaded {filename}"
            else:
                return False, "Download completed but file not found"
                
        except ImportError:
            logger.warning("huggingface_hub not installed, trying direct URL...")
        except Exception as e:
            logger.warning(f"huggingface_hub failed: {e}, trying direct URL...")
    
    # Fallback to direct URL download
    url = info.get("url")
    if not url:
        return False, "No download URL available"
    
    if not requests:
        return False, "requests module not available"
    
    try:
        logger.info(f"Downloading {filename}...")
        logger.info(f"URL: {url}")
        logger.info(f"Target: {target_path}")
        
        session = requests.Session()
        response = session.get(url, stream=True, timeout=60, allow_redirects=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        logger.info(f"Content-Length: {total_size} bytes ({total_size // (1024*1024)}MB)")
        
        if total_size == 0:
            return False, "Server returned empty content-length"
        
        downloaded = 0
        last_reported = 0
        
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if progress_callback and total_size > 0:
                        display_downloaded = min(downloaded, total_size)
                        if downloaded - last_reported >= 1024 * 1024:
                            progress_callback(display_downloaded, total_size)
                            last_reported = downloaded
        
        actual_size = os.path.getsize(target_path)
        if actual_size < MIN_FILE_SIZE:
            os.remove(target_path)
            return False, f"Downloaded file too small ({actual_size} bytes)"
        
        logger.info(f"Downloaded {filename} ({actual_size // (1024*1024)}MB)")
        return True, f"Downloaded {filename}"
    
    except requests.exceptions.RequestException as e:
        if os.path.exists(target_path):
            os.remove(target_path)
        return False, f"Network error: {str(e)}"
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
    
    # Check if we have info in MODEL_DB (or from HuggingFace search)
    in_db, info = check_model_in_db(model_name)
    if in_db:
        # Return folder and info dict itself for download
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
        "installed": os.path.exists(COMFY_PATH),
        "current_commit": None,
        "latest_commit": None,
        "update_available": False,
        "commits_behind": 0,
        "error": None
    }
    
    if not result["installed"]:
        result["error"] = "ComfyUI not installed"
        return result
    
    git_dir = os.path.join(COMFY_PATH, ".git")
    if not os.path.exists(git_dir):
        result["error"] = "Not a git repository"
        return result
    
    try:
        # Fetch latest (don't pull, just fetch)
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True, cwd=COMFY_PATH, timeout=30
        )
        
        # Get current commit
        current = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=COMFY_PATH
        )
        result["current_commit"] = current.stdout.strip()
        
        # Get remote latest commit
        remote = subprocess.run(
            ["git", "rev-parse", "--short", "origin/master"],
            capture_output=True, text=True, cwd=COMFY_PATH
        )
        if remote.returncode != 0:
            # Try origin/main instead
            remote = subprocess.run(
                ["git", "rev-parse", "--short", "origin/main"],
                capture_output=True, text=True, cwd=COMFY_PATH
            )
        result["latest_commit"] = remote.stdout.strip()
        
        # Count commits behind
        behind = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/master"],
            capture_output=True, text=True, cwd=COMFY_PATH
        )
        if behind.returncode != 0:
            behind = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..origin/main"],
                capture_output=True, text=True, cwd=COMFY_PATH
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
    
    if not os.path.exists(CUSTOM_NODES_PATH):
        return results
    
    for node_name in os.listdir(CUSTOM_NODES_PATH):
        node_path = os.path.join(CUSTOM_NODES_PATH, node_name)
        
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
    if not os.path.exists(COMFY_PATH):
        return False, "ComfyUI not installed"
    
    try:
        logger.info("Updating ComfyUI...")
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True, text=True, cwd=COMFY_PATH, timeout=120
        )
        
        if result.returncode == 0:
            return True, "ComfyUI updated successfully"
        else:
            return False, result.stderr or result.stdout
    except Exception as e:
        return False, str(e)


def update_custom_node(node_name):
    """Update a single custom node. Returns (success, message)."""
    node_path = os.path.join(CUSTOM_NODES_PATH, node_name)
    
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


# Initialize NODE_DB and MODEL_DB on module load
fetch_node_db()
load_model_db()
fetch_ext_model_db()

