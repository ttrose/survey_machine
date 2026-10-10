"""Small asynchronous database adapters; native drivers never load in Workers."""

from typing import Any, Protocol


class Database(Protocol):
    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]: ...
    async def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None: ...
    async def execute(self, sql: str, params: tuple = ()) -> int: ...
    async def close(self) -> None: ...


class D1Database:
    def __init__(self, binding):
        # Keep reads within each request consistent, including after writes.
        self.binding = binding.withSession("first-primary")

    def statement(self, sql: str, params: tuple):
        return self.binding.prepare(sql).bind(*params) if params else self.binding.prepare(sql)

    async def fetch_all(self, sql: str, params: tuple = ()):
        result = await self.statement(sql, params).all()
        # The Workers SDK converts D1 rows to Python dictionaries.
        return result.results

    async def fetch_one(self, sql: str, params: tuple = ()):
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple = ()):
        result = await self.statement(sql, params).run()
        return int(result.meta.changes)

    async def close(self):
        pass


class SQLiteDatabase:
    def __init__(self, path: str):
        import sqlite3
        import threading
        from pathlib import Path

        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        if path != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        self.lock = threading.RLock()

    async def fetch_all(self, sql: str, params: tuple = ()):
        import asyncio

        def query():
            with self.lock:
                return [dict(row) for row in self.connection.execute(sql, params).fetchall()]
        return await asyncio.to_thread(query)

    async def fetch_one(self, sql: str, params: tuple = ()):
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple = ()):
        import asyncio

        def query():
            with self.lock:
                return self.connection.execute(sql, params).rowcount
        return await asyncio.to_thread(query)

    async def migrate(self, version: str, sql: str):
        import asyncio

        def apply():
            with self.lock:
                try:
                    self.connection.executescript("BEGIN IMMEDIATE;\n" + sql)
                    self.connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
                    self.connection.execute("COMMIT")
                except Exception:
                    if self.connection.in_transaction:
                        self.connection.execute("ROLLBACK")
                    raise
        await asyncio.to_thread(apply)

    async def close(self):
        self.connection.close()


class PostgresDatabase:
    def __init__(self, pool):
        self.pool = pool

    async def fetch_all(self, sql: str, params: tuple = ()):
        async with self.pool.connection() as connection:
            cursor = await connection.execute(sql.replace("?", "%s"), params)
            return await cursor.fetchall()

    async def fetch_one(self, sql: str, params: tuple = ()):
        rows = await self.fetch_all(sql, params)
        return rows[0] if rows else None

    async def execute(self, sql: str, params: tuple = ()):
        async with self.pool.connection() as connection:
            cursor = await connection.execute(sql.replace("?", "%s"), params)
            return cursor.rowcount

    async def migrate(self, version: str, sql: str):
        async with self.pool.connection() as connection:
            async with connection.transaction():
                for statement in sql.split(";"):
                    if statement.strip():
                        await connection.execute(statement)
                await connection.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))

    async def close(self):
        await self.pool.close()


async def open_database(url: str):
    from pathlib import Path

    if url.startswith("sqlite:///"):
        database = SQLiteDatabase(url.removeprefix("sqlite:///"))
    elif url.startswith(("postgresql://", "postgres://")):
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(url, open=False, min_size=1, max_size=10, kwargs={"row_factory": dict_row})
        await pool.open(wait=True)
        database = PostgresDatabase(pool)
    else:
        raise ValueError("DATABASE_URL must use sqlite:/// or postgresql://.")
    try:
        await database.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)")
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            if not await database.fetch_one("SELECT version FROM schema_migrations WHERE version = ?", (path.name,)):
                await database.migrate(path.name, path.read_text(encoding="utf-8"))
        return database
    except Exception:
        await database.close()
        raise
