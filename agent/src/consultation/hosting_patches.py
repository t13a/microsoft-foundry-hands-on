"""Foundry のホストのライブラリへの回避策。

プレリリース版の組み合わせによるもので、版を上げたら要否を確かめる。

状態ストアは、項目を 1 つ読み書きするたびに `FoundryStateStore.get_or_create` でストア自体を
取得し直す。項目の操作に要るのはストアの名前だけなので、同じプロセスで一度確かめたストアは
取得を省く。1 回の発言で 50 回ほどの往復 (約 4 秒) がなくなる。
"""

from typing import Any

from azure.ai.agentserver.core.storage._state import FoundryStateStore

_confirmed: set[tuple[Any, ...]] = set()
_applied = False


def apply() -> None:
    global _applied
    if _applied:
        return
    original = FoundryStateStore.get_or_create.__func__  # type: ignore[attr-defined]

    async def get_or_create(cls, name, credential=None, endpoint=None, **kwargs):
        key = (name, str(endpoint), kwargs.get("user_isolation"), kwargs.get("user_id"))
        if key in _confirmed:
            return cls(name, credential, endpoint, **kwargs)
        store = await original(cls, name, credential, endpoint, **kwargs)
        _confirmed.add(key)
        return store

    FoundryStateStore.get_or_create = classmethod(get_or_create)  # type: ignore[method-assign]
    _applied = True
