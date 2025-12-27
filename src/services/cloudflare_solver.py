"""Cloudflare Solver - Unified Cloudflare challenge handling"""
import asyncio
from typing import Optional, Dict, Any
from ..core.config import config


async def solve_cloudflare_challenge(proxy_url: Optional[str] = None, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """解决 Cloudflare challenge
    
    使用配置的 Cloudflare Solver API，最多重试指定次数
    
    Args:
        proxy_url: 代理 URL（当前未使用，保留接口兼容性）
        max_retries: 最大重试次数
        
    Returns:
        包含 cookies 和 user_agent 的字典，如 {"cookies": {...}, "user_agent": "..."}
        失败返回 None
    """
    import httpx
    
    if not config.cloudflare_solver_enabled or not config.cloudflare_solver_api_url:
        print("⚠️ Cloudflare Solver API 未配置，请在配置文件中设置 cloudflare_solver_enabled 和 cloudflare_solver_api_url")
        return None
    
    api_url = config.cloudflare_solver_api_url
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"🔄 调用 Cloudflare Solver API: {api_url} (尝试 {attempt}/{max_retries})")
            
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.get(api_url)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        cookies = data.get("cookies", {})
                        user_agent = data.get("user_agent")
                        print(f"✅ Cloudflare Solver API 返回成功，耗时 {data.get('elapsed_seconds', 0):.2f}s")
                        return {"cookies": cookies, "user_agent": user_agent}
                    else:
                        print(f"⚠️ Cloudflare Solver API 返回失败: {data.get('error')}")
                else:
                    print(f"⚠️ Cloudflare Solver API 请求失败: {response.status_code}")
                    
        except Exception as e:
            print(f"⚠️ Cloudflare Solver API 调用失败: {e}")
        
        # 如果不是最后一次尝试，等待后重试
        if attempt < max_retries:
            wait_time = attempt * 2  # 2s, 4s
            print(f"⏳ 等待 {wait_time}s 后重试...")
            await asyncio.sleep(wait_time)
    
    print(f"❌ Cloudflare Solver API 调用失败，已重试 {max_retries} 次")
    return None


def is_cloudflare_challenge(status_code: int, headers: dict, response_text: str) -> bool:
    """检测响应是否为 Cloudflare challenge
    
    Args:
        status_code: HTTP 状态码
        headers: 响应头
        response_text: 响应文本
    
    Returns:
        True 如果是 Cloudflare challenge
    """
    if status_code not in [429, 403]:
        return False
    
    return (
        "cf-mitigated" in str(headers) or
        "Just a moment" in response_text or
        "challenge-platform" in response_text
    )
