"""Fictional squads: invented names, a few formations, a bench.

Names are assembled from syllables rather than picked from a list of surnames, so none is meant to
match a real player (trademark risk, per DATA-MODEL).
"""

from dataclasses import dataclass

import numpy as np

from matchlens.models import Player, Team

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


@dataclass(frozen=True)
class Slot:
    """One place in a formation. `depth` runs 0 (the defensive line) to 1 (the front line)."""

    role: str  # GK | DF | MF | FW
    depth: float
    y: float  # metres from the centre line, own-attack frame


_BACK_FOUR = (
    Slot("DF", 0.0, -24.0),
    Slot("DF", 0.0, -8.0),
    Slot("DF", 0.0, 8.0),
    Slot("DF", 0.0, 24.0),
)
FORMATIONS: dict[str, tuple[Slot, ...]] = {
    "4-3-3": (
        Slot("GK", 0.0, 0.0), *_BACK_FOUR,
        Slot("MF", 0.45, -13.0), Slot("MF", 0.35, 0.0), Slot("MF", 0.45, 13.0),
        Slot("FW", 0.95, -20.0), Slot("FW", 1.0, 0.0), Slot("FW", 0.95, 20.0),
    ),
    "4-4-2": (
        Slot("GK", 0.0, 0.0), *_BACK_FOUR,
        Slot("MF", 0.5, -24.0), Slot("MF", 0.45, -8.0),
        Slot("MF", 0.45, 8.0), Slot("MF", 0.5, 24.0),
        Slot("FW", 0.95, -6.0), Slot("FW", 0.95, 6.0),
    ),
    "4-2-3-1": (
        Slot("GK", 0.0, 0.0), *_BACK_FOUR,
        Slot("MF", 0.3, -7.0), Slot("MF", 0.3, 7.0),
        Slot("MF", 0.65, -18.0), Slot("MF", 0.7, 0.0), Slot("MF", 0.65, 18.0),
        Slot("FW", 1.0, 0.0),
    ),
}  # fmt: skip
BENCH_ROLES = ("GK", "DF", "DF", "MF", "MF", "FW", "FW")

_FIRST = (
    "Dale", "Marek", "Tomas", "Idris", "Callum", "Joao", "Luka", "Ewan", "Kofi", "Rafe", "Niko",
    "Sami", "Declan", "Matteo", "Jonas", "Arlo", "Teddy", "Yusuf", "Ivor", "Bram", "Cai", "Dario",
    "Elio", "Finn", "Gideon", "Hamza", "Ilan", "Jory", "Kian", "Leif",
)  # fmt: skip
_PREFIX = (
    "Bar", "Cor", "Dal", "Fen", "Gar", "Hal", "Kes", "Lor", "Mar", "Nor", "Ors", "Pel", "Ren",
    "Sav", "Tor", "Vel", "Wen", "Yar", "Zan", "Ash", "Bro", "Cal", "Dru", "Eld", "Fal", "Gor",
)  # fmt: skip
_SUFFIX = (
    "ton", "ley", "wick", "dane", "ford", "mere", "vik", "ssen", "nov", "ric", "bell", "ham",
    "lan", "stow", "hart", "mont", "ner", "dro",
)  # fmt: skip
_PLACES = (
    "Northgate", "Riverside", "Ashbourne", "Kestrel", "Marlow", "Hartley", "Eastvale", "Westmere",
    "Oakhurst", "Stonebridge", "Redfern", "Lakeside",
)  # fmt: skip
_CLUBS = ("United", "Town", "Rovers", "Athletic", "City", "Wanderers")


@dataclass(frozen=True)
class Squad:
    team: Team
    players: tuple[Player, ...]  # the eleven starters in slot order, then the bench
    slots: tuple[Slot, ...]
    bench: tuple[tuple[str, str], ...]  # (player_id, role)

    @property
    def starters(self) -> tuple[str, ...]:
        return tuple(p.player_id for p in self.players[: len(self.slots)])


def _full_name(rng: np.random.Generator, taken: set[str]) -> str:
    while True:
        name = (
            f"{_FIRST[rng.integers(len(_FIRST))]} "
            f"{_PREFIX[rng.integers(len(_PREFIX))]}{_SUFFIX[rng.integers(len(_SUFFIX))]}"
        )
        if name not in taken:
            taken.add(name)
            return name


def build_squads(
    rng: np.random.Generator, match_id: str, home_direction: int
) -> tuple[Squad, Squad]:
    """Home squad, then away. `home_direction` is the way home attack in the first half."""
    places = list(rng.permutation(len(_PLACES))[:2])
    formations = list(FORMATIONS)
    taken: set[str] = set()
    squads = []
    for is_home, place in zip((True, False), places, strict=True):
        side = "home" if is_home else "away"
        team_id = f"{match_id}-{side}"
        name = f"{_PLACES[place]} {_CLUBS[rng.integers(len(_CLUBS))]}"
        formation = formations[rng.integers(len(formations))]
        direction = home_direction if is_home else -home_direction
        team = Team(
            team_id=team_id,
            match_id=match_id,
            name=name,
            short_name=name[:3].upper(),
            formation=formation,
            is_home=is_home,
            attack_direction_by_period={1: direction, 2: -direction},
        )
        slots = FORMATIONS[formation]
        roles = [s.role for s in slots] + list(BENCH_ROLES)
        players = tuple(
            Player(
                player_id=f"{team_id}-p{shirt}",
                team_id=team_id,
                shirt=shirt,
                name=_full_name(rng, taken),
                position=role,
                is_starter=shirt <= len(slots),
            )
            for shirt, role in enumerate(roles, start=1)
        )
        bench = tuple((p.player_id, p.position) for p in players[len(slots) :])
        squads.append(Squad(team, players, slots, bench))
    return squads[0], squads[1]
