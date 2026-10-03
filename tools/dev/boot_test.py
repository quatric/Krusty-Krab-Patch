"""Dev-time: boot a game dir in Dolphin and dump the game's own pad state (device type per channel)."""
import os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dolphin import Dolphin, ROOT

PAD = 0x805CDB80          # USA: 4 x 184-byte pad records; +108 device type, +112 active flag, +164 KPAD sample count
KBUF = 0x805CDE60         # USA: 4 x 1360-byte KPADRead buffers

def show(d):
    for c in range(4):
        r = d.read(PAD + c * 184, 184)
        dev, act, cnt = struct.unpack('>I', r[108:112])[0], struct.unpack('>I', r[112:116])[0], struct.unpack('>I', r[164:168])[0]
        k = d.read(KBUF + c * 1360, 0x88)
        hold, = struct.unpack('>I', k[0:4])
        print('chan%d dev=%d active=%d kpad_count=%d hold=%04X ktype=%d' % (c, dev, act, cnt, hold, struct.unpack('>i', k[0x5C:0x60])[0]))

if __name__ == '__main__':
    ext = {1: sys.argv[1]} if len(sys.argv) > 1 and sys.argv[1] != 'none' else {}
    with Dolphin(os.path.join(ROOT, 'dumps/fst/RQ4E78/sys/main.dol'), game_id='RQ4E78', wii_ext=ext) as d:
        for t in (20, 40, 60):
            time.sleep(20)
            print('t=%d' % t); show(d)
