# openai_sentinel_token.py
import argparse
import base64
import hashlib
import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from curl_cffi import requests as curl_requests

from src.core.http_utils import build_sora_headers, get_random_fingerprint

CHATGPT_BASE_URL = "https://chatgpt.com"
SORA_BASE_URL = "https://sora.chatgpt.com"
SENTINEL_FLOW = "sora_2_create_task"

# PoW 相关常量
POW_MAX_ITERATION = 500000
POW_CORES = [8, 16, 24, 32]
POW_SCRIPTS = [
    "https://cdn.oaistatic.com/_next/static/cXh69klOLzS0Gy2joLDRS/_ssgManifest.js?dpl=453ebaec0d44c2decab71692e1bfe39be35a24b3"
]
POW_DPL = ["prod-f501fe933b3edf57aea882da888e1a544df99840"]
POW_NAVIGATOR_KEYS = [
    "registerProtocolHandler−function registerProtocolHandler() { [native code] }",
    "storage−[object StorageManager]",
    "locks−[object LockManager]",
    "appCodeName−Mozilla",
    "permissions−[object Permissions]",
    "webdriver−false",
    "vendor−Google Inc.",
    "mediaDevices−[object MediaDevices]",
    "cookieEnabled−true",
    "product−Gecko",
    "productSub−20030107",
    "hardwareConcurrency−32",
    "onLine−true",
]
POW_DOCUMENT_KEYS = ["_reactListeningo743lnnpvdg", "location"]
POW_WINDOW_KEYS = [
    "0", "window", "self", "document", "name", "location",
    "navigator", "screen", "innerWidth", "innerHeight",
    "localStorage", "sessionStorage", "crypto", "performance",
    "fetch", "setTimeout", "setInterval", "console",
]


def get_pow_parse_time() -> str:
    """生成 PoW 用的时间字符串 (EST 时区)"""
    now = datetime.now(timezone(timedelta(hours=-5)))
    return now.strftime("%a %b %d %Y %H:%M:%S") + " GMT-0500 (Eastern Standard Time)"


def get_pow_config(user_agent: str) -> list:
    """生成 PoW 配置数组"""
    return [
        random.choice([1920 + 1080, 2560 + 1440, 1920 + 1200, 2560 + 1600]),
        get_pow_parse_time(),
        4294705152,
        0,  # [3] 动态
        user_agent,
        random.choice(POW_SCRIPTS) if POW_SCRIPTS else "",
        random.choice(POW_DPL) if POW_DPL else None,
        "en-US",
        "en-US,es-US,en,es",
        0,  # [9] 动态
        random.choice(POW_NAVIGATOR_KEYS),
        random.choice(POW_DOCUMENT_KEYS),
        random.choice(POW_WINDOW_KEYS),
        time.perf_counter() * 1000,
        str(uuid4()),
        "",
        random.choice(POW_CORES),
        time.time() * 1000 - (time.perf_counter() * 1000),
    ]


def solve_pow(seed: str, difficulty: str, config: list) -> Tuple[str, bool]:
    """执行真正的 PoW 计算"""
    diff_len = len(difficulty) // 2
    seed_encoded = seed.encode()
    target_diff = bytes.fromhex(difficulty)
    
    static_part1 = (json.dumps(config[:3], separators=(',', ':'), ensure_ascii=False)[:-1] + ',').encode()
    static_part2 = (',' + json.dumps(config[4:9], separators=(',', ':'), ensure_ascii=False)[1:-1] + ',').encode()
    static_part3 = (',' + json.dumps(config[10:], separators=(',', ':'), ensure_ascii=False)[1:]).encode()
    
    for i in range(POW_MAX_ITERATION):
        dynamic_i = str(i).encode()
        dynamic_j = str(i >> 1).encode()
        
        final_json = static_part1 + dynamic_i + static_part2 + dynamic_j + static_part3
        b64_encoded = base64.b64encode(final_json)
        
        hash_value = hashlib.sha3_512(seed_encoded + b64_encoded).digest()
        
        if hash_value[:diff_len] <= target_diff:
            return b64_encoded.decode(), True
    
    error_token = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + base64.b64encode(f'"{seed}"'.encode()).decode()
    return error_token, False


def get_pow_token(user_agent: str) -> str:
    """生成初始 PoW token"""
    config = get_pow_config(user_agent)
    seed = format(random.random())
    difficulty = "0fffff"
    solution, _ = solve_pow(seed, difficulty, config)
    return "gAAAAAC" + solution


def generate_id() -> str:
    """生成请求 ID"""
    return str(uuid4())


def build_sentinel_token(
    flow: str,
    req_id: str,
    pow_token: str,
    resp: Dict[str, Any],
    user_agent: str,
) -> str:
    """构建 openai-sentinel-token
    
    如果响应中包含 proofofwork 要求，会执行真正的 PoW 计算
    """
    final_pow_token = pow_token
    
    # 检查是否需要执行 PoW
    proofofwork = resp.get("proofofwork", {})
    if proofofwork.get("required"):
        seed = proofofwork.get("seed", "")
        difficulty = proofofwork.get("difficulty", "")
        if seed and difficulty:
            config = get_pow_config(user_agent)
            solution, success = solve_pow(seed, difficulty, config)
            final_pow_token = "gAAAAAB" + solution
            if not success:
                print(f"⚠️ PoW 计算失败，使用错误标记")
    
    token_payload = {
        "p": final_pow_token,
        "t": resp.get("turnstile", {}).get("dx", ""),
        "c": resp.get("token", ""),
        "id": req_id,
        "flow": flow,
    }
    return json.dumps(token_payload, ensure_ascii=False, separators=(",", ":"))


def post_sentinel_req(
    session: curl_requests.Session,
    pow_token: str,
    req_id: str,
    fingerprint: str,
    user_agent: Optional[str] = None,
    auth_token: Optional[str] = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """Request /backend-api/sentinel/req"""
    url = f"{CHATGPT_BASE_URL}/backend-api/sentinel/req"
    payload = {"p": pow_token, "flow": SENTINEL_FLOW, "id": req_id}
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://sora.chatgpt.com",
        "Referer": "https://sora.chatgpt.com/",
    }
    if user_agent:
        headers["User-Agent"] = user_agent
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    if debug:
        _print_request("POST", url, headers, payload)

    response = session.post(
        url,
        json=payload,
        headers=headers,
        timeout=10,
        impersonate=fingerprint,
    )
    _raise_for_status(response)
    return response.json()


def generate_sentinel_token(
    session: curl_requests.Session,
    fingerprint: str,
    user_agent: Optional[str] = None,
    auth_token: Optional[str] = None,
    debug: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """Generate openai-sentinel-token via /backend-api/sentinel/req"""
    req_id = generate_id()
    ua = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    pow_token = get_pow_token(ua)

    if debug:
        print(f"Generated PoW token (len={len(pow_token)})")

    resp = post_sentinel_req(
        session,
        pow_token,
        req_id,
        fingerprint,
        user_agent=ua,
        auth_token=auth_token,
        debug=debug,
    )

    if debug:
        dx = resp.get("turnstile", {}).get("dx", "")
        print(f"Turnstile dx length: {len(dx)}")
        proofofwork = resp.get("proofofwork", {})
        if proofofwork.get("required"):
            print(f"PoW required: seed={proofofwork.get('seed', '')[:20]}..., difficulty={proofofwork.get('difficulty', '')}")

    sentinel_token = build_sentinel_token(SENTINEL_FLOW, req_id, pow_token, resp, ua)
    return sentinel_token, resp



def create_nf_task(
    session: curl_requests.Session,
    access_token: str,
    payload: Dict[str, Any],
    fingerprint: str,
    sentinel_auth: bool,
    debug: bool = False,
) -> Dict[str, Any]:
    """Call /backend/nf/create with a generated openai-sentinel-token."""
    sentinel_token, sentinel_resp = generate_sentinel_token(
        session,
        fingerprint,
        auth_token=access_token if sentinel_auth else None,
        debug=debug,
    )

    if debug:
        print(f"Sentinel token expires_at: {sentinel_resp.get('expire_at')}")

    headers = build_sora_headers(
        token=access_token,
        content_type="application/json",
        sentinel_token=sentinel_token,
    )
    headers["Accept"] = "application/json"

    url = f"{SORA_BASE_URL}/backend/nf/create"
    if debug:
        _print_request("POST", url, headers, payload)
    response = session.post(
        url,
        headers=headers,
        json=payload,
        timeout=30,
        impersonate=fingerprint,
    )
    _raise_for_status(response)
    return response.json()


def _format_response_body(response: curl_requests.Response) -> str:
    try:
        return json.dumps(response.json(), ensure_ascii=False, indent=2)
    except Exception:
        return response.text


def _raise_for_status(response: curl_requests.Response) -> None:
    if response.status_code in (200, 201):
        return
    reason = response.reason or ""
    print(f"HTTP Error {response.status_code}: {reason}")
    print("Response headers:")
    for key, value in response.headers.items():
        print(f"  {key}: {value}")
    print("Response body:")
    print(_format_response_body(response))
    raise SystemExit(1)


def _mask_header_value(key: str, value: str) -> str:
    lower_key = key.lower()
    if lower_key == "authorization":
        if value.startswith("Bearer "):
            token = value[7:]
            return f"Bearer {_mask_token(token)}"
        return _mask_token(value)
    if lower_key == "openai-sentinel-token":
        return _mask_token(value, keep_start=12, keep_end=12)
    return value


def _mask_token(value: str, keep_start: int = 6, keep_end: int = 6) -> str:
    if len(value) <= keep_start + keep_end:
        return value
    return f"{value[:keep_start]}...{value[-keep_end:]}"


def _print_request(
    method: str, url: str, headers: Dict[str, Any], body: Dict[str, Any]
) -> None:
    print(f"{method} {url}")
    print("Request headers:")
    for key, value in headers.items():
        if isinstance(value, str):
            safe_value = _mask_header_value(key, value)
        else:
            safe_value = value
        print(f"  {key}: {safe_value}")
    print("Request body:")
    print(json.dumps(body, ensure_ascii=False, indent=2))


def build_payload(prompt: str, orientation: str, n_frames: int) -> Dict[str, Any]:
    return {
        "kind": "video",
        "prompt": prompt,
        "title": None,
        "orientation": orientation,
        "size": "small",
        "n_frames": n_frames,
        "inpaint_items": [],
        "remix_target_id": None,
        "metadata": None,
        "cameo_ids": None,
        "cameo_replacements": None,
        "model": "sy_8",
        "style_id": None,
        "audio_caption": None,
        "audio_transcript": None,
        "video_caption": None,
        "storyboard_id": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sora /backend/nf/create test demo")
    parser.add_argument("--token", default=None, help="Access token")
    parser.add_argument("--prompt", default="test prompt", help="Prompt text")
    parser.add_argument(
        "--orientation", default="portrait", choices=["portrait", "landscape"]
    )
    parser.add_argument("--n-frames", type=int, default=450)
    parser.add_argument(
        "--only-sentinel", action="store_true", help="Only print sentinel token"
    )
    parser.add_argument(
        "--fingerprint",
        default=None,
        help="curl_cffi fingerprint (default: random mobile)",
    )
    parser.add_argument(
        "--sentinel-auth",
        action="store_true",
        help="Add Authorization header when calling /backend-api/sentinel/req",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print request headers and payload (tokens are masked)",
    )
    args = parser.parse_args()

    fingerprint = args.fingerprint or get_random_fingerprint()
    session = curl_requests.Session()

    if args.only_sentinel:
        if args.sentinel_auth and not args.token:
            raise SystemExit("Missing token for --sentinel-auth.")
        sentinel, resp = generate_sentinel_token(
            session,
            fingerprint,
            auth_token=args.token if args.sentinel_auth else None,
            debug=args.debug,
        )
        print("Sentinel Token:")
        print(sentinel)
        print("\nResponse Info:")
        print(f"  persona: {resp.get('persona')}")
        print(f"  expire_at: {resp.get('expire_at')}")
        print(f"  expire_after: {resp.get('expire_after')}s")
        print(f"  turnstile required: {resp.get('turnstile', {}).get('required')}")
        print(f"  pow required: {resp.get('proofofwork', {}).get('required')}")
        return

    if not args.token:
        raise SystemExit("Missing token. Set --token.")

    payload = build_payload(args.prompt, args.orientation, args.n_frames)
    result = create_nf_task(
        session,
        args.token,
        payload,
        fingerprint,
        args.sentinel_auth,
        debug=args.debug,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
