"""
DSUComfyCG Manager - Fuzzy Matcher Module
Provides fuzzy matching, model aliases, and alternative format detection for model names.
"""

import os
import re
import logging
from difflib import SequenceMatcher

logger = logging.getLogger("FuzzyMatcher")

# ─── Confidence Levels ───────────────────────────────────────────────────────
CONFIDENCE_EXACT = 1.0
CONFIDENCE_ALIAS = 0.90
CONFIDENCE_FUZZY_HIGH = 0.85
CONFIDENCE_FUZZY_MED = 0.70

# ─── Model Format Aliases ────────────────────────────────────────────────────
# Maps precision/format suffixes to their alternative forms.
# Used to find alternative versions of a model when the exact one isn't available.
FORMAT_ALIASES = {
    # Precision aliases
    "fp16": ["bf16", "fp32", "fp8_e4m3fn", "fp8_e4m3fn_scaled", "fp8"],
    "bf16": ["fp16", "fp32", "fp8_e4m3fn", "fp8_e4m3fn_scaled", "fp8"],
    "fp32": ["bf16", "fp16"],
    "fp8": ["fp8_e4m3fn", "fp8_e4m3fn_scaled", "fp16", "bf16"],
    "fp8_e4m3fn": ["fp8_e4m3fn_scaled", "fp8", "fp16", "bf16"],
    "fp8_e4m3fn_scaled": ["fp8_e4m3fn", "fp8", "fp16", "bf16"],
    # Quantization aliases
    "Q4_K_M": ["Q4_K_S", "Q5_K_M", "Q5_K_S", "Q8_0", "Q6_K"],
    "Q4_K_S": ["Q4_K_M", "Q5_K_S", "Q5_K_M", "Q8_0"],
    "Q5_K_M": ["Q5_K_S", "Q4_K_M", "Q6_K", "Q8_0"],
    "Q5_K_S": ["Q5_K_M", "Q4_K_M", "Q4_K_S", "Q8_0"],
    "Q6_K": ["Q5_K_M", "Q8_0", "Q4_K_M"],
    "Q8_0": ["Q6_K", "Q5_K_M", "Q4_K_M"],
}

# File extension alternatives
EXTENSION_ALIASES = {
    ".safetensors": [".ckpt", ".pt", ".pth", ".bin"],
    ".ckpt": [".safetensors", ".pt", ".pth"],
    ".pt": [".pth", ".safetensors", ".ckpt"],
    ".pth": [".pt", ".safetensors", ".ckpt"],
    ".gguf": [".safetensors"],  # GGUF is a different format entirely
    ".bin": [".safetensors", ".pt"],
}

# Regex to extract precision/quant suffix from a model filename
# Matches patterns like: _fp16, _bf16, _fp8_e4m3fn, _Q4_K_M, -fp16, etc.
_PRECISION_PATTERN = re.compile(
    r'[_-](fp16|bf16|fp32|fp8_e4m3fn_scaled|fp8_e4m3fn|fp8|'
    r'Q4_K_M|Q4_K_S|Q5_K_M|Q5_K_S|Q6_K|Q8_0)'
    r'(?=[\._-]|$)',
    re.IGNORECASE
)

# ─── Fuzzy Matching ──────────────────────────────────────────────────────────

def fuzzy_match_model(name, candidates, threshold=0.70):
    """Find models matching by fuzzy string similarity.
    
    Args:
        name: Model filename to search for
        candidates: List of candidate model names (strings) 
        threshold: Minimum similarity ratio (0.0 - 1.0)
    
    Returns:
        List of (candidate_name, similarity_ratio) tuples, sorted by similarity desc.
    """
    if not name or not candidates:
        return []
    
    basename = os.path.basename(name.replace("\\", "/")).lower()
    # Strip extension for comparison
    name_stem = os.path.splitext(basename)[0]
    
    matches = []
    for candidate in candidates:
        cand_basename = os.path.basename(str(candidate).replace("\\", "/")).lower()
        cand_stem = os.path.splitext(cand_basename)[0]
        
        # Calculate similarity
        ratio = SequenceMatcher(None, name_stem, cand_stem).ratio()
        
        if ratio >= threshold:
            matches.append((candidate, round(ratio, 3)))
    
    # Sort by similarity descending
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches


def fuzzy_match_in_db(model_name, model_db, ext_model_db=None, threshold=0.70):
    """Search for fuzzy matches across local and external model databases.
    
    Args:
        model_name: Model filename to search for
        model_db: Dict of {name: info} from models_db.json
        ext_model_db: List of dicts from model-list.json (ComfyUI-Manager format)
        threshold: Minimum similarity ratio
    
    Returns:
        (found, info_dict, confidence, matched_name) or (False, None, 0, None)
    """
    basename = os.path.basename(model_name.replace("\\", "/"))
    
    # Search local MODEL_DB
    if model_db:
        candidates = list(model_db.keys())
        matches = fuzzy_match_model(basename, candidates, threshold)
        if matches:
            best_name, confidence = matches[0]
            logger.info(f"[Fuzzy] Match in MODEL_DB: {basename} → {best_name} ({confidence*100:.0f}%)")
            return True, model_db[best_name], confidence, best_name
    
    # Search external MODEL_DB
    if ext_model_db:
        ext_names = []
        ext_map = {}
        for model in ext_model_db:
            fname = model.get("filename", "")
            mname = model.get("name", "")
            if fname:
                ext_names.append(fname)
                ext_map[fname] = model
            if mname and mname != fname:
                ext_names.append(mname)
                ext_map[mname] = model
        
        matches = fuzzy_match_model(basename, ext_names, threshold)
        if matches:
            best_name, confidence = matches[0]
            model_info = ext_map[best_name]
            logger.info(f"[Fuzzy] Match in EXT_DB: {basename} → {best_name} ({confidence*100:.0f}%)")
            return True, {
                "url": model_info.get("url"),
                "filename": model_info.get("filename"),
                "folder": model_info.get("type", "checkpoints"),
                "description": f"{model_info.get('name', best_name)} (Fuzzy)"
            }, confidence, best_name
    
    return False, None, 0.0, None


# ─── Model Aliases / Alternative Format Detection ────────────────────────────

def get_alternative_names(model_name):
    """Generate alternative model names by varying precision, quantization, and extension.
    
    Args:
        model_name: Original model filename
    
    Returns:
        List of alternative filenames to search for.
    """
    basename = os.path.basename(model_name.replace("\\", "/"))
    stem, ext = os.path.splitext(basename)
    alternatives = []
    
    # 1. Precision/quantization alternatives
    match = _PRECISION_PATTERN.search(stem)
    if match:
        original_precision = match.group(1)
        prefix = stem[:match.start()]
        suffix = stem[match.end():]
        sep = stem[match.start():match.start()+1]  # _ or -
        
        alias_list = FORMAT_ALIASES.get(original_precision, [])
        # Also try case-insensitive lookup
        if not alias_list:
            for key, val in FORMAT_ALIASES.items():
                if key.lower() == original_precision.lower():
                    alias_list = val
                    break
        
        for alt_precision in alias_list:
            alt_name = f"{prefix}{sep}{alt_precision}{suffix}{ext}"
            if alt_name != basename:
                alternatives.append(alt_name)
    
    # 2. Extension alternatives
    ext_lower = ext.lower()
    if ext_lower in EXTENSION_ALIASES:
        for alt_ext in EXTENSION_ALIASES[ext_lower]:
            alt_name = f"{stem}{alt_ext}"
            if alt_name != basename and alt_name not in alternatives:
                alternatives.append(alt_name)
    
    # 3. GGUF ↔ safetensors special case
    # If looking for a .gguf, also try the safetensors version without quant suffix
    if ext_lower == ".gguf" and match:
        clean_stem = _PRECISION_PATTERN.sub("", stem)
        alternatives.append(f"{clean_stem}.safetensors")
    elif ext_lower == ".safetensors":
        # Try common GGUF quant versions
        for quant in ["Q4_K_M", "Q5_K_M", "Q8_0"]:
            alternatives.append(f"{stem}_{quant}.gguf")
            alternatives.append(f"{stem}-{quant}.gguf")
    
    return alternatives


def find_model_with_alternatives(model_name, model_db, ext_model_db=None):
    """Search for a model using alternative names (aliases/format variants).
    
    Args:
        model_name: Original model filename
        model_db: Dict from models_db.json
        ext_model_db: List from model-list.json
    
    Returns:
        (found, info_dict, confidence, method_str, matched_name) or (False, None, 0, None, None)
    """
    alternatives = get_alternative_names(model_name)
    
    if not alternatives:
        return False, None, 0.0, None, None
    
    logger.info(f"[Alias] Trying {len(alternatives)} alternatives for: {model_name}")
    
    for alt_name in alternatives:
        # Check local MODEL_DB
        if alt_name in model_db:
            logger.info(f"[Alias] ✓ Found alias in MODEL_DB: {alt_name}")
            return True, model_db[alt_name], CONFIDENCE_ALIAS, "alias", alt_name
        
        # Check basename match in MODEL_DB
        alt_basename = os.path.basename(alt_name)
        for key, info in model_db.items():
            if os.path.basename(key) == alt_basename:
                logger.info(f"[Alias] ✓ Found alias (basename) in MODEL_DB: {key}")
                return True, info, CONFIDENCE_ALIAS, "alias", key
        
        # Check external MODEL_DB
        if ext_model_db:
            for model in ext_model_db:
                if model.get("filename") == alt_basename or model.get("name") == alt_basename:
                    logger.info(f"[Alias] ✓ Found alias in EXT_DB: {alt_basename}")
                    return True, {
                        "url": model.get("url"),
                        "filename": model.get("filename"),
                        "folder": model.get("type", "checkpoints"),
                        "description": f"{model.get('name', alt_basename)} (Alt format)"
                    }, CONFIDENCE_ALIAS, "alias", alt_basename
    
    return False, None, 0.0, None, None


# ─── Combined Search (Integration helper) ────────────────────────────────────

def enhanced_model_search(model_name, model_db, ext_model_db=None, fuzzy_threshold=0.70):
    """Perform enhanced model search with aliases and fuzzy matching.
    
    This combines alias search + fuzzy search. Called by checker.py when
    exact matches fail.
    
    Args:
        model_name: Model filename to search for
        model_db: Dict from models_db.json
        ext_model_db: List from model-list.json
        fuzzy_threshold: Minimum fuzzy match ratio
    
    Returns:
        (found, info_dict, confidence, method) or (False, None, 0.0, None)
        method is one of: "alias", "fuzzy" or None
    """
    # Step 1: Try aliases first (higher confidence)
    found, info, confidence, method, matched = find_model_with_alternatives(
        model_name, model_db, ext_model_db
    )
    if found:
        info["_matched_name"] = matched
        info["_confidence"] = confidence
        info["_method"] = method
        return True, info, confidence, method
    
    # Step 2: Fall back to fuzzy matching
    found, info, confidence, matched = fuzzy_match_in_db(
        model_name, model_db, ext_model_db, fuzzy_threshold
    )
    if found:
        info["_matched_name"] = matched
        info["_confidence"] = confidence
        info["_method"] = "fuzzy"
        return True, info, confidence, "fuzzy"
    
    return False, None, 0.0, None
