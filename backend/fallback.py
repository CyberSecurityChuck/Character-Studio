"""The fallback list of each engine panel (Phase 8C, DECISIONS.md D046).

Off by default. When the user ticks "Switch automatically" in an engine panel, the
accounts (Claude Code, Codex) or API keys they tick there, in the order they set, are
where a run moves when its own account or key cannot be used. The list is kept per
choice (`codex_cli:generation`, `openai_api:analysis`, …) inside the registry it belongs
to: `cli-accounts/accounts.json` for accounts, `keys/keys.json` for keys. These helpers
work on that registry's data; the registries own the reading, writing and locking.
"""

MAX_ORDER = 10


def clean(raw) -> dict:
    """The stored lists, without anything malformed."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for choice, value in raw.items():
        if not isinstance(choice, str) or not isinstance(value, dict):
            continue
        order = [i for i in value.get("order", []) if isinstance(i, str)]
        result[choice] = {"on": value.get("on") is True, "order": _unique(order)[:MAX_ORDER]}
    return result


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [i for i in items if not (i in seen or seen.add(i))]


def read(data: dict, choice: str, existing: list[str]) -> dict:
    """One panel's list: whether it is on and the accounts or keys in it that still exist."""
    stored = data.get("fallback", {}).get(choice) or {}
    known = set(existing)
    return {
        "on": stored.get("on") is True,
        "order": [i for i in stored.get("order", []) if i in known],
    }


def write(data: dict, choice: str, on: bool, order: list[str]) -> None:
    data.setdefault("fallback", {})[choice] = {"on": bool(on), "order": _unique(order)[:MAX_ORDER]}


def forget(data: dict, prefix: str, item_id: str) -> None:
    """A removed account or key leaves every list of its engine or provider."""
    for choice, value in data.get("fallback", {}).items():
        if choice.startswith(prefix):
            value["order"] = [i for i in value.get("order", []) if i != item_id]


def promote(data: dict, choice: str, old: str, new: str) -> None:
    """After an automatic switch the one that worked becomes the panel's choice (D046); the
    one that could not be used goes to the end of the list, so it is tried last once it
    works again."""
    data.setdefault("active", {})[choice] = new
    stored = data.setdefault("fallback", {}).setdefault(choice, {"on": True, "order": []})
    order = [i for i in stored.get("order", []) if i not in (new, old)]
    stored["order"] = [*order, old][:MAX_ORDER]
