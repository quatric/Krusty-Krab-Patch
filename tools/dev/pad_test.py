"""Dev-time: GameCube pad on port 1 with no Wii Remote at all -> what does the game's own device layer see?"""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dolphin import Dolphin, ROOT
from boot_test import show, PAD, KBUF

def sample(d, chan=0):
    k = d.read(KBUF + chan * 1360, 0x88)
    f = struct.unpack('>34f', k); w = struct.unpack('>34I', k)
    return dict(hold=w[0], trig=w[1], rel=w[2], ty=w[0x5C // 4], sx=f[0x60 // 4], sy=f[0x64 // 4], acc=f[3:6], accv=f[6], faccv=f[0x74 // 4])

if __name__ == '__main__':
    with Dolphin(os.path.join(ROOT, 'dumps/fst/RQ4E78/sys/main.dol'), game_id='RQ4E78') as d:
        time.sleep(25)
        print('--- idle'); show(d)
        g = d.gc(1)
        g.press('A'); g.press('Z'); g.stick('MAIN', 0, 1)
        time.sleep(1.5)
        print('--- A+Z+stick up'); show(d); print(sample(d))
        g.clear(); g.press('START'); g.press('L'); g.press('R')
        time.sleep(1.5)
        print('--- L+R+Start'); show(d); print(sample(d))
