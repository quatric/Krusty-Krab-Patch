"""Dev-time: boot the patched game with a GameCube pad and press buttons on a schedule, shooting the screen.

Schedule items are BUTTON@seconds-after-boot; a leading '!' holds the button for 0.2 s (default tap 0.15 s).
"""
import argparse, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dolphin import Dolphin, ROOT

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('region'); ap.add_argument('out'); ap.add_argument('schedule', nargs='?', default='')
    ap.add_argument('--every', type=float, default=10); ap.add_argument('--until', type=float, default=90)
    ap.add_argument('--wii', default=None, help="emulate a Wii Remote with this extension (Nunchuk/Classic) instead of a GC pad")
    a = ap.parse_args()
    sched = []
    for it in filter(None, a.schedule.split(',')):
        b, t = it.split('@'); sched.append((float(t), b))
    sched.sort()
    ext = {1: a.wii} if a.wii else {}
    with Dolphin(os.path.join(ROOT, 'dumps/fst/%s/sys/main.dol' % a.region), game_id=a.region, video='Metal',
                 wii_ext=ext, gc_ports=() if a.wii else (1,)) as d:
        t0 = time.time(); nxt = a.every; i = 0
        pad = d.wii(1) if a.wii else d.gc(1)
        while True:
            now = time.time() - t0
            if now > a.until: break
            while i < len(sched) and sched[i][0] <= now:
                b = sched[i][1]
                if ':' in b:                      # AXIS:x:y -> stick
                    _, x, y = b.split(':'); pad.stick('MAIN', float(x), float(y))
                else:
                    pad.tap(b, 0.15)
                i += 1
            if now >= nxt:
                p = d.shot(os.path.join(ROOT, 'dumps', 'shots', a.out, 't%03d.png' % int(now))); print(int(now), p, flush=True)
                nxt += a.every
            time.sleep(0.2)

if __name__ == '__main__':
    main()
