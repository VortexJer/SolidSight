"""A tiny 2-layer grid autorouter for the examples.

Not production EDA — just enough to route a demo board to zero findings
so the "after" side of a before/after is real. Lee/BFS maze routing on a
0.5 mm grid, two copper layers, vias to change layer, and a clearance
halo around every net so nothing it lays down shorts to anything else.

Emits KiCad `segment` and `via` lines. Deterministic.
"""

from __future__ import annotations

import heapq
import math

GRID = 0.4           # mm per cell
CLEAR = 0.3          # clearance halo, mm
VIA_COST = 12        # discourage layer changes


class Router:
    def __init__(self, w: float, h: float, margin: float = 1.5):
        self.nx = int(w / GRID) + 1
        self.ny = int(h / GRID) + 1
        self.margin = margin
        self.w, self.h = w, h
        # occ[layer][y][x] = net id occupying the cell, or 0 = free
        self.occ = [[[0] * self.nx for _ in range(self.ny)]
                    for _ in range(2)]
        self.segments: list[str] = []
        self.vias: list[str] = []

    def _cell(self, x, y):
        return (int(round(x / GRID)), int(round(y / GRID)))

    def _in(self, cx, cy):
        return 0 <= cx < self.nx and 0 <= cy < self.ny

    def _stamp(self, cx, cy, layer, net, radius):
        r = int(math.ceil((radius + CLEAR) / GRID))
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = cx + dx, cy + dy
                if self._in(x, y):
                    self.occ[layer][y][x] = net

    def block_pad(self, x, y, w, h, net, through=False):
        cx, cy = self._cell(x, y)
        r = max(w, h) / 2
        layers = (0, 1) if through else (0,)
        for L in layers:
            self._stamp(cx, cy, L, net, r)

    def block_edge(self):
        # a border ring is blocked to all nets (id -1) so routes stay in
        for L in (0, 1):
            m = int(self.margin / GRID)
            for y in range(self.ny):
                for x in range(self.nx):
                    if (x < m or x >= self.nx - m or y < m
                            or y >= self.ny - m):
                        self.occ[L][y][x] = -1

    def route(self, net: int, pads: list[tuple[float, float, bool]],
              width: float) -> bool:
        """Connect all pads of one net. pads: (x, y, through). Returns
        True if every pad joined the net."""
        if len(pads) < 2:
            return True
        # seed the net with its first pad's cell on its layer(s)
        placed = set()
        first = pads[0]
        c = self._cell(first[0], first[1])
        placed.add((0, c[0], c[1]))
        if first[2]:
            placed.add((1, c[0], c[1]))
        for pad in pads[1:]:
            tc = self._cell(pad[0], pad[1])
            targets = {(0, tc[0], tc[1])}
            if pad[2]:
                targets.add((1, tc[0], tc[1]))
            path = self._maze(net, placed, targets)
            if path is None:
                return False
            self._lay(net, path, width)
            for (L, x, y) in path:
                placed.add((L, x, y))
        return True

    def _maze(self, net, sources, targets):
        # Dijkstra over (layer, x, y); free cell = 0 or this net; target
        # cells always enterable
        dist = {}
        pq = []
        for s in sources:
            dist[s] = 0
            heapq.heappush(pq, (0, s))
        while pq:
            d, (L, x, y) = heapq.heappop(pq)
            if d > dist.get((L, x, y), 1e18):
                continue
            if (L, x, y) in targets:
                return self._trace(dist, (L, x, y), sources)
            # in-plane neighbours
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx_, ny_ = x + dx, y + dy
                if not self._in(nx_, ny_):
                    continue
                occ = self.occ[L][ny_][nx_]
                if occ not in (0, net) and (L, nx_, ny_) not in targets:
                    continue
                nd = d + 1
                if nd < dist.get((L, nx_, ny_), 1e18):
                    dist[(L, nx_, ny_)] = nd
                    dist[("p", L, nx_, ny_)] = (L, x, y)
                    heapq.heappush(pq, (nd, (L, nx_, ny_)))
            # layer change (via)
            oL = 1 - L
            occ = self.occ[oL][y][x]
            if occ in (0, net) or (oL, x, y) in targets:
                nd = d + VIA_COST
                if nd < dist.get((oL, x, y), 1e18):
                    dist[(oL, x, y)] = nd
                    dist[("p", oL, x, y)] = (L, x, y)
                    heapq.heappush(pq, (nd, (oL, x, y)))
        return None

    def _trace(self, dist, end, sources):
        path = [end]
        cur = end
        while cur not in sources:
            L, x, y = cur
            prev = dist.get(("p", L, x, y))
            if prev is None:
                break
            path.append(prev)
            cur = prev
        path.reverse()
        return path

    def _lay(self, net, path, width):
        # mark occupancy and emit geometry, collapsing straight runs
        for (L, x, y) in path:
            self._stamp(x, y, L, net, width / 2)
        # split into per-layer polylines, insert vias at layer changes
        i = 0
        while i < len(path) - 1:
            (L, x, y) = path[i]
            (L2, x2, y2) = path[i + 1]
            if L2 != L:                       # via
                self.vias.append(
                    f'  (via (at {x * GRID:.3f} {y * GRID:.3f}) '
                    f'(size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") '
                    f'(net {net}))')
                i += 1
                continue
            # extend a straight run on this layer
            j = i + 1
            dx = x2 - x
            dy = y2 - y
            while j + 1 < len(path):
                (Ln, xn, yn) = path[j]
                (Ln2, xn2, yn2) = path[j + 1]
                if Ln2 != Ln:
                    break
                if (xn2 - xn, yn2 - yn) != (dx, dy):
                    break
                j += 1
            (Le, xe, ye) = path[j]
            layer = "F.Cu" if L == 0 else "B.Cu"
            self.segments.append(
                f'  (segment (start {x * GRID:.3f} {y * GRID:.3f}) '
                f'(end {xe * GRID:.3f} {ye * GRID:.3f}) (width {width}) '
                f'(layer "{layer}") (net {net}))')
            i = j

    def emit(self) -> list[str]:
        return self.segments + self.vias
