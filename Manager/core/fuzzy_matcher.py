"""
DSUComfyCG Manager - Fuzzy Matcher Module
Provides fuzzy matching, model aliases, and alternative format detection for model names.
"""

import os
import re
import json
import logging
from difflib import SequenceMatcher

logger = logging.getLogger("FuzzyMatcher")

# ─── External Alias Dictionary (Manager/data/model-aliases.json) ─────────────
# Ported from _ref_downloader/metadata/model-aliases.json. Structure:
#   {
#     "aliases":  { canonical_filename: [alias1, alias2, ...], ... },
#     "patterns": [ {"pattern": "regex", "base": "$1.safetensors"}, ... ]
#   }
# Loaded lazily on first call.
_MODEL_ALIASES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "model-aliases.json",
)
MODEL_ALIASES = None  # Populated on first _load_model_aliases() call


def _load_model_aliases():
    """Lazy-load the model-aliases.json dictionary. Returns {} on failure."""
    global MODEL_ALIASES
    if MODEL_ALIASES is not None:
        return MODEL_ALIASES
    try:
        if os.path.exists(_MODEL_ALIASES_FILE):
            with open(_MODEL_ALIASES_FILE, "r", encoding="utf-8") as f:
                MODEL_ALIASES = json.load(f)
                logger.debug(
                    f"[FuzzyMatcher] Loaded {len(MODEL_ALIASES.get('aliases', {}))} alias groups, "
                    f"{len(MODEL_ALIASES.get('patterns', []))} patterns from {_MODEL_ALIASES_FILE}"
                )
        else:
            logger.warning(f"[FuzzyMatcher] {_MODEL_ALIASES_FILE} not found")
            MODEL_ALIASES = {"aliases": {}, "patterns": []}
    except Exception as e:
        logger.error(f"[FuzzyMatcher] Error loading model-aliases.json: {e}")
        MODEL_ALIASES = {"aliases": {}, "patterns": []}
    return MODEL_ALIASES


def resolve_canonical_name(filename):
    """Resolve filename → canonical name via aliases dict + pattern regex.
    Returns the original filename if no alias match found.
    """
    data = _load_model_aliases()
    filename_lower = filename.lower()

    # Direct alias lookup
    for canonical, alias_list in data.get("aliases", {}).items():
        if filename_lower in [a.lower() for a in alias_list]:
            return canonical
        if filename_lower == canonical.lower():
            return canonical

    # Pattern-based normalization (fp16, fp8, q8_0, pruned, ...)
    for pattern_def in data.get("patterns", []):
        try:
            match = re.match(pattern_def["pattern"], filename, re.IGNORECASE)
            if match:
                base = pattern_def["base"].replace("$1", match.group(1))
                return base
        except re.error:
            continue

    return filename


def get_aliases(model_name):
    """Return a deduplicated list of candidate filenames for fuzzy matching.

    Combines three sources:
      1. JSON aliases dict (canonical ↔ variant filenames)
      2. JSON regex patterns (stripping fp16/fp8/q8_0/pruned/... → base)
      3. Precision/quant/extension alternatives via get_alternative_names()

    Args:
        model_name: Model filename (basename or path)

    Returns:
        List of unique candidate names (excluding the input itself).
    """
    basename = os.path.basename(str(model_name).replace("\\", "/"))
    basename_lower = basename.lower()
    candidates = []
    seen = {basename_lower}

    def _add(name):
        if not name:
            return
        nl = name.lower()
        if nl not in seen:
            seen.add(nl)
            candidates.append(name)

    data = _load_model_aliases()
    aliases_map = data.get("aliases", {})

    # 1. If basename is a canonical key → add all its variants
    for canonical, alias_list in aliases_map.items():
        if canonical.lower() == basename_lower:
            for a in alias_list:
                _add(a)
        elif basename_lower in [a.lower() for a in alias_list]:
            # basename is a variant → add the canonical + siblings
            _add(canonical)
            for a in alias_list:
                _add(a)

    # 2. Pattern normalization → add the base form
    for pattern_def in data.get("patterns", []):
        try:
            match = re.match(pattern_def["pattern"], basename, re.IGNORECASE)
            if match:
                base = pattern_def["base"].replace("$1", match.group(1))
                _add(base)
        except re.error:
            continue

    # 3. Precision/quant/extension alternatives (existing logic)
    for alt in get_alternative_names(basename):
        _add(alt)

    return candidates

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

# Equivalent model directories — models in these directories are interchangeable
EQUIVALENT_DIRECTORIES = {
    "text_encoders": ["clip", "text_encoders"],
    "clip": ["clip", "text_encoders"],
    "unet": ["unet", "diffusion_models"],
    "diffusion_models": ["unet", "diffusion_models"],
    "controlnet": ["controlnet", "control_net"],
    "control_net": ["controlnet", "control_net"],
}

def get_equivalent_dirs(directory):
    """Return list of equivalent directory names for cross-directory model search."""
    return EQUIVALENT_DIRECTORIES.get(directory, [directory])

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

    # Pre-fuzzy: try alias variants (canonical / regex-normalized names).
    # These are higher-confidence than blind fuzzy matching.
    alias_candidates = get_aliases(basename)
    if alias_candidates:
        basename_lower = basename.lower()
        # Local MODEL_DB alias hits
        if model_db:
            db_lower_map = {k.lower(): k for k in model_db.keys()}
            db_basename_map = {os.path.basename(k).lower(): k for k in model_db.keys()}
            for alt in alias_candidates:
                alt_lower = alt.lower()
                if alt_lower in db_lower_map:
                    matched_key = db_lower_map[alt_lower]
                    logger.info(f"[Alias] MODEL_DB hit: {basename} → {matched_key}")
                    return True, model_db[matched_key], CONFIDENCE_ALIAS, matched_key
                alt_base_lower = os.path.basename(alt).lower()
                if alt_base_lower != basename_lower and alt_base_lower in db_basename_map:
                    matched_key = db_basename_map[alt_base_lower]
                    logger.info(f"[Alias] MODEL_DB basename hit: {basename} → {matched_key}")
                    return True, model_db[matched_key], CONFIDENCE_ALIAS, matched_key
        # External MODEL_DB alias hits
        if ext_model_db:
            for alt in alias_candidates:
                alt_base_lower = os.path.basename(alt).lower()
                for model in ext_model_db:
                    fname = (model.get("filename") or "").lower()
                    mname = (model.get("name") or "").lower()
                    if alt_base_lower and alt_base_lower in (fname, mname):
                        matched = model.get("filename") or model.get("name")
                        logger.info(f"[Alias] EXT_DB hit: {basename} → {matched}")
                        return True, {
                            "url": model.get("url"),
                            "filename": model.get("filename"),
                            "folder": model.get("type", "checkpoints"),
                            "description": f"{model.get('name', matched)} (Alias)",
                        }, CONFIDENCE_ALIAS, matched

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
