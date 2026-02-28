"""
DSUComfyCG Manager - External Search Engines Module
Provides CivitAI API search and Tavily AI-powered search for model sources.
"""

import os
import json
import logging

logger = logging.getLogger("SearchEngines")

try:
    import requests
except ImportError:
    requests = None

# ─── Settings ─────────────────────────────────────────────────────────────────

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "settings.json"
)

def load_settings():
    """Load settings from settings.json."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(settings):
    """Save settings to settings.json."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return False

def get_api_key(key_name):
    """Get an API key from settings or environment variable."""
    # Environment variable takes precedence
    env_map = {
        "hf_token": "HF_TOKEN",
        "civitai_api_key": "CIVITAI_API_KEY",
        "tavily_api_key": "TAVILY_API_KEY",
    }
    env_name = env_map.get(key_name)
    if env_name:
        val = os.environ.get(env_name)
        if val:
            return val
    
    # Fall back to settings file
    settings = load_settings()
    return settings.get("api_keys", {}).get(key_name, "")

def set_api_key(key_name, value):
    """Save an API key to settings."""
    settings = load_settings()
    if "api_keys" not in settings:
        settings["api_keys"] = {}
    settings["api_keys"][key_name] = value
    return save_settings(settings)


# ─── CivitAI Search ──────────────────────────────────────────────────────────

CIVITAI_API_BASE = "https://civitai.com/api/v1"

def search_civitai(model_name, api_key=None):
    """Search CivitAI for a model by name.
    
    Args:
        model_name: Model filename to search for
        api_key: Optional CivitAI API key (for better rate limits)
    
    Returns:
        (url, info_dict) or (None, None)
    """
    if not requests:
        logger.debug("requests not available for CivitAI search")
        return None, None
    
    basename = os.path.basename(model_name.replace("\\", "/"))
    # Strip extension and precision suffixes for better search
    search_term = os.path.splitext(basename)[0]
    # Clean up common suffixes
    import re
    search_term = re.sub(
        r'[_-]?(fp16|bf16|fp32|fp8_e4m3fn_scaled|fp8_e4m3fn|fp8|'
        r'Q4_K_M|Q4_K_S|Q5_K_M|Q5_K_S|Q6_K|Q8_0)$',
        '', search_term, flags=re.IGNORECASE
    )
    search_term = search_term.replace("_", " ").replace("-", " ")[:50]
    
    if not search_term.strip():
        return None, None
    
    logger.info(f"[CivitAI] Searching for: {search_term}")
    
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        response = requests.get(
            f"{CIVITAI_API_BASE}/models",
            params={
                "query": search_term,
                "limit": 10,
                "sort": "Highest Rated",
            },
            headers=headers,
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        if not items:
            logger.info(f"[CivitAI] No results for: {search_term}")
            return None, None
        
        # Search through results for matching file
        for item in items:
            model_versions = item.get("modelVersions", [])
            for version in model_versions:
                files = version.get("files", [])
                for file_info in files:
                    file_name = file_info.get("name", "")
                    # Exact filename match
                    if file_name.lower() == basename.lower():
                        download_url = file_info.get("downloadUrl", "")
                        if download_url:
                            # Add API key to download URL if available
                            if api_key and "?" in download_url:
                                download_url += f"&token={api_key}"
                            elif api_key:
                                download_url += f"?token={api_key}"
                            
                            logger.info(f"[CivitAI] ✓ Exact match: {file_name}")
                            return download_url, {
                                "url": download_url,
                                "filename": file_name,
                                "description": f"{item.get('name', '')} (CivitAI)",
                                "source": "civitai",
                                "civitai_model_id": item.get("id"),
                                "civitai_version_id": version.get("id"),
                            }
        
        # If no exact match, return first model's primary file as a suggestion
        first_item = items[0]
        versions = first_item.get("modelVersions", [])
        if versions:
            files = versions[0].get("files", [])
            if files:
                primary = files[0]
                download_url = primary.get("downloadUrl", "")
                if api_key and download_url:
                    if "?" in download_url:
                        download_url += f"&token={api_key}"
                    else:
                        download_url += f"?token={api_key}"
                
                logger.info(f"[CivitAI] ~ Partial match: {primary.get('name', '?')}")
                return download_url, {
                    "url": download_url,
                    "filename": primary.get("name", ""),
                    "description": f"{first_item.get('name', '')} (CivitAI, partial match)",
                    "source": "civitai",
                    "civitai_model_id": first_item.get("id"),
                    "_confidence": 0.65,  # lower confidence for partial
                }
    
    except requests.exceptions.Timeout:
        logger.warning("[CivitAI] Search timed out")
    except requests.exceptions.HTTPError as e:
        if e.response and e.response.status_code == 429:
            logger.warning("[CivitAI] Rate limited. Consider setting CIVITAI_API_KEY.")
        else:
            logger.warning(f"[CivitAI] HTTP error: {e}")
    except Exception as e:
        logger.warning(f"[CivitAI] Search failed: {e}")
    
    return None, None


# ─── Tavily AI Search ─────────────────────────────────────────────────────────

def search_tavily(model_name, api_key=None):
    """Search the web using Tavily AI for model download sources.
    
    Tavily is an AI-powered search engine that provides relevant, accurate results.
    API key is required. Free tier: 1000 requests/month.
    
    Args:
        model_name: Model filename to search for
        api_key: Tavily API key (required)
    
    Returns:
        (url, info_dict) or (None, None)
    """
    if not api_key:
        api_key = get_api_key("tavily_api_key")
    
    if not api_key:
        logger.debug("[Tavily] No API key configured, skipping")
        return None, None
    
    basename = os.path.basename(model_name.replace("\\", "/"))
    
    logger.info(f"[Tavily] AI search for: {basename}")
    
    # Try using the tavily-python package first
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        
        response = client.search(
            query=f"download {basename} model HuggingFace OR CivitAI",
            search_depth="advanced",
            include_domains=["huggingface.co", "civitai.com", "github.com"],
            max_results=5,
        )
        
        results = response.get("results", [])
        return _parse_tavily_results(results, basename)
    
    except ImportError:
        logger.debug("[Tavily] tavily-python not installed, using REST API")
    except Exception as e:
        logger.warning(f"[Tavily] SDK search failed: {e}")
    
    # Fallback: Direct REST API call
    if not requests:
        return None, None
    
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": f"download {basename} model HuggingFace OR CivitAI",
                "search_depth": "advanced",
                "include_domains": ["huggingface.co", "civitai.com", "github.com"],
                "max_results": 5,
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        return _parse_tavily_results(results, basename)
    
    except Exception as e:
        logger.warning(f"[Tavily] REST search failed: {e}")
    
    return None, None


def _parse_tavily_results(results, basename):
    """Parse Tavily search results to extract download URLs."""
    import re
    
    for result in results:
        url = result.get("url", "")
        title = result.get("title", "")
        content = result.get("content", "")
        
        # Check for HuggingFace direct links
        hf_match = re.search(
            r'https?://huggingface\.co/([^/]+/[^/]+)(?:/(?:blob|resolve)/[^/]+/(.+?))?',
            url
        )
        if hf_match:
            repo_id = hf_match.group(1)
            filename = hf_match.group(2) if hf_match.group(2) else None
            
            logger.info(f"[Tavily] ✓ Found HuggingFace link: {repo_id}")
            return url, {
                "repo_id": repo_id,
                "filename": filename,
                "description": f"{title} (Tavily → HuggingFace)",
                "source": "tavily",
            }
        
        # Check for CivitAI links
        civit_match = re.search(
            r'https?://civitai\.com/models/(\d+)',
            url
        )
        if civit_match:
            logger.info(f"[Tavily] ✓ Found CivitAI link: {url}")
            return url, {
                "url": url,
                "description": f"{title} (Tavily → CivitAI)",
                "source": "tavily",
                "civitai_model_id": civit_match.group(1),
            }
    
    logger.info(f"[Tavily] No useful results for: {basename}")
    return None, None

def advanced_search_tavily(model_name, api_key=None):
    """Perform a Tavily search but return all raw results for UI selection.
    
    Returns:
        List of dicts: [{"title": ..., "url": ..., "content": ...}, ...]
    """
    if not api_key:
        api_key = get_api_key("tavily_api_key")
    
    if not api_key:
        return []
        
    basename = os.path.basename(model_name.replace("\\", "/"))
    
    # Try using the tavily-python package first
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        
        response = client.search(
            query=f"download {basename} model dataset HuggingFace OR CivitAI",
            search_depth="advanced",
            include_domains=["huggingface.co", "civitai.com", "github.com"],
            max_results=10,
        )
        return response.get("results", [])
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[Tavily] SDK search failed: {e}")
        
    # Fallback: Direct REST API call
    if not requests:
        return []
        
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": f"download {basename} model dataset HuggingFace OR CivitAI",
                "search_depth": "advanced",
                "include_domains": ["huggingface.co", "civitai.com", "github.com"],
                "max_results": 10,
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        logger.warning(f"[Tavily] REST search failed: {e}")
    
    return []
