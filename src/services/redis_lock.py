"""Redis-based distributed lock manager for concurrent request handling"""
import asyncio
from typing import Optional
from ..core.config import config

# Redis client (lazy initialization)
_redis_client = None


async def get_redis_client():
    """Get or create Redis client"""
    global _redis_client
    if _redis_client is None and config.redis_enabled:
        try:
            import redis.asyncio as redis
            _redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                password=config.redis_password or None,
                db=config.redis_db,
                decode_responses=True
            )
            # Test connection
            await _redis_client.ping()
            print(f"✅ Redis connected: {config.redis_host}:{config.redis_port}")
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}, falling back to local locks")
            _redis_client = None
    return _redis_client


class RedisLock:
    """Distributed lock using Redis"""
    
    def __init__(self, key: str, timeout: int = None):
        self.key = f"lock:{key}"
        self.timeout = timeout or config.redis_lock_timeout
        self._lock_value = None
    
    async def acquire(self, blocking: bool = True, timeout: float = None) -> bool:
        """Acquire the lock"""
        import uuid
        redis_client = await get_redis_client()
        
        if redis_client is None:
            # Fallback: always succeed if Redis not available
            return True
        
        self._lock_value = str(uuid.uuid4())
        wait_timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()
        
        while True:
            # Try to set lock with NX (only if not exists)
            acquired = await redis_client.set(
                self.key, 
                self._lock_value, 
                nx=True, 
                ex=self.timeout
            )
            
            if acquired:
                return True
            
            if not blocking:
                return False
            
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= wait_timeout:
                return False
            
            # Wait and retry
            await asyncio.sleep(0.1)
    
    async def release(self):
        """Release the lock"""
        redis_client = await get_redis_client()
        
        if redis_client is None or self._lock_value is None:
            return
        
        # Use Lua script to ensure we only delete our own lock
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            await redis_client.eval(lua_script, 1, self.key, self._lock_value)
        except Exception as e:
            print(f"⚠️ Failed to release Redis lock: {e}")
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


class RedisCFLock:
    """Distributed lock for Cloudflare credential refresh"""
    
    CF_LOCK_KEY = "cf:refresh:lock"
    CF_REFRESHING_KEY = "cf:refreshing"
    
    @classmethod
    async def is_refreshing(cls) -> bool:
        """Check if CF credentials are being refreshed"""
        redis_client = await get_redis_client()
        if redis_client is None:
            return False
        
        try:
            return await redis_client.exists(cls.CF_REFRESHING_KEY) > 0
        except:
            return False
    
    @classmethod
    async def set_refreshing(cls, value: bool, ttl: int = 60):
        """Set CF refreshing status"""
        redis_client = await get_redis_client()
        if redis_client is None:
            return
        
        try:
            if value:
                await redis_client.set(cls.CF_REFRESHING_KEY, "1", ex=ttl)
            else:
                await redis_client.delete(cls.CF_REFRESHING_KEY)
        except Exception as e:
            print(f"⚠️ Failed to set CF refreshing status: {e}")
    
    @classmethod
    async def acquire_lock(cls, timeout: int = 60) -> bool:
        """Acquire CF refresh lock"""
        redis_client = await get_redis_client()
        if redis_client is None:
            return True  # Fallback: allow if Redis not available
        
        try:
            import uuid
            lock_value = str(uuid.uuid4())
            acquired = await redis_client.set(
                cls.CF_LOCK_KEY,
                lock_value,
                nx=True,
                ex=timeout
            )
            return bool(acquired)
        except:
            return True
    
    @classmethod
    async def release_lock(cls):
        """Release CF refresh lock"""
        redis_client = await get_redis_client()
        if redis_client is None:
            return
        
        try:
            await redis_client.delete(cls.CF_LOCK_KEY)
        except:
            pass


async def close_redis():
    """Close Redis connection"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
