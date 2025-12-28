"""Database connection pool for SQLite"""
import asyncio
import aiosqlite
from typing import Optional
from contextlib import asynccontextmanager


class DatabasePool:
    """SQLite connection pool with read/write separation
    
    SQLite 特性：
    - 写操作需要独占锁，同一时间只能有一个写操作
    - 读操作可以并发（WAL 模式下）
    
    策略：
    - 使用单个写连接 + 写锁确保写操作串行
    - 使用连接池处理读操作
    - 启用 WAL 模式提高并发性能
    """
    
    def __init__(self, db_path: str, pool_size: int = 5):
        self.db_path = db_path
        self.pool_size = pool_size
        self._read_pool: asyncio.Queue = asyncio.Queue()
        self._write_conn: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self):
        """Initialize the connection pool"""
        if self._initialized:
            return
        
        # Create write connection
        self._write_conn = await aiosqlite.connect(self.db_path)
        # Enable WAL mode for better concurrency
        await self._write_conn.execute("PRAGMA journal_mode=WAL")
        await self._write_conn.execute("PRAGMA synchronous=NORMAL")
        await self._write_conn.execute("PRAGMA cache_size=10000")
        await self._write_conn.execute("PRAGMA temp_store=MEMORY")
        
        # Create read connections pool
        for _ in range(self.pool_size):
            conn = await aiosqlite.connect(self.db_path)
            await conn.execute("PRAGMA query_only=ON")  # Read-only mode
            await self._read_pool.put(conn)
        
        self._initialized = True
        print(f"✅ Database pool initialized (read pool: {self.pool_size}, WAL mode enabled)")
    
    async def close(self):
        """Close all connections"""
        if self._write_conn:
            await self._write_conn.close()
            self._write_conn = None
        
        while not self._read_pool.empty():
            conn = await self._read_pool.get()
            await conn.close()
        
        self._initialized = False
    
    @asynccontextmanager
    async def read_connection(self):
        """Get a read connection from pool"""
        if not self._initialized:
            await self.initialize()
        
        conn = await self._read_pool.get()
        try:
            conn.row_factory = aiosqlite.Row
            yield conn
        finally:
            await self._read_pool.put(conn)
    
    @asynccontextmanager
    async def write_connection(self):
        """Get the write connection with lock"""
        if not self._initialized:
            await self.initialize()
        
        async with self._write_lock:
            self._write_conn.row_factory = aiosqlite.Row
            yield self._write_conn


# Global pool instance
_pool: Optional[DatabasePool] = None


def get_pool() -> Optional[DatabasePool]:
    """Get the global database pool"""
    return _pool


async def init_pool(db_path: str, pool_size: int = 5):
    """Initialize the global database pool"""
    global _pool
    if _pool is None:
        _pool = DatabasePool(db_path, pool_size)
        await _pool.initialize()
    return _pool


async def close_pool():
    """Close the global database pool"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
