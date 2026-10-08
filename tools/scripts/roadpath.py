"""Find the road path between two points through Skyrim's road pieces and place checkpoints along it.

usage: python -I roadpath.py <roads.json> <x0,y0> <x1,y1> <spacing units> <out.json> <out.png>
Road pieces closer than LINK units are linked; Dijkstra gives the path; checkpoints are spaced along it.
"""
import heapq
import json
import math
import sys

LINK = 1300.0


def main():
    roads = json.load(open(sys.argv[1]))["roads"]
    a = tuple(map(float, sys.argv[2].split(","))); z = tuple(map(float, sys.argv[3].split(",")))
    spacing, out_json, out_png = float(sys.argv[4]), sys.argv[5], sys.argv[6]
    pts = [r["pos"] for r in roads]
    d2 = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])
    start = min(range(len(pts)), key=lambda i: d2(pts[i], a))
    goal = min(range(len(pts)), key=lambda i: d2(pts[i], z))
    dist, prev, heap = {start: 0.0}, {}, [(0.0, start)]
    while heap:
        d, i = heapq.heappop(heap)
        if i == goal:
            break
        if d > dist.get(i, 1e18):
            continue
        for j, q in enumerate(pts):
            w = d2(pts[i], q)
            if 0 < w < LINK and d + w < dist.get(j, 1e18):
                dist[j] = d + w; prev[j] = i; heapq.heappush(heap, (d + w, j))
    if goal not in dist:
        raise SystemExit("no connected road path; raise LINK")
    path, i = [goal], goal
    while i != start:
        i = prev[i]; path.append(i)
    path.reverse()
    poly = [pts[i] for i in path]
    length = sum(d2(poly[k], poly[k + 1]) for k in range(len(poly) - 1))
    # checkpoints every `spacing` units along the path (outbound), plus the end (turn marker)
    cps, acc, nxt = [poly[0]], 0.0, spacing
    for k in range(len(poly) - 1):
        seg = d2(poly[k], poly[k + 1])
        while acc + seg >= nxt:
            t = (nxt - acc) / seg
            cps.append([poly[k][c] + t * (poly[k + 1][c] - poly[k][c]) for c in range(3)])
            nxt += spacing
        acc += seg
    if d2(cps[-1], poly[-1]) > spacing * 0.4:
        cps.append(poly[-1])
    out = []
    for n, p in enumerate(cps):
        nxt_p = cps[min(n + 1, len(cps) - 1)] if n < len(cps) - 1 else cps[n - 1]
        heading = math.atan2(nxt_p[0] - p[0], nxt_p[1] - p[1])  # Skyrim rotZ: 0 = +Y (north), clockwise
        ref = roads[path[min(range(len(path)), key=lambda k: d2(pts[path[k]], p))]]
        out.append(dict(order=n, pos=[round(v, 1) for v in p], heading=round(heading % (2 * math.pi), 4),
                        cell=ref["cell"], cellId=ref["cellId"], nearRoad=ref["refId"]))
    json.dump(dict(length_units=round(length, 1), length_m=round(length * 0.0142875, 1),
                   pieces=len(path), checkpoints=out), open(out_json, "w"), indent=1)
    print(f"path: {len(path)} road pieces, {length:.0f} units = {length * 0.0142875:.0f} m one way; {len(out)} checkpoints")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 10), dpi=90)
    ax.plot([p[0] for p in pts], [p[1] for p in pts], "s", ms=2, color="lightgray")
    ax.plot([p[0] for p in poly], [p[1] for p in poly], "-", color="saddlebrown")
    for c in out:
        ax.plot(c["pos"][0], c["pos"][1], "o", color="crimson"); ax.annotate(str(c["order"]), c["pos"][:2], fontsize=9)
    ax.set_aspect("equal"); ax.set_title(f"Crossroads -> Riverwood: {length * 0.0142875:.0f} m one way")
    fig.savefig(out_png, bbox_inches="tight")


if __name__ == "__main__":
    main()
