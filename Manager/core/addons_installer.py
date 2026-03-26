import os
import subprocess
import logging
import platform

logger = logging.getLogger(__name__)

# Hardcoded Wheel mapping based on the legacy .bat files for Python 3.12 / Torch 2.8+ / CUDA 12.8
ADDON_WHEELS = {
    "triton": "triton-windows==3.4.0.post20",
    "sageattention": "https://github.com/woct0rdho/SageAttention/releases/download/v2.2.0-windows.post3/sageattention-2.2.0+cu128torch2.8.0.post3-cp39-abi3-win_amd64.whl",
    "sageattention3": "https://github.com/mengqin/SageAttention/releases/download/20251229/sageattn3-1.0.0+cu128torch280-cp312-cp312-win_amd64.whl",
    "nunchaku": "https://github.com/nunchaku-ai/nunchaku/releases/download/v1.2.1/nunchaku-1.2.1+cu12.8torch2.8-cp312-cp312-win_amd64.whl",
    "flashattention": "https://github.com/kingbri1/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu128torch2.8.0cxx11abiFALSE-cp312-cp312-win_amd64.whl"
}

def install_addon(addon_id, python_executable, comfy_path, callback=None):
    """
    Installs specific advanced backend tools into a specific environment.
    addon_id: 'sageattention', 'nunchaku', 'flashattention'
    """
    if not os.path.exists(python_executable):
        return False, "Python executable not found for this environment."

    def _run_pip(args, desc):
        if callback:
            callback(f"Installing {desc}...")
        cmd = [python_executable, "-I", "-m", "pip", "install", "--no-cache-dir", "--no-warn-script-location", "--use-pep517"] + args
        try:
            logger.info(f"Running PIP: {' '.join(cmd)}")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                if callback:
                    callback(line.strip()[:100] + "..." if len(line) > 100 else line.strip())
            proc.wait()
            if proc.returncode != 0:
                logger.error(f"Failed to install {desc}.")
                return False
            return True
        except Exception as e:
            logger.error(f"PIP Exception ({desc}): {e}")
            return False

    def _ensure_triton():
        if callback:
            callback("Checking Triton Prerequisite...")
        return _run_pip([ADDON_WHEELS["triton"]], "Triton-Windows (3.4.0)")

    if addon_id == "sageattention":
        if not _ensure_triton():
            return False, "Failed to install Triton prerequisite."
        
        # Install Sage2
        if not _run_pip([ADDON_WHEELS["sageattention"]], "SageAttention 2.2.0"):
            return False, "Failed to install SageAttention 2.2.0"
            
        # Install Sage3
        if not _run_pip([ADDON_WHEELS["sageattention3"]], "SageAttention 3.0"):
            return False, "Failed to install SageAttention 3.0"
            
        return True, "SageAttention v2 & v3 Installed Successfully."

    elif addon_id == "nunchaku":
        # Nunchaku needs the custom node cloned as well
        custom_nodes_path = os.path.join(comfy_path, "custom_nodes", "ComfyUI-nunchaku")
        if not os.path.exists(custom_nodes_path):
            if callback:
                callback("Cloning ComfyUI-nunchaku repository...")
            try:
                subprocess.run(["git", "clone", "https://github.com/nunchaku-ai/ComfyUI-nunchaku", custom_nodes_path], check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                return False, f"Failed to git clone ComfyUI-nunchaku: {e.stderr.decode('utf-8')}"
                
        # Install exact Numpy version required by Nunchaku
        _run_pip(["numpy==1.26.4", "--force-reinstall"], "Nunchaku Numpy Requirement")
                
        # Install Nunchaku Whl
        if not _run_pip([ADDON_WHEELS["nunchaku"]], "Nunchaku Engine"):
            return False, "Failed to install Nunchaku wheel."

        return True, "Nunchaku core and node installed successfully."

    elif addon_id == "flashattention":
        if not _ensure_triton():
            return False, "Failed to install Triton prerequisite."
            
        if not _run_pip([ADDON_WHEELS["flashattention"]], "FlashAttention v2.8.3"):
            return False, "Failed to install FlashAttention."
            
        return True, "FlashAttention Installed Successfully."

    elif addon_id == "onnxruntime-gpu":
        if not _run_pip(["onnxruntime-gpu"], "ONNX Runtime GPU"):
            return False, "Failed to install ONNX Runtime GPU."
        return True, "ONNX Runtime GPU Installed Successfully."

    return False, "Unknown addon requested."
