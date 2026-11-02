"""SQL Server application locks; SQLite fallback is only for isolated unit tests."""
from contextlib import contextmanager
from threading import Lock
from weakref import WeakKeyDictionary

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

_locks: dict[str, Lock] = {}
_registry_lock = Lock()
_guard_engines = WeakKeyDictionary()
_ACQUIRE = text("""
DECLARE @result int;
EXEC @result = sys.sp_getapplock @Resource=:resource, @LockMode='Exclusive',
    @LockOwner=:owner, @LockTimeout=:timeout;
SELECT @result;
""")


def transaction_lock(db, resource: str):
    if db.bind.dialect.name == "mssql":
        result = db.execute(_ACQUIRE, {"resource": resource, "owner": "Transaction", "timeout": 5000}).scalar()
        if result < 0:
            raise HTTPException(503, "Giao dịch đang bận; thử lại bằng cùng payment_id")


@contextmanager
def session_lock(engine, resource: str):
    """Serialize an orchestrator across HTTP calls, without an open SQL transaction."""
    if engine.dialect.name != "mssql":
        with _registry_lock:
            lock = _locks.setdefault(resource, Lock())
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()
        return
    # A session guard lives across network calls. It must not consume the ORM
    # pool that those calls' short state transactions need: enough concurrent
    # guards could otherwise exhaust that pool and stall every orchestrator.
    # NullPool also closes a guard's DBAPI connection after each use.
    with _registry_lock:
        guard_engine = _guard_engines.get(engine)
        if guard_engine is None:
            guard_engine = create_engine(engine.url, poolclass=NullPool)
            _guard_engines[engine] = guard_engine
    with guard_engine.connect() as connection:
        acquired = False
        try:
            try:
                result = connection.execute(_ACQUIRE, {"resource": resource, "owner": "Session", "timeout": 0}).scalar()
                connection.commit()
                acquired = result >= 0
            except BaseException:
                # Acquisition may have reached SQL Server even if its reply was
                # lost. Never recycle a session with an unknown lock state.
                connection.invalidate()
                raise
            yield acquired
        finally:
            if acquired:
                try:
                    connection.execute(text("EXEC sys.sp_releaseapplock @Resource=:resource, @LockOwner='Session'"), {"resource": resource})
                    connection.commit()
                except Exception:
                    # Never return a pooled connection that may still own the lock.
                    connection.invalidate()
                    raise
