import os, re, logging
from contextlib import asynccontextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)
_pool = None
_use_pg: bool = False

async def init_pool() -> None:
    global _pool, _use_pg
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        import asyncpg
        _pool = await asyncpg.create_pool(
            database_url, min_size=2, max_size=10,
            command_timeout=30, statement_cache_size=0,
        )
        _use_pg = True
        logger.info("db.py: PostgreSQL pool initialised")
    else:
        _use_pg = False
        logger.info("db.py: SQLite mode (no DATABASE_URL)")

async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

def is_postgres() -> bool:
    return _use_pg

def _q2d(sql: str) -> str:
    n = 0
    r = []
    for c in sql:
        if c == "?":
            n += 1
            r.append(f"${n}")
        else:
            r.append(c)
    return "".join(r)

class DBConn:
    __slots__ = ("_conn", "_is_pg")
    def __init__(self, conn, is_pg): self._conn = conn; self._is_pg = is_pg

    async def fetch(self, sql, *a):
        if self._is_pg:
            return [dict(r) for r in await self._conn.fetch(_q2d(sql), *a)]
        import aiosqlite; self._conn.row_factory = aiosqlite.Row
        async with self._conn.execute(sql, a) as c: return [dict(r) for r in await c.fetchall()]

    async def fetchrow(self, sql, *a):
        if self._is_pg:
            r = await self._conn.fetchrow(_q2d(sql), *a); return dict(r) if r else None
        import aiosqlite; self._conn.row_factory = aiosqlite.Row
        async with self._conn.execute(sql, a) as c:
            r = await c.fetchone(); return dict(r) if r else None

    async def fetchval(self, sql, *a):
        if self._is_pg: return await self._conn.fetchval(_q2d(sql), *a)
        async with self._conn.execute(sql, a) as c:
            r = await c.fetchone(); return r[0] if r else None

    async def execute(self, sql, *a):
        if self._is_pg:
            sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO","INSERT INTO",sql,flags=re.IGNORECASE)
            if "INSERT OR IGNORE" in sql.upper(): sql = sql.rstrip() + " ON CONFLICT DO NOTHING"
            if re.search(r"INSERT INTO", sql, re.IGNORECASE) and "ON CONFLICT" not in sql.upper() and re.search(r"OR\s+IGNORE",sql,re.IGNORECASE):
                sql = sql.rstrip() + " ON CONFLICT DO NOTHING"
            await self._conn.execute(_q2d(sql), *a)
        else:
            await self._conn.execute(sql, a)

    async def commit(self):
        if not self._is_pg: await self._conn.commit()

    async def upsert(self, table, conflict_cols, data):
        cols = list(data.keys()); vals = list(data.values())
        if self._is_pg:
            pg_ph = ", ".join(f"${i+1}" for i in range(len(vals)))
            conflict = ", ".join(conflict_cols)
            update_set = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in conflict_cols)
            sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({pg_ph}) ON CONFLICT ({conflict}) DO " +
                   (f"UPDATE SET {update_set}" if update_set else "NOTHING"))
            await self._conn.execute(sql, *vals)
        else:
            ph = ", ".join("?" for _ in vals)
            await self._conn.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({ph})", vals)
            await self._conn.commit()

    @asynccontextmanager
    async def transaction(self):
        if self._is_pg:
            async with self._conn.transaction(): yield self
        else:
            await self._conn.execute("BEGIN EXCLUSIVE")
            try: yield self; await self._conn.commit()
            except: await self._conn.execute("ROLLBACK"); raise

@asynccontextmanager
async def acquire():
    if _use_pg:
        async with _pool.acquire() as raw: yield DBConn(raw, True)
    else:
        import aiosqlite, config
        async with aiosqlite.connect(config.DB_PATH) as raw: yield DBConn(raw, False)
