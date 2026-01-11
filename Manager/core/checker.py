"""
DSUComfyCG Manager - Core Checker Module
Provides dependency checking and system status functionality.
"""

import os
import sys
import json
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='[DSUComfyCG] %(message)s')
logger = logging.getLogger("Checker")

# Get base path (DSUComfyCG folder)
MANAGER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(MANAGER_DIR)
WORKFLOWS_DIR = os.path.join(BASE_DIR, "workflows")
COMFY_PATH = os.path.join(BASE_DIR, "ComfyUI")
CUSTOM_NODES_PATH = os.path.join(COMFY_PATH, "custom_nodes")
MODELS_PATH = os.path.join(COMFY_PATH, "models")
PYTHON_PATH = os.path.join(BASE_DIR, "python_embeded", "python.exe")

# Node Database (expanded)
NODE_DB = {
    # Built-in nodes
    "CheckpointLoaderSimple": ("Builtin", None),
    "KSampler": ("Builtin", None),
    "KSamplerAdvanced": ("Builtin", None),
    "EmptyLatentImage": ("Builtin", None),
    "CLIPTextEncode": ("Builtin", None),
    "VAEDecode": ("Builtin", None),
    "VAEEncode": ("Builtin", None),
    "SaveImage": ("Builtin", None),
    "LoadImage": ("Builtin", None),
    "PreviewImage": ("Builtin", None),
    "LoraLoader": ("Builtin", None),
    "CLIPSetLastLayer": ("Builtin", None),
    "ConditioningCombine": ("Builtin", None),
    "ConditioningSetArea": ("Builtin", None),
    
    # ComfyUI-Manager
    "ManagerMenu": ("ComfyUI-Manager", "https://github.com/Comfy-Org/ComfyUI-Manager.git"),
    
    # Video Helper Suite
    "VHS_VideoCombine": ("ComfyUI-VideoHelperSuite", "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"),
    "VHS_LoadVideo": ("ComfyUI-VideoHelperSuite", "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"),
    "VHS_LoadVideoPath": ("ComfyUI-VideoHelperSuite", "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"),
    "VHS_LoadImages": ("ComfyUI-VideoHelperSuite", "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"),
    
    # IPAdapter
    "IPAdapterApply": ("ComfyUI_IPAdapter_plus", "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"),
    "IPAdapterModelLoader": ("ComfyUI_IPAdapter_plus", "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"),
    "IPAdapterEncoder": ("ComfyUI_IPAdapter_plus", "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"),
    "IPAdapterUnifiedLoader": ("ComfyUI_IPAdapter_plus", "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"),
    
    # ControlNet Aux
    "ControlNetApply": ("comfyui_controlnet_aux", "https://github.com/Fannovel16/comfyui_controlnet_aux.git"),
    "CannyEdgePreprocessor": ("comfyui_controlnet_aux", "https://github.com/Fannovel16/comfyui_controlnet_aux.git"),
    "DepthAnythingPreprocessor": ("comfyui_controlnet_aux", "https://github.com/Fannovel16/comfyui_controlnet_aux.git"),
    "DWPreprocessor": ("comfyui_controlnet_aux", "https://github.com/Fannovel16/comfyui_controlnet_aux.git"),
    "LineArtPreprocessor": ("comfyui_controlnet_aux", "https://github.com/Fannovel16/comfyui_controlnet_aux.git"),
    
    # LTX Video
    "LTXVLoader": ("ComfyUI-LTXVideo", "https://github.com/Lightricks/ComfyUI-LTXVideo.git"),
    "LTXVSampler": ("ComfyUI-LTXVideo", "https://github.com/Lightricks/ComfyUI-LTXVideo.git"),
    "LTXVConditioning": ("ComfyUI-LTXVideo", "https://github.com/Lightricks/ComfyUI-LTXVideo.git"),
    
    # WanVideo
    "WanVideoSampler": ("ComfyUI-WanVideoWrapper", "https://github.com/kijai/ComfyUI-WanVideoWrapper.git"),
    "WanVideoModelLoader": ("ComfyUI-WanVideoWrapper", "https://github.com/kijai/ComfyUI-WanVideoWrapper.git"),
    "WanVideoTextEncode": ("ComfyUI-WanVideoWrapper", "https://github.com/kijai/ComfyUI-WanVideoWrapper.git"),
    "DownloadAndLoadWanVideoModel": ("ComfyUI-WanVideoWrapper", "https://github.com/kijai/ComfyUI-WanVideoWrapper.git"),
    
    # KJNodes
    "GetImageSizeAndCount": ("ComfyUI-KJNodes", "https://github.com/kijai/ComfyUI-KJNodes.git"),
    "ImageBatchToImageList": ("ComfyUI-KJNodes", "https://github.com/kijai/ComfyUI-KJNodes.git"),
    "EmptyLatentImagePresets": ("ComfyUI-KJNodes", "https://github.com/kijai/ComfyUI-KJNodes.git"),
    
    # Florence2
    "Florence2Run": ("ComfyUI-Florence2", "https://github.com/kijai/ComfyUI-Florence2.git"),
    "DownloadAndLoadFlorence2Model": ("ComfyUI-Florence2", "https://github.com/kijai/ComfyUI-Florence2.git"),
    
    # WAS Node Suite
    "WAS_Image_Resize": ("was-node-suite-comfyui", "https://github.com/WASasquatch/was-node-suite-comfyui.git"),
    "WAS_Mask_Dilate_Region": ("was-node-suite-comfyui", "https://github.com/WASasquatch/was-node-suite-comfyui.git"),
    
    # Impact Pack
    "SAMLoader": ("ComfyUI-Impact-Pack", "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"),
    "SAMDetectorCombined": ("ComfyUI-Impact-Pack", "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"),
    "DetailerForEach": ("ComfyUI-Impact-Pack", "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"),
    "FaceDetailer": ("ComfyUI-Impact-Pack", "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"),
    
    # GGUF
    "UnetLoaderGGUF": ("ComfyUI-GGUF", "https://github.com/city96/ComfyUI-GGUF.git"),
    "CLIPLoaderGGUF": ("ComfyUI-GGUF", "https://github.com/city96/ComfyUI-GGUF.git"),
    
    # Essentials
    "ImageResize+": ("ComfyUI_essentials", "https://github.com/cubiq/ComfyUI_essentials.git"),
    "GetImageSize+": ("ComfyUI_essentials", "https://github.com/cubiq/ComfyUI_essentials.git"),
}

# Model Database  
MODEL_DB = {
    "ltx_video_v2.safetensors": ("checkpoints", "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.safetensors"),
    "sd_xl_base_1.0.safetensors": ("checkpoints", "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"),
    "v1-5-pruned-emaonly.ckpt": ("checkpoints", "https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.ckpt"),
}


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
                if "type" in node:
                    node_types.add(node["type"])
                if "widgets_values" in node and node["widgets_values"]:
                    for val in node["widgets_values"]:
                        if isinstance(val, str):
                            lower = val.lower()
                            if lower.endswith(('.safetensors', '.ckpt', '.pt', '.pth')):
                                model_names.add(val)
    except Exception as e:
        logger.error(f"Failed to parse {filename}: {e}")
    
    return list(node_types), list(model_names)


def check_node_installed(node_type):
    """Check if a node type is installed. Returns (installed, folder_name, git_url)."""
    if node_type in NODE_DB:
        folder_name, git_url = NODE_DB[node_type]
        if folder_name == "Builtin":
            return True, "Builtin", None
        node_path = os.path.join(CUSTOM_NODES_PATH, folder_name)
        return os.path.exists(node_path), folder_name, git_url
    return False, "Unknown", None


def check_model_installed(model_name):
    """Check if a model is installed. Returns (installed, subfolder, url)."""
    # Check in MODEL_DB
    if model_name in MODEL_DB:
        subfolder, url = MODEL_DB[model_name]
        # Search in models folder
        if os.path.exists(MODELS_PATH):
            for root, dirs, files in os.walk(MODELS_PATH):
                if model_name in files:
                    return True, subfolder, url
        return False, subfolder, url
    
    # Unknown model - still search for it
    if os.path.exists(MODELS_PATH):
        for root, dirs, files in os.walk(MODELS_PATH):
            if model_name in files:
                return True, "found", None
    return False, "unknown", None


def check_workflow_dependencies(filename):
    """Check all dependencies for a workflow. Returns dict with nodes and models status."""
    node_types, model_names = parse_workflow(filename)
    
    nodes_status = []
    for nt in node_types:
        installed, folder, url = check_node_installed(nt)
        nodes_status.append({
            "type": nt,
            "folder": folder,
            "installed": installed,
            "url": url
        })
    
    models_status = []
    for mn in model_names:
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
        "gpu_name": None
    }
    
    # Get Python version
    if status["python_installed"]:
        try:
            result = subprocess.run(
                [PYTHON_PATH, "--version"],
                capture_output=True, text=True, timeout=5
            )
            status["python_version"] = result.stdout.strip().replace("Python ", "")
        except:
            pass
    
    # Check CUDA (via torch)
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
    
    repo_name = git_url.split("/")[-1].replace(".git", "")
    target_path = os.path.join(CUSTOM_NODES_PATH, repo_name)
    
    if os.path.exists(target_path):
        return True, f"{repo_name} already exists"
    
    try:
        subprocess.check_call(["git", "clone", "--depth", "1", git_url, target_path])
        
        # Install requirements
        req_file = os.path.join(target_path, "requirements.txt")
        if os.path.exists(req_file):
            subprocess.check_call([PYTHON_PATH, "-m", "pip", "install", "-r", req_file, "--quiet"])
        
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
