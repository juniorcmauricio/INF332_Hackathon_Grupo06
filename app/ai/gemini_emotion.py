# app/ai/gemini_emotion.py
from __future__ import annotations
from typing import List, Tuple, Dict, Optional

import httpx
import json
from ..config import settings
from .genre_mapper import TMDB_GENRES

_last_error: Optional[str] = None
MODEL_NAME: str = settings.gemini_model or "gemini-pro"  # gemini-pro is available on v1 generateContent
_last_http_status: Optional[int] = None
_last_raw_response: Optional[Dict[str, object]] = None
_last_request_payload: Optional[Dict[str, object]] = None
_available_models: List[str] = []
_used_model: Optional[str] = None

def get_last_error() -> Optional[str]:
    """Returns the last error message from the Gemini API call."""
    global _last_error
    return _last_error

def get_last_http_status() -> Optional[int]:
    """HTTP status of last Gemini API call (if performed)."""
    global _last_http_status
    return _last_http_status

def get_last_raw_response() -> Optional[Dict[str, object]]:
    """Raw JSON body (already parsed) of last Gemini response."""
    global _last_raw_response
    return _last_raw_response

def get_last_request_payload() -> Optional[Dict[str, object]]:
    """Payload sent to Gemini (for debugging prompt issues)."""
    global _last_request_payload
    return _last_request_payload

def get_model_name() -> str:
    return MODEL_NAME

def get_api_version() -> str:
    """Choose API version: 1.5/2.0 models typically live under v1beta."""
    name = (MODEL_NAME or "").lower()
    return "v1beta" if ("1.5" in name or "2.0" in name) else "v1"

def get_available_models() -> List[str]:
    return _available_models

def get_used_model() -> Optional[str]:
    return _used_model

def _reset_state() -> None:
    global _last_error, _last_http_status, _last_raw_response, _last_request_payload
    _last_error = None
    _last_http_status = None
    _last_raw_response = None
    _last_request_payload = None
    _available_models.clear()
    global _used_model
    _used_model = None

def _list_models(token: str) -> None:
    """Populate _available_models by querying model list endpoints."""
    global _available_models
    versions = ["v1", "v1beta"]
    names: List[str] = []
    with httpx.Client(timeout=settings.request_timeout_s) as client:
        for ver in versions:
            try:
                resp = client.get(f"https://generativelanguage.googleapis.com/{ver}/models", params={"key": token})
                if resp.status_code == 200:
                    body = resp.json()
                    if isinstance(body, dict) and isinstance(body.get("models"), list):
                        for m in body["models"]:  # type: ignore[index]
                            if isinstance(m, dict) and isinstance(m.get("name"), str):
                                names.append(m["name"].split('/')[-1])
            except Exception:
                continue
    _available_models = sorted(set(names))

def _choose_fallback_model() -> Optional[str]:
    """Pick the best available text-gen model from the discovered list."""
    # Preference order: newest fast text models first, then 1.5, then pro
    preference = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-pro",
    ]
    for p in preference:
        if p in _available_models and p != MODEL_NAME:
            return p
    # Heuristic: any available 'flash' model
    for m in _available_models:
        if m.startswith("gemini-") and "flash" in m and m != MODEL_NAME:
            return m
    # Next: any gemini text model
    for m in _available_models:
        if m.startswith("gemini-") and m != MODEL_NAME:
            return m
    return None

def map_via_gemini_api(mood: str, top_k: int = 2) -> List[Tuple[str, int]]:
    """
    Zero-shot classification via Google's Gemini API.
    Returns a list of (genre_name, genre_id).
    """
    # declare globals up-front for any later assignments
    global MODEL_NAME, _used_model
    labels: List[str] = list(TMDB_GENRES.keys())
    token: str | None = settings.gemini_api_key
    if not token:
        raise RuntimeError("GEMINI_API_KEY not configured (HACK_GEMINI_API_KEY)")

    # Gemini API endpoint
    # Official REST style: API key as query param keeps it explicit.
    api_version = get_api_version()
    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{MODEL_NAME}:generateContent"
    params = {"key": token}
    headers = {"Content-Type": "application/json"}

    # Construct prompt for Gemini from a customizable template
    DEFAULT_PROMPT = (
        "Given the mood or emotion '{mood}', select the most relevant movie genres from this list: {labels}.\n"
        "Respond ONLY with a pure JSON array (no extra text, no code fences), containing the top {top_k} exact genre names.\n"
        "Example: [\"Action\", \"Adventure\"]"
    )

    template = settings.gemini_prompt_template or DEFAULT_PROMPT
    try:
        prompt = template.format(mood=mood, labels=', '.join(labels), top_k=top_k)
    except Exception:
        # if user provided a bad template, fall back to default to avoid 500s
        prompt = DEFAULT_PROMPT.format(mood=mood, labels=', '.join(labels), top_k=top_k)

    payload: Dict[str, object] = {
        "contents": [{
            "parts":[{
                "text": prompt
            }]
        }]
    }

    _reset_state()
    global _last_http_status, _last_raw_response, _last_request_payload, _last_error
    _last_request_payload = payload

    with httpx.Client(timeout=settings.request_timeout_s) as client:
        try:
            r = client.post(url, headers=headers, json=payload, params=params)
            _last_http_status = r.status_code
            data = r.json()
            _last_raw_response = data  # store before any mutation
        except httpx.HTTPError as he:  # network / protocol
            _last_error = f"HTTP client error: {he}"
            raise RuntimeError(_last_error) from he
        except Exception as e:
            _last_error = f"Unexpected transport error: {e}"
            raise RuntimeError(_last_error) from e

        # Non-2xx handling (Gemini returns JSON error object)
        if _last_http_status and _last_http_status >= 300:
            msg = None
            if isinstance(_last_raw_response, dict):
                err = _last_raw_response.get("error")  # type: ignore[arg-type]
                if isinstance(err, dict):
                    msg = err.get("message")
            _last_error = f"Gemini non-2xx ({_last_http_status}): {msg or 'no message'}"
            # Auto fallback attempt for common 404 model mismatch
            if _last_http_status == 404 and "not found" in (_last_error.lower()):
                # list models and decide fallback target
                _list_models(token)
                target = _choose_fallback_model()
                if target:
                    # second attempt
                    fallback_version = "v1beta" if ("1.5" in target or "2.0" in target) else "v1"
                    try:
                        r2 = client.post(
                            f"https://generativelanguage.googleapis.com/{fallback_version}/models/{target}:generateContent",
                            headers=headers,
                            json=payload,
                            params=params,
                        )
                        _last_http_status = r2.status_code
                        data = r2.json()
                        _last_raw_response = data
                        if _last_http_status < 300:
                            MODEL_NAME = target  # update for subsequent calls
                            _last_error = None
                            _used_model = target
                        else:
                            raise RuntimeError(_last_error)
                    except Exception:
                        raise RuntimeError(_last_error)
                else:
                    raise RuntimeError(_last_error)
            else:
                raise RuntimeError(_last_error)
        
        # Extract the response text and parse it as JSON
        try:
            # Check for structured API error object (should have been caught above but double guard)
            if isinstance(data, dict) and 'error' in data:
                error_msg = isinstance(data['error'], dict) and data['error'].get('message', 'Unknown Gemini API error')
                _last_error = f"Gemini API error (post-parse): {error_msg}"
                raise RuntimeError(_last_error)

            # Track used model for debug (already declared global at function start)
            _used_model = MODEL_NAME

            # Validate candidates structure
            if not isinstance(data, dict) or 'candidates' not in data:
                _last_error = "Missing 'candidates' in Gemini response"
                raise RuntimeError(_last_error)
            candidates = data.get('candidates')
            if not isinstance(candidates, list) or not candidates:
                _last_error = "Empty 'candidates' array in Gemini response"
                raise RuntimeError(_last_error)
            first = candidates[0]
            if not isinstance(first, dict):
                _last_error = "First candidate malformed"
                raise RuntimeError(_last_error)
            content = first.get('content')
            if not isinstance(content, dict):
                _last_error = "Candidate content missing"
                raise RuntimeError(_last_error)
            parts = content.get('parts')
            if not isinstance(parts, list) or not parts or not isinstance(parts[0], dict):
                _last_error = "Content parts missing or invalid"
                raise RuntimeError(_last_error)
            response_text = parts[0].get('text', '')
            # Clean the response text (remove any markdown or extra text)
            response_text = response_text.strip()
            if response_text.startswith("```"):
                response_text = response_text[response_text.find("["):response_text.rfind("]")+1]
            selected_genres = json.loads(response_text)
            
            # Validate response format
            if not isinstance(selected_genres, list):
                _last_error = "Invalid response format: expected a list"
                raise RuntimeError(_last_error)
            
            # Ensure all genres are valid
            valid_genres = [g for g in selected_genres if g in TMDB_GENRES]
            if not valid_genres:
                _last_error = f"No valid genres found in response: {selected_genres}"
                raise RuntimeError(_last_error)
            
            # Ensure we only take top_k genres
            selected_genres = valid_genres[:top_k]
            
            # Convert to list of tuples with genre IDs
            return [(name, TMDB_GENRES[name]) for name in selected_genres]
            
        except (KeyError, json.JSONDecodeError, IndexError, TypeError) as e:
            _last_error = f"Failed to parse Gemini API response: {str(e)}"
            raise RuntimeError(_last_error) from e