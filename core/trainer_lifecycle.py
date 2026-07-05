from __future__ import annotations

from typing import Any


def reset_turn_flags(state: dict[str, Any], actor: str) -> None:
    state["players"][actor].setdefault("turn_flags", {})
    state["players"][actor]["turn_flags"].update(
        {
            "supporter_played": False,
            "stadium_played": False,
            "tool_attached": False,
        }
    )


def _turn_flags(state: dict[str, Any], actor: str) -> dict[str, Any]:
    state["players"][actor].setdefault("turn_flags", {})
    return state["players"][actor]["turn_flags"]


def can_play_supporter(state: dict[str, Any], actor: str) -> tuple[bool, str]:
    player = state["players"][actor]
    flags = _turn_flags(state, actor)
    if flags.get("supporter_played"):
        return False, "Supporter already played this turn."
    if int(player.get("hand_supporters", 0)) <= 0:
        return False, "No Supporter cards available in hand."
    return True, "Supporter can be played."


def play_supporter(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    allowed, reason = can_play_supporter(state, actor)
    if not allowed:
        return False, [f"{actor} could not play Supporter: {reason}"]

    player = state["players"][actor]
    player["hand_supporters"] = max(0, int(player.get("hand_supporters", 0)) - 1)
    player["hand_size"] = int(player.get("hand_size", 0)) + 2
    _turn_flags(state, actor)["supporter_played"] = True
    return True, [f"{actor} played a Supporter and drew 2 cards."]


def can_play_stadium(state: dict[str, Any], actor: str) -> tuple[bool, str]:
    player = state["players"][actor]
    flags = _turn_flags(state, actor)
    if flags.get("stadium_played"):
        return False, "Stadium already played this turn."
    if int(player.get("hand_stadiums", 0)) <= 0:
        return False, "No Stadium cards available in hand."
    return True, "Stadium can be played."


def play_stadium(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    allowed, reason = can_play_stadium(state, actor)
    if not allowed:
        return False, [f"{actor} could not play Stadium: {reason}"]

    player = state["players"][actor]
    player["hand_stadiums"] = max(0, int(player.get("hand_stadiums", 0)) - 1)
    state.setdefault("board", {})["stadium"] = f"{actor}-stadium"
    _turn_flags(state, actor)["stadium_played"] = True
    return True, [f"{actor} played a Stadium card."]


def can_attach_tool(state: dict[str, Any], actor: str) -> tuple[bool, str]:
    player = state["players"][actor]
    active = player["active"]
    flags = _turn_flags(state, actor)
    if flags.get("tool_attached"):
        return False, "Tool already attached this turn."
    if int(player.get("hand_tools", 0)) <= 0:
        return False, "No Tool cards available in hand."
    if active.get("tool_attached"):
        return False, "Active Pokémon already has a Tool attached."
    return True, "Tool can be attached."


def attach_tool(state: dict[str, Any], actor: str) -> tuple[bool, list[str]]:
    allowed, reason = can_attach_tool(state, actor)
    if not allowed:
        return False, [f"{actor} could not attach Tool: {reason}"]

    player = state["players"][actor]
    active = player["active"]
    player["hand_tools"] = max(0, int(player.get("hand_tools", 0)) - 1)
    active["tool_attached"] = True
    _turn_flags(state, actor)["tool_attached"] = True
    return True, [f"{actor} attached a Tool to their Active Pokémon."]

