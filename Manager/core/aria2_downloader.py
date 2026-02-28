"""
DSUComfyCG Manager - aria2 Download Engine
Uses aria2c for high-speed downloads with multi-connection and resume support.
Falls back to built-in downloader if aria2c is not available.
"""

import os
import re
import subprocess
import shutil
import logging
import threading

logger = logging.getLogger("Aria2Downloader")

# ─── aria2c Detection ─────────────────────────────────────────────────────────

_aria2c_path = None
_aria2c_checked = False

def find_aria2c():
    """Find aria2c executable. Returns path or None."""
    global _aria2c_path, _aria2c_checked
    
    if _aria2c_checked:
        return _aria2c_path
    
    _aria2c_checked = True
    
    # 1. Check bundled aria2c in Manager dir
    manager_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled = os.path.join(manager_dir, "tools", "aria2c.exe")
    if os.path.exists(bundled):
        _aria2c_path = bundled
        logger.info(f"[aria2] Found bundled aria2c: {bundled}")
        return _aria2c_path
    
    # 2. Check system PATH
    system_path = shutil.which("aria2c")
    if system_path:
        _aria2c_path = system_path
        logger.info(f"[aria2] Found system aria2c: {system_path}")
        return _aria2c_path
    
    logger.info("[aria2] aria2c not found, will use built-in downloader")
    return None


def is_aria2_available():
    """Check if aria2c is available."""
    return find_aria2c() is not None


# ─── aria2c Download ──────────────────────────────────────────────────────────

def download_with_aria2(url, target_path, progress_callback=None, 
                        max_connections=16, split=16, headers=None):
    """Download a file using aria2c.
    
    Args:
        url: Download URL
        target_path: Full path where the file should be saved
        progress_callback: Optional callback(downloaded_bytes, total_bytes)
        max_connections: Max connections per server (default 16)
        split: Number of splits for parallel download (default 16)
        headers: Optional dict of HTTP headers
    
    Returns:
        (success: bool, message: str)
    """
    aria2c = find_aria2c()
    if not aria2c:
        return False, "aria2c not available"
    
    target_dir = os.path.dirname(target_path)
    target_name = os.path.basename(target_path)
    
    # Ensure target directory exists
    os.makedirs(target_dir, exist_ok=True)
    
    # Build aria2c command
    cmd = [
        aria2c,
        url,
        f"--dir={target_dir}",
        f"--out={target_name}",
        f"--max-connection-per-server={max_connections}",
        f"--split={split}",
        "--min-split-size=5M",
        "--continue=true",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        "--console-log-level=warn",
        "--summary-interval=1",
        "--download-result=hide",
        "--file-allocation=none",
    ]
    
    # Add custom headers
    if headers:
        for key, value in headers.items():
            cmd.append(f"--header={key}: {value}")
    
    logger.info(f"[aria2] Starting download: {target_name}")
    logger.debug(f"[aria2] Command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        
        total_size = 0
        downloaded = 0
        
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            # Parse aria2c progress output
            # Format: [#xxxxxx 123MiB/456MiB(27%) CN:16 DL:50MiB ETA:6s]
            progress_match = re.search(
                r'\[#\w+\s+([\d.]+)([KMG]i?B)/([\d.]+)([KMG]i?B)\((\d+)%\)',
                line
            )
            if progress_match and progress_callback:
                dl_val = float(progress_match.group(1))
                dl_unit = progress_match.group(2)
                total_val = float(progress_match.group(3))
                total_unit = progress_match.group(4)
                
                downloaded = _parse_size(dl_val, dl_unit)
                total_size = _parse_size(total_val, total_unit)
                
                if total_size > 0:
                    progress_callback(downloaded, total_size)
        
        process.wait()
        
        if process.returncode == 0:
            # Verify file exists
            if os.path.exists(target_path):
                file_size = os.path.getsize(target_path)
                logger.info(f"[aria2] ✓ Download complete: {target_name} ({file_size // (1024*1024)}MB)")
                
                # Final progress callback
                if progress_callback:
                    progress_callback(file_size, file_size)
                
                return True, f"Downloaded {target_name} via aria2 ({file_size // (1024*1024)}MB)"
            else:
                return False, f"aria2 reported success but file not found: {target_path}"
        else:
            return False, f"aria2c exited with code {process.returncode}"
    
    except FileNotFoundError:
        return False, "aria2c executable not found"
    except Exception as e:
        logger.error(f"[aria2] Download failed: {e}")
        return False, f"aria2 error: {str(e)}"


def _parse_size(value, unit):
    """Convert aria2c size notation to bytes."""
    unit = unit.upper().replace("I", "i")
    multipliers = {
        "B": 1,
        "KB": 1024, "KiB": 1024,
        "MB": 1024**2, "MiB": 1024**2,
        "GB": 1024**3, "GiB": 1024**3,
    }
    return int(value * multipliers.get(unit, 1))


# ─── Smart Download (with aria2 fallback) ────────────────────────────────────

def smart_download(url, target_path, progress_callback=None, headers=None):
    """Download a file using aria2c if available, otherwise return False for fallback.
    
    This is the main entry point. If aria2c succeeds, returns (True, message).
    If aria2c is not available or fails, returns (False, reason) so the caller
    can fall back to the built-in downloader.
    
    Args:
        url: Download URL
        target_path: Full path for the downloaded file
        progress_callback: Optional callback(downloaded_bytes, total_bytes)
        headers: Optional dict of HTTP headers
    
    Returns:
        (success: bool, message: str)
    """
    if not is_aria2_available():
        return False, "aria2c not installed"
    
    success, message = download_with_aria2(
        url, target_path, progress_callback, headers=headers
    )
    
    if not success:
        logger.warning(f"[aria2] Failed, caller should use fallback: {message}")
        # Clean up partial file if aria2 failed
        partial = target_path + ".aria2"
        if os.path.exists(partial):
            try:
                os.remove(partial)
            except Exception:
                pass
    
    return success, message
