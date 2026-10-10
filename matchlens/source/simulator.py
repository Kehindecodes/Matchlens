"""Seeded match simulator: one plausible football match from a seed."""

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy

from matchlens.config.settings import settings
from matchlens.models import (
    Action,
    BodyPart,
    Event,
    Frame,
    Match,
    Outcome,
    Phase,
    PlayerPosition,
    Team,
)
from matchlens.source.archetypes import COMEBACK, ArchetypeParams, interpolate
from matchlens.source.squads import PITCH_LENGTH_M, PITCH_WIDTH_M, Slot, build_squads
from matchlens.source.stream import MatchSetup, StreamItem

# An opponent this close to the actor at execution means the action was under pressure.
PRESSING_DISTANCE_M = 3.0

HALF_L = PITCH_LENGTH_M / 2
HALF_W = PITCH_WIDTH_M / 2
GOAL_HALF_W = 3.66
KICKOFF_AT = datetime(2026, 10, 24, 15, 0, tzinfo=UTC)  # notional; fixed so it cannot vary
MAX_SPEED_MS = 9.5
# Events inside one tick are spread over the first half of the interval, never at offset zero, so
# no event shares a clock with a frame and a frame always shows the state before its events.
EVENT_SLOTS = 6


@dataclass
class _Side:
    idx: int  # 0 home, 1 away
    team: Team
    ids: list[str]
    slots: list[Slot]
    bench: list[tuple[str, str]]
    pos: numpy.ndarray  # (n, 2), in this side's own frame: it attacks towards +x
    speed: numpy.ndarray
    line: float = 30.0  # defensive line, metres from own goal
    line_ou: float = 0.0
    yellow: set[str] = field(default_factory=set)  # membership only, never iterated
    # Derived from `slots` by `refresh`, which runs on construction and after any removal.
    depth: numpy.ndarray = field(init=False, repr=False)
    slot_y: numpy.ndarray = field(init=False, repr=False)
    outfield_mask: numpy.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.depth = numpy.array([s.depth for s in self.slots])
        self.slot_y = numpy.array([s.y for s in self.slots])
        self.outfield_mask = numpy.array([s.role in ("MF", "FW") for s in self.slots])

    def remove(self, i: int) -> None:
        for lst in (self.ids, self.slots):
            del lst[i]
        self.pos = numpy.delete(self.pos, i, axis=0)
        self.speed = numpy.delete(self.speed, i)
        self.refresh()


@dataclass
class _Flight:
    t0: int
    t1: int
    start: numpy.ndarray  # global
    end: numpy.ndarray
    height: float = 0.0
    carry: bool = False  # the carrier travels with the ball
    runner: tuple[int, int] | None = None  # (side, player) heading to meet the ball


@dataclass
class _Restart:
    kind: str  # kickoff | throw_in | goal_kick | corner | free_kick
    side: int
    spot: numpy.ndarray  # global
    taker: int


@dataclass
class _Plan:
    side: int
    clock_ms: int
    roles: tuple[str, ...] = ()
    done: bool = False


def _r2(v: float) -> float:
    return round(float(v), 2)


class _Engine:
    def __init__(self, seed: int, archetype: ArchetypeParams, hz: int, rng: numpy.random.Generator):
        if hz <= 0 or 1000 % hz:
            raise ValueError("frame_rate_hz must divide 1000 so frames land on whole milliseconds")
        self.rng = rng
        self.hz = hz
        self.dt = 1.0 / hz
        self.interval = 1000 // hz
        self.archetype = archetype

        match_id = f"m-{seed}"
        home_dir = 1 if rng.random() < 0.5 else -1
        home, away = build_squads(rng, match_id, home_dir)
        self.setup = MatchSetup(
            match=Match(
                match_id=match_id,
                pitch_length_m=PITCH_LENGTH_M,
                pitch_width_m=PITCH_WIDTH_M,
                kickoff_at=KICKOFF_AT,
                archetype_id=archetype.archetype_id,
                seed=seed,
                teams=(home.team, away.team),
            ),
            players=home.players + away.players,
        )
        self.sides = [self._make_side(i, sq) for i, sq in enumerate((home, away))]
        self.match_id = match_id

        added1, added2 = rng.uniform(60, 150), rng.uniform(180, 270)
        self.period_ticks = {1: self._ticks(45 * 60 + added1), 2: self._ticks(45 * 60 + added2)}

        def idx(side: str) -> int:
            return 0 if side == "home" else 1

        def when(minute: float, jitter: float) -> int:
            return int((minute + rng.uniform(-jitter, jitter)) * 60_000)

        self.goals = [_Plan(idx(g.side), when(g.minute, 2.0)) for g in archetype.goals]
        self.subs = [_Plan(idx(s.side), when(s.minute, 0.0), s.roles) for s in archetype.subs]
        self.reds = [_Plan(idx(r.side), when(r.minute, 0.0)) for r in archetype.red_cards]

        # slow state
        self.m = 0.0
        self.m_ou = 0.0
        self.press = [0.5, 0.5]
        self.press_ou = [0.0, 0.0]

        # play state
        self.tick = 0
        self.period = 1
        self.phase = Phase.SET_PIECE
        self.timer = 0
        self.restart: _Restart | None = None
        self.ball = numpy.zeros(2)
        self.ball_z = 0.0
        self.ball_speed = 0.0
        self.holder: tuple[int, int] | None = None
        self.poss = 0
        self.flight: _Flight | None = None
        self.due_tick = 0
        self.due_fn: Callable[[], None] | None = None
        self.header_chance = False
        self.fresh = False

        # output
        self.seq = 0
        self.frame_seq = 0
        self.n_events = 0
        self.slot = 0
        self.out: list[Event] = []

    # --- construction helpers ---------------------------------------------------------------

    def _make_side(self, idx: int, squad) -> _Side:
        n = len(squad.slots)
        return _Side(
            idx=idx,
            team=squad.team,
            ids=list(squad.starters),
            slots=list(squad.slots),
            bench=list(squad.bench),
            pos=numpy.zeros((n, 2)),
            speed=numpy.zeros(n),
        )

    def _ticks(self, seconds: float) -> int:
        return max(1, round(seconds * self.hz))

    # --- geometry ---------------------------------------------------------------------------

    def _dir(self, s: _Side) -> int:
        return s.team.attack_direction(self.period)

    def _mom(self, s: _Side) -> float:
        return self.m if s.idx == 0 else -self.m

    def _clock(self) -> int:
        return self.tick * self.interval

    def _opp_in(self, s: _Side) -> numpy.ndarray:
        """The opposing players, expressed in `s`'s own frame."""
        o = self.sides[1 - s.idx]
        return o.pos * (self._dir(o) * self._dir(s))

    def _nearest_opp(self, s: _Side, xy: numpy.ndarray, *, with_keeper: bool = False) -> int:
        pts = self._opp_in(s)
        d = numpy.hypot(pts[:, 0] - xy[0], pts[:, 1] - xy[1])
        if not with_keeper:
            d[0] = numpy.inf
        return int(numpy.argmin(d))

    def _pressured(self, s: _Side, xy: numpy.ndarray) -> bool:
        pts = self._opp_in(s)
        return bool(
            numpy.min(numpy.hypot(pts[:, 0] - xy[0], pts[:, 1] - xy[1])) < PRESSING_DISTANCE_M
        )

    def _to_g(self, s: _Side, xy) -> numpy.ndarray:
        return numpy.asarray(xy, dtype=float) * self._dir(s)

    @staticmethod
    def _clip_pitch(xy, margin: float = 1.0) -> numpy.ndarray:
        return numpy.array(
            [
                numpy.clip(xy[0], -HALF_L + margin, HALF_L - margin),
                numpy.clip(xy[1], -HALF_W + margin, HALF_W - margin),
            ]
        )

    # --- main loop --------------------------------------------------------------------------

    def run(self) -> Iterator[StreamItem]:
        yield self.setup
        for period in (1, 2):
            n = self.period_ticks[period]
            self._start_period(period)
            for k in range(n):
                self._begin_tick()
                yield self._frame()
                if k == 0:
                    self._emit(Action.PERIOD_START, None, None)
                self._step()
                if k == n - 1:
                    self._emit(Action.PERIOD_END, None, None)
                yield from self._flush()
                self.tick += 1

    def _start_period(self, period: int) -> None:
        self.period = period
        self.ball = numpy.zeros(2)
        self.ball_z = 0.0
        self.ball_speed = 0.0
        self.flight = None
        self.due_fn = None
        self.holder = None
        self.header_chance = False
        kicking = self.sides[0 if period == 1 else 1]
        self.poss = kicking.idx
        self._update_slow_state()
        for s in self.sides:
            s.line = 30.0
            s.pos = self._targets(s)
            s.speed = numpy.zeros(len(s.ids))
        taker = self._pick_taker(kicking, numpy.zeros(2), "kickoff")
        kicking.pos[taker] = (0.0, 0.0)
        self.restart = _Restart("kickoff", kicking.idx, numpy.zeros(2), taker)
        self.holder = (kicking.idx, taker)
        self.phase = Phase.SET_PIECE
        self.timer = self._ticks(2.0)
        self.fresh = True

    def _begin_tick(self) -> None:
        self.slot = 0
        if self.fresh:  # the first tick of a period: positions were set by `_start_period`
            self.fresh = False
            self._update_ball()
            return
        self._update_slow_state()
        self._update_ball()
        self._move_players()

    def _step(self) -> None:
        if self.phase is Phase.STOPPED:
            self.timer -= 1
            if self.timer <= 0:
                self._begin_set_piece()
        elif self.phase is Phase.SET_PIECE:
            self.timer -= 1
            if self.timer <= 0:
                self._take_restart()
        else:
            for _ in range(8):
                if self.due_fn is None or self.tick < self.due_tick:
                    break
                fn, self.due_fn = self.due_fn, None
                fn()
                if self.phase is not Phase.IN_PLAY:
                    break
            if self.phase is Phase.IN_PLAY and self.due_fn is None:
                raise RuntimeError("play is live but nothing is scheduled")

    def _schedule(self, tick: int, fn: Callable[[], None]) -> None:
        self.due_tick = tick
        self.due_fn = fn

    # --- slow variables ---------------------------------------------------------------------

    def _update_slow_state(self) -> None:
        rng, dt = self.rng, self.dt
        minute = self._clock() / 60_000

        def ou(x: float, tau: float, sigma: float) -> float:
            a = math.exp(-dt / tau)
            return x * a + sigma * math.sqrt(1 - a * a) * rng.normal()

        self.m_ou = ou(self.m_ou, 90.0, 0.12)
        self.m = float(numpy.clip(interpolate(self.archetype.momentum, minute) + self.m_ou, -1, 1))
        schedules = (self.archetype.home_press, self.archetype.away_press)
        for i, s in enumerate(self.sides):
            self.press_ou[i] = ou(self.press_ou[i], 60.0, 0.06)
            self.press[i] = float(
                numpy.clip(interpolate(schedules[i], minute) + self.press_ou[i], 0.05, 0.95)
            )
            s.line_ou = ou(s.line_ou, 120.0, 1.5)

    # --- ball and players -------------------------------------------------------------------

    def _update_ball(self) -> None:
        f = self.flight
        if f is not None:
            u = min(1.0, (self.tick - f.t0) / (f.t1 - f.t0))
            new = f.start + u * (f.end - f.start)
            self.ball_speed = min(float(numpy.hypot(*(new - self.ball))) / self.dt, 40.0)
            self.ball_z = f.height * 4 * u * (1 - u)
            self.ball = new
        elif self.holder is not None:
            s = self.sides[self.holder[0]]
            self.ball = self._to_g(s, s.pos[self.holder[1]])
            self.ball_speed = 0.0
            self.ball_z = 0.0
        else:
            self.ball_speed = 0.0
            self.ball_z = 0.0

    def _targets(self, s: _Side) -> numpy.ndarray:
        d = self._dir(s)
        ball_n = self.ball * d
        m = self._mom(s)
        press = self.press[s.idx]
        has_ball = self.poss == s.idx
        line = 30.0 + 6.0 * m + 4.0 * (press - 0.5) + s.line_ou + 0.12 * ball_n[0]
        s.line += 0.35 * (float(numpy.clip(line, 20.0, 46.0)) - s.line)
        line_x = -HALF_L + s.line
        length = 27.0 + 7.0 * has_ball - 5.0 * press * (not has_ball)
        tx = line_x + s.depth * length
        if has_ball and self.phase is Phase.IN_PLAY:  # attackers push on ahead of the ball
            ahead = numpy.minimum(ball_n[0] + 12.0 * (s.depth - 0.3), HALF_L - 4.0)
            tx = numpy.where(s.depth > 0.3, numpy.maximum(tx, ahead), tx)
        tx[0] = -HALF_L + 4.0 + 0.15 * (s.line - 30.0)
        width = 0.8 + 0.2 * has_ball - 0.15 * press * (not has_ball)
        ty = numpy.clip(s.slot_y * width + 0.25 * ball_n[1], -30.0, 30.0)
        tgt = numpy.stack([numpy.clip(tx, -HALF_L + 1, HALF_L - 1), ty], axis=1)

        if self.phase is Phase.IN_PLAY and not has_ball:
            k = 1 + (press > 0.5) + (press > 0.8)
            idxs = numpy.flatnonzero(s.outfield_mask)
            dist = numpy.hypot(*(s.pos[idxs] - ball_n).T)
            toward = numpy.array([-HALF_L, 0.0]) - ball_n
            toward /= max(float(numpy.hypot(*toward)), 1e-6)
            pd = max(6.5 - 5.0 * press, 1.5)
            for rank, j in enumerate(idxs[numpy.argsort(dist)[:k]]):
                lateral = numpy.array([0.0, 3.5 * rank * (1 if rank % 2 else -1)])
                tgt[j] = ball_n + toward * pd + lateral
        if self.restart is not None and self.phase is not Phase.IN_PLAY:
            r = self.restart
            if r.side == s.idx and r.taker < len(s.ids):
                tgt[r.taker] = r.spot * d
        return tgt

    def _move_players(self) -> None:
        in_play = self.phase is Phase.IN_PLAY
        f = self.flight
        for s in self.sides:
            d = self._dir(s)
            tgt = self._targets(s)
            vmax = numpy.full(len(s.ids), 6.0 if in_play else 2.4)
            if f is not None and f.runner is not None and f.runner[0] == s.idx:
                tgt[f.runner[1]] = f.end * d
                vmax[f.runner[1]] = 8.5
            step = tgt - s.pos
            dist = numpy.hypot(step[:, 0], step[:, 1])
            step *= numpy.minimum(1.0, vmax * self.dt / numpy.maximum(dist, 1e-9))[:, None]
            step += self.rng.normal(0.0, 0.12, step.shape)
            new = s.pos + step
            if self.holder is not None and self.holder[0] == s.idx:
                new[self.holder[1]] = self.ball * d
            new = numpy.stack(
                [numpy.clip(new[:, 0], -HALF_L, HALF_L), numpy.clip(new[:, 1], -HALF_W, HALF_W)],
                axis=1,
            )
            moved = numpy.hypot(*(new - s.pos).T) / self.dt
            s.speed = numpy.minimum(moved, MAX_SPEED_MS)
            s.pos = new

    def _frame(self) -> Frame:
        players = []
        for s in self.sides:
            g = s.pos * self._dir(s)
            for i, pid in enumerate(s.ids):
                players.append(PlayerPosition(pid, _r2(g[i, 0]), _r2(g[i, 1]), _r2(s.speed[i])))
        carrier = None
        if self.holder is not None and (self.flight is None or self.flight.carry):
            carrier = self.sides[self.holder[0]].ids[self.holder[1]]
        frame = Frame(
            seq=self.seq,
            clock_ms=self._clock(),
            period=self.period,
            phase=self.phase,
            ball_x=_r2(self.ball[0]),
            ball_y=_r2(self.ball[1]),
            ball_z=_r2(self.ball_z),
            ball_speed=_r2(self.ball_speed),
            carrier=carrier,
            players=tuple(players),
        )
        self.frame_seq = self.seq
        self.seq += 1
        return frame

    # --- events -----------------------------------------------------------------------------

    def _next_offset(self) -> int:
        step = max(self.interval // 2 // (EVENT_SLOTS + 1), 1)
        offset = (min(self.slot, EVENT_SLOTS - 1) + 1) * step
        self.slot += 1
        return offset

    def _emit(
        self,
        action: Action,
        side: _Side | None,
        player: str | None,
        *,
        start=None,
        end=None,
        outcome: Outcome | None = None,
        receiver: str | None = None,
        body: BodyPart | None = None,
        pressure: bool | None = None,
        player_on: str | None = None,
        offset: int | None = None,
    ) -> None:
        if offset is None:
            offset = self._next_offset()
        self.n_events += 1
        self.out.append(
            Event(
                event_id=f"{self.match_id}-e{self.n_events}",
                seq=self.seq,
                clock_ms=self._clock() + offset,
                period=self.period,
                action=action,
                player=player,
                team=side.team.team_id if side is not None else None,
                start_x=None if start is None else _r2(start[0]),
                start_y=None if start is None else _r2(start[1]),
                end_x=None if end is None else _r2(end[0]),
                end_y=None if end is None else _r2(end[1]),
                outcome=outcome,
                receiver=receiver,
                player_on=player_on,
                under_pressure=pressure,
                body_part=body,
                frame_ref=self.frame_seq,
            )
        )
        self.seq += 1

    def _flush(self) -> Iterator[Event]:
        out, self.out = self.out, []
        yield from out

    def _foot(self) -> BodyPart:
        return BodyPart.LEFT_FOOT if self.rng.random() < 0.3 else BodyPart.RIGHT_FOOT

    # --- scripted plans ---------------------------------------------------------------------

    def _active_goal(self) -> _Plan | None:
        return next((g for g in self.goals if not g.done and self._clock() >= g.clock_ms), None)

    def _plan_for(self, s: _Side) -> _Plan | None:
        g = self._active_goal()
        return g if g is not None and g.side == s.idx else None

    # --- deciding what the holder does ------------------------------------------------------

    def _hold_ticks(self) -> int:
        seconds = float(self.rng.choice([0.5, 1.0, 2.0, 3.0], p=[0.35, 0.3, 0.25, 0.10]))
        return round(seconds * self.hz)

    def _after_hold(self) -> None:
        self._schedule(self.tick + self._hold_ticks(), self._decide)

    def _decide(self) -> None:
        rng = self.rng
        assert self.holder is not None
        s = self.sides[self.holder[0]]
        h = self.holder[1]
        x, y = s.pos[h]
        m = self._mom(s)
        goal = self._active_goal()
        if goal is not None and goal.side != s.idx:
            self._pass(s, h, force_loss=True)
            return
        finishing = goal is not None
        dg = math.hypot(HALF_L - x, y)
        if finishing:
            if dg < 18.0:
                self._shoot(s, h, goal=goal)
                return
        else:
            if self.header_chance:
                self.header_chance = False
                if rng.random() < 0.55:
                    self._shoot(s, h, header=True)
                    return
            p_shot = 0.0 if dg > 34 else min(0.3, 0.12 * math.exp(-(dg - 7) / 8)) * (1 + 0.4 * m)
            if rng.random() < p_shot:
                self._shoot(s, h)
                return
            up = self._pressured(s, s.pos[h])
            if x < -32.0 and rng.random() < (0.3 if up else 0.03):
                self._clearance(s, h)
                return
        if rng.random() < 0.2:
            self._carry(s, h)
        else:
            self._pass(s, h)

    # --- pass family ------------------------------------------------------------------------

    def _pass(
        self,
        s: _Side,
        h: int,
        *,
        action: Action = Action.PASS,
        dpref: float | None = None,
        fwd: float | None = None,
        box: bool = False,
        force_loss: bool = False,
    ) -> None:
        rng = self.rng
        opp = self.sides[1 - s.idx]
        src = s.pos[h].copy()
        m = self._mom(s)
        finishing = self._plan_for(s) is not None
        press_opp = self.press[opp.idx]
        up = self._pressured(s, src)
        cand = numpy.array(
            [j for j in range(len(s.ids)) if j != h and (j != 0 or src[0] < -30.0)], dtype=int
        )
        pts = s.pos[cand]
        delta = pts - src
        dist = numpy.hypot(delta[:, 0], delta[:, 1])
        if box:
            target = numpy.array([rng.uniform(41, 49), rng.uniform(-8, 8)])
            k = int(numpy.argmin(numpy.hypot(pts[:, 0] - target[0], pts[:, 1] - target[1])))
        else:
            if dpref is None:
                dpref = 13.0 + (12.0 if src[0] < -35 else 0.0)
            fwd = (0.9 + 1.4 * m if fwd is None else fwd) if not finishing else 3.0
            anchor = 4.0 + 22.0 * m
            w = (
                numpy.exp(-(((dist - dpref) / 11.0) ** 2))
                * numpy.exp(fwd * delta[:, 0] / 25.0)
                * (1.0 if finishing else numpy.exp(-0.5 * ((pts[:, 0] - anchor) / 30.0) ** 2))
            )
            opp_pts = self._opp_in(s)
            nearest = numpy.min(
                numpy.hypot(
                    pts[:, None, 0] - opp_pts[None, :, 0], pts[:, None, 1] - opp_pts[None, :, 1]
                ),
                axis=1,
            )
            w *= 0.4 + 0.6 * numpy.minimum(nearest / 6.0, 1.0)
            w[dist < 3.0] = 0.0
            if w.sum() <= 0:
                w = numpy.ones_like(w)
            k = int(rng.choice(len(cand), p=w / w.sum()))
            target = pts[k] + numpy.array([1.5, 0.0])
        j = int(cand[k])
        target = self._clip_pitch(target)
        length = float(numpy.hypot(*(target - src)))
        gain = float(target[0] - src[0])
        duel = length > 26.0 or box
        flight_ticks = self._ticks(length / (20.0 if duel else 16.0))
        height = min(0.12 * length, 9.0) if duel else 0.0

        if finishing:
            ok = True
        elif force_loss:
            ok = False
        else:
            p_ok = (
                0.90
                - 0.10 * up
                - 0.0045 * max(length - 15.0, 0.0)
                - 0.05 * (gain > 12.0)
                - 0.12 * press_opp
                + 0.06 * m
                + (0.03 if action is not Action.PASS else 0.0)
            )
            if box:
                p_ok = 0.45
            ok = bool(rng.random() < float(numpy.clip(p_ok, 0.4, 0.97)))

        body = BodyPart.OTHER if action is Action.THROW_IN else self._foot()
        src_g, tgt_g = self._to_g(s, src), self._to_g(s, target)

        if ok:
            self._emit(
                action,
                s,
                s.ids[h],
                start=src_g,
                end=tgt_g,
                outcome=Outcome.COMPLETE,
                receiver=s.ids[j],
                body=body,
                pressure=up,
            )
            self.flight = _Flight(
                self.tick, self.tick + flight_ticks, src_g, tgt_g, height, runner=(s.idx, j)
            )
            self._schedule(self.tick + flight_ticks, lambda: self._arrive_complete(s, j, duel, box))
            return

        out_chance = 0.0 if force_loss else (0.45 if abs(target[1]) > 20 or length > 30 else 0.22)
        if rng.random() < out_chance:
            over_byline = src[0] > 15.0 and rng.random() < 0.4
            end_n = (
                numpy.array([HALF_L, float(numpy.clip(target[1], -30.0, 30.0))])
                if over_byline
                else numpy.array([target[0], math.copysign(HALF_W, target[1] or 1.0)])
            )
            end_g = self._to_g(s, end_n)
            self._emit(
                action,
                s,
                s.ids[h],
                start=src_g,
                end=end_g,
                outcome=Outcome.OUT_OF_PLAY,
                receiver=s.ids[j],
                body=body,
                pressure=up,
            )
            self.flight = _Flight(self.tick, self.tick + flight_ticks, src_g, end_g, height)
            arrive = self._arrive_byline if over_byline else self._arrive_out
            self._schedule(self.tick + flight_ticks, lambda: arrive(s, end_g))
            return

        frac = float(rng.uniform(0.55, 1.0))
        point = src + frac * (target - src)
        point_g = self._to_g(s, point)
        w_idx = self._nearest_opp(s, point, with_keeper=point[0] > 40.0)
        ticks_i = max(1, round(flight_ticks * frac))
        self._emit(
            action,
            s,
            s.ids[h],
            start=src_g,
            end=point_g,
            outcome=Outcome.INCOMPLETE,
            receiver=s.ids[j],
            body=body,
            pressure=up,
        )
        self.flight = _Flight(
            self.tick, self.tick + ticks_i, src_g, point_g, height, runner=(opp.idx, w_idx)
        )
        self._schedule(self.tick + ticks_i, lambda: self._arrive_intercept(opp, w_idx, duel))

    def _arrive_complete(self, s: _Side, j: int, duel: bool, box: bool) -> None:
        self.flight = None
        self.holder = (s.idx, j)
        self.poss = s.idx
        if duel:
            self._emit(
                Action.AERIAL_DUEL,
                s,
                s.ids[j],
                start=self.ball,
                end=self.ball,
                outcome=Outcome.WON,
                body=BodyPart.HEAD,
                pressure=False,
            )
        if box:
            self.header_chance = True
        self._after_hold()

    def _arrive_intercept(self, opp: _Side, w: int, duel: bool) -> None:
        self.flight = None
        self.holder = (opp.idx, w)
        self.poss = opp.idx
        if duel:
            self._emit(
                Action.AERIAL_DUEL,
                opp,
                opp.ids[w],
                start=self.ball,
                end=self.ball,
                outcome=Outcome.WON,
                body=BodyPart.HEAD,
                pressure=False,
            )
        else:
            self._emit(
                Action.INTERCEPTION,
                opp,
                opp.ids[w],
                start=self.ball,
                end=self.ball,
                outcome=Outcome.WON,
                body=self._foot(),
                pressure=False,
            )
        self._after_hold()

    def _arrive_out(self, s: _Side, point_g: numpy.ndarray) -> None:
        """`s` put the ball out of play; the other side takes the throw-in."""
        self.flight = None
        spot = numpy.array([numpy.clip(point_g[0], -HALF_L + 2, HALF_L - 2), point_g[1]])
        self._begin_stoppage("throw_in", 1 - s.idx, spot, seconds=(11.0, 19.0))

    def _arrive_byline(self, s: _Side, _point_g: numpy.ndarray) -> None:
        """`s` put the ball over the opposition's goal line; their keeper takes the goal kick."""
        self.flight = None
        opp = self.sides[1 - s.idx]
        y = math.copysign(9.0, self.rng.normal())
        self._begin_stoppage(
            "goal_kick", opp.idx, self._to_g(opp, (-47.0, y)), seconds=(14.0, 24.0)
        )

    # --- carry, challenge, foul -------------------------------------------------------------

    def _carry(self, s: _Side, h: int) -> None:
        rng = self.rng
        opp = self.sides[1 - s.idx]
        m = self._mom(s)
        src = s.pos[h].copy()
        finishing = self._plan_for(s) is not None
        length = float(rng.uniform(5.0, 16.0))
        forward = finishing or rng.random() < float(numpy.clip(0.58 + 0.25 * m, 0.2, 0.9))
        angle = float(rng.normal(0.0, 0.6))
        dx = length * math.cos(angle) * (1 if forward else -1)
        dy = length * math.sin(angle)
        if src[0] > 25.0:
            dy -= 0.25 * src[1]
        end = self._clip_pitch(src + numpy.array([dx, dy]))
        ticks = self._ticks(float(numpy.hypot(*(end - src))) / 5.5)
        up = self._pressured(s, src)
        lose = not finishing and rng.random() < float(
            numpy.clip(0.12 + 0.20 * self.press[opp.idx] + 0.04 * up - 0.06 * m, 0.02, 0.4)
        )
        src_g, end_g = self._to_g(s, src), self._to_g(s, end)
        self._emit(
            Action.CARRY,
            s,
            s.ids[h],
            start=src_g,
            end=end_g,
            outcome=Outcome.INCOMPLETE if lose else Outcome.COMPLETE,
            pressure=up,
        )
        self.flight = _Flight(self.tick, self.tick + ticks, src_g, end_g, carry=True)
        self._schedule(self.tick + ticks, lambda: self._arrive_carry(s, h, lose))

    def _arrive_carry(self, s: _Side, h: int, lose: bool) -> None:
        self.flight = None
        if lose:
            self._challenge(s, h)
        else:
            self._after_hold()

    def _challenge(self, s: _Side, h: int) -> None:
        rng = self.rng
        opp = self.sides[1 - s.idx]
        point = s.pos[h].copy()
        point_g = self._to_g(s, point)
        w = self._nearest_opp(s, point)
        red = next(
            (
                r
                for r in self.reds
                if not r.done and r.side == opp.idx and self._clock() >= r.clock_ms
            ),
            None,
        )
        if red is not None or rng.random() < 0.25:
            self._foul(s, opp, w, point_g, red)
            return
        self.holder = (opp.idx, w)
        self.poss = opp.idx
        self._emit(
            Action.TACKLE,
            opp,
            opp.ids[w],
            start=point_g,
            end=point_g,
            outcome=Outcome.WON,
            pressure=False,
        )
        self._after_hold()

    def _foul(
        self, s: _Side, opp: _Side, w: int, point_g: numpy.ndarray, red: _Plan | None
    ) -> None:
        rng = self.rng
        offender = opp.ids[w]
        self.holder = None
        self.flight = None
        self._emit(
            Action.FOUL,
            opp,
            offender,
            start=point_g,
            end=point_g,
            outcome=Outcome.LOST,
            pressure=False,
        )
        extra = 0.0
        if red is not None:
            red.done = True
            self._emit(Action.RED_CARD, opp, offender)
            opp.remove(w)
            extra = 40.0
        elif offender not in opp.yellow and rng.random() < 0.25:
            opp.yellow.add(offender)
            self._emit(Action.YELLOW_CARD, opp, offender)
            extra = 15.0
        self._begin_stoppage("free_kick", s.idx, point_g, seconds=(20.0 + extra, 32.0 + extra))

    # --- clearance and shots ----------------------------------------------------------------

    def _clearance(self, s: _Side, h: int) -> None:
        rng = self.rng
        opp = self.sides[1 - s.idx]
        src = s.pos[h].copy()
        length = float(rng.uniform(25.0, 45.0))
        angle = float(rng.normal(0.0, 0.5))
        end = self._clip_pitch(src + length * numpy.array([math.cos(angle), math.sin(angle)]))
        roll = float(rng.random())
        out = roll < 0.2
        if out:
            end = numpy.array([end[0], math.copysign(HALF_W, end[1] or 1.0)])
        up = self._pressured(s, src)
        ticks = self._ticks(float(numpy.hypot(*(end - src))) / 20.0)
        src_g, end_g = self._to_g(s, src), self._to_g(s, end)
        body = BodyPart.HEAD if rng.random() < 0.3 else self._foot()
        self._emit(
            Action.CLEARANCE,
            s,
            s.ids[h],
            start=src_g,
            end=end_g,
            outcome=Outcome.OUT_OF_PLAY if out else Outcome.COMPLETE,
            body=body,
            pressure=up,
        )
        height = min(0.12 * float(numpy.hypot(*(end - src))), 9.0)
        if out:
            self.flight = _Flight(self.tick, self.tick + ticks, src_g, end_g, height)
            self._schedule(self.tick + ticks, lambda: self._arrive_out(s, end_g))
            return
        winner = s if roll < 0.5 else opp
        w_idx = (
            int(
                numpy.argmin(
                    numpy.where(
                        numpy.arange(len(s.ids)) == 0, numpy.inf, numpy.hypot(*(s.pos - end).T)
                    )
                )
            )
            if winner is s
            else self._nearest_opp(s, end)
        )
        self.flight = _Flight(
            self.tick, self.tick + ticks, src_g, end_g, height, runner=(winner.idx, w_idx)
        )
        if winner is s:
            self._schedule(self.tick + ticks, lambda: self._arrive_complete(s, w_idx, True, False))
        else:
            self._schedule(self.tick + ticks, lambda: self._arrive_intercept(opp, w_idx, True))

    def _shoot(
        self,
        s: _Side,
        h: int,
        *,
        goal: _Plan | None = None,
        header: bool = False,
        action: Action = Action.SHOT,
    ) -> None:
        rng = self.rng
        opp = self.sides[1 - s.idx]
        src = s.pos[h].copy()
        dg = math.hypot(HALF_L - src[0], src[1])
        quality = math.exp(-dg / 11.0) * (
            0.6 + 0.4 * math.cos(math.atan2(abs(src[1]), HALF_L - src[0]))
        )
        up = self._pressured(s, src)
        if goal is not None:
            outcome = Outcome.GOAL
        else:
            p_block = 0.26
            p_off = float(numpy.clip(0.42 - 0.5 * quality, 0.15, 0.42))
            u = rng.random()
            outcome = (
                Outcome.BLOCKED
                if u < p_block
                else Outcome.OFF_TARGET
                if u < p_block + p_off
                else Outcome.SAVED
            )
        if outcome is Outcome.BLOCKED:
            end = src + float(rng.uniform(0.1, 0.3)) * (numpy.array([HALF_L, 0.0]) - src)
        elif outcome is Outcome.OFF_TARGET:
            end = numpy.array(
                [HALF_L, math.copysign(GOAL_HALF_W + 0.4 + rng.exponential(2.0), rng.normal())]
            )
            end[1] = float(numpy.clip(end[1], -12.0, 12.0))
        else:
            end = numpy.array([HALF_L, rng.uniform(-3.0, 3.0)])
        ticks = 1 if outcome is Outcome.BLOCKED else self._ticks(dg / 20.0)
        body = BodyPart.HEAD if header else self._foot()
        src_g, end_g = self._to_g(s, src), self._to_g(s, end)
        self._emit(
            action, s, s.ids[h], start=src_g, end=end_g, outcome=outcome, body=body, pressure=up
        )
        self.holder = None
        self.flight = _Flight(self.tick, self.tick + ticks, src_g, end_g, 0.5)
        self._schedule(self.tick + ticks, lambda: self._arrive_shot(s, opp, outcome, end, goal))

    def _arrive_shot(
        self, s: _Side, opp: _Side, outcome: Outcome, end: numpy.ndarray, goal: _Plan | None
    ) -> None:
        rng = self.rng
        self.flight = None
        here_g = self.ball.copy()
        if outcome is Outcome.GOAL:
            assert goal is not None
            goal.done = True
            self._begin_stoppage("kickoff", opp.idx, numpy.zeros(2), seconds=(40.0, 55.0))
        elif outcome is Outcome.OFF_TARGET:
            side_y = math.copysign(9.0, rng.normal())
            self._begin_stoppage(
                "goal_kick", opp.idx, self._to_g(opp, (-47.0, side_y)), seconds=(14.0, 24.0)
            )
        elif outcome is Outcome.SAVED:
            self._emit(
                Action.SAVE,
                opp,
                opp.ids[0],
                start=here_g,
                end=here_g,
                outcome=Outcome.COMPLETE,
                body=BodyPart.OTHER,
                pressure=False,
            )
            if rng.random() < 0.35:
                spot = self._to_g(s, (HALF_L - 0.5, math.copysign(HALF_W - 0.5, rng.normal())))
                self._begin_stoppage("corner", s.idx, spot, seconds=(14.0, 22.0))
            else:
                self.holder = (opp.idx, 0)
                self.poss = opp.idx
                self._after_hold()
        else:  # blocked
            w = self._nearest_opp(s, here_g * self._dir(s))
            self._emit(
                Action.BLOCK,
                opp,
                opp.ids[w],
                start=here_g,
                end=here_g,
                outcome=Outcome.WON,
                body=BodyPart.OTHER,
                pressure=False,
            )
            if rng.random() < 0.3:
                spot = self._to_g(s, (HALF_L - 0.5, math.copysign(HALF_W - 0.5, rng.normal())))
                self._begin_stoppage("corner", s.idx, spot, seconds=(14.0, 22.0))
            else:
                self.holder = (opp.idx, w)
                self.poss = opp.idx
                self._after_hold()

    # --- stoppages and restarts -------------------------------------------------------------

    def _pick_taker(self, s: _Side, spot_g: numpy.ndarray, kind: str) -> int:
        if kind == "goal_kick":
            return 0
        d = numpy.hypot(*(s.pos - spot_g * self._dir(s)).T)
        d[0] = numpy.inf
        return int(numpy.argmin(d))

    def _begin_stoppage(
        self, kind: str, side_idx: int, spot: numpy.ndarray, *, seconds: tuple[float, float]
    ) -> None:
        self.flight = None
        self.holder = None
        self.due_fn = None
        self.header_chance = False
        self.phase = Phase.STOPPED
        self.timer = self._ticks(float(self.rng.uniform(*seconds)))
        self.poss = side_idx
        side = self.sides[side_idx]
        self._substitutions()
        self.restart = _Restart(
            kind, side_idx, numpy.asarray(spot, dtype=float), self._pick_taker(side, spot, kind)
        )

    def _begin_set_piece(self) -> None:
        r = self.restart
        assert r is not None
        side = self.sides[r.side]
        side.pos[r.taker] = r.spot * self._dir(side)
        self.holder = (r.side, r.taker)
        self.poss = r.side
        self.ball = r.spot.copy()
        self.phase = Phase.SET_PIECE
        self.timer = self._ticks(float(self.rng.uniform(2.0, 4.0 if r.kind == "throw_in" else 6.0)))

    def _take_restart(self) -> None:
        r = self.restart
        assert r is not None
        side = self.sides[r.side]
        self.phase = Phase.IN_PLAY
        self.header_chance = False
        if r.kind == "kickoff":
            self._pass(side, r.taker, fwd=-0.6, dpref=8.0)
        elif r.kind == "throw_in":
            self._pass(side, r.taker, action=Action.THROW_IN, dpref=11.0)
        elif r.kind == "goal_kick":
            self._pass(side, r.taker, action=Action.GOAL_KICK, dpref=36.0)
        elif r.kind == "corner":
            self._pass(side, r.taker, action=Action.CORNER, box=True)
        else:
            x, y = side.pos[r.taker]
            dg = math.hypot(HALF_L - x, y)
            if 16.0 < dg < 30.0 and self.rng.random() < 0.4:
                self._shoot(side, r.taker, action=Action.FREE_KICK)
            else:
                self._pass(side, r.taker, action=Action.FREE_KICK, dpref=20.0)

    # --- substitutions ----------------------------------------------------------------------

    def _substitutions(self) -> None:
        rng = self.rng
        for plan in self.subs:
            if plan.done or self._clock() < plan.clock_ms:
                continue
            plan.done = True
            side = self.sides[plan.side]
            offset = self._next_offset()  # a double change shares one clock
            for role in plan.roles:
                cands = [i for i, sl in enumerate(side.slots) if sl.role == role and i != 0]
                bench = [b for b in side.bench if b[1] == role]
                if not cands or not bench:
                    continue
                i = cands[int(rng.integers(len(cands)))]
                on = bench[0]
                side.bench.remove(on)
                off_id, side.ids[i] = side.ids[i], on[0]
                self._emit(Action.SUBSTITUTION, side, off_id, player_on=on[0], offset=offset)


def simulate(
    seed: int | None = None,
    archetype: ArchetypeParams = COMEBACK,
    *,
    frame_rate_hz: int | None = None,
) -> Iterator[StreamItem]:
    """One match as a stream: the roster first, then frames and events in `seq` order.

    The seed defaults to `settings.match_seed` (the demo match) and the rate to
    `settings.frame_rate_hz`, both read when called.
    """
    seed = settings.match_seed if seed is None else seed
    hz = settings.frame_rate_hz if frame_rate_hz is None else frame_rate_hz
    return _Engine(seed, archetype, hz, numpy.random.default_rng(seed)).run()
