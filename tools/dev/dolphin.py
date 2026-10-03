"""Dev-time Dolphin harness: a private user folder, scripted pad/remote input, memory access over GDB.

    from dolphin import Dolphin
    with Dolphin('dumps/fst/R4QE01', gecko=open('src/cc/R4QE01.txt').read()) as d:
        d.wait_boot(60)
        d.gc(1).press('A'); print(d.read(0x805beb18, 16).hex())

Needs a stock Dolphin (macOS app).  The harness never touches your own Dolphin configuration:
everything lives in dumps/dolphin-user.  Controllers are Dolphin "Pipe" devices (named pipes in
<user>/Pipes), so no physical input is needed:  gc(n) is GameCube port n, wii(n) is Wii Remote n.
"""
import os
import shutil
import socket
import subprocess
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
USER = os.path.join(ROOT, 'dumps', 'dolphin-user')
APP = os.environ.get('DOLPHIN_APP', '/Applications/Dolphin.app/Contents/MacOS/Dolphin')
GDB_PORT = int(os.environ.get('KK_GDB_PORT', 2263))   # not 2160: other projects' Dolphins may be running

GC_MAP = '''[GCPad%(n)d]
Device = Pipe/0/gc%(n)d
Buttons/A = `Button A`
Buttons/B = `Button B`
Buttons/X = `Button X`
Buttons/Y = `Button Y`
Buttons/Z = `Button Z`
Buttons/Start = `Button START`
Main Stick/Up = `Axis MAIN Y +`
Main Stick/Down = `Axis MAIN Y -`
Main Stick/Left = `Axis MAIN X -`
Main Stick/Right = `Axis MAIN X +`
C-Stick/Up = `Axis C Y +`
C-Stick/Down = `Axis C Y -`
C-Stick/Left = `Axis C X -`
C-Stick/Right = `Axis C X +`
Triggers/L = `Button L`
Triggers/R = `Button R`
D-Pad/Up = `Button D_UP`
D-Pad/Down = `Button D_DOWN`
D-Pad/Left = `Button D_LEFT`
D-Pad/Right = `Button D_RIGHT`
'''

# an emulated Wii Remote driven through the same kind of pipe; `ext` is None, 'Nunchuk' or 'Classic'
WII_MAP = '''[Wiimote%(n)d]
Source = 1
Device = Pipe/0/wm%(n)d
Extension = %(ext)s
Buttons/A = `Button A`
Buttons/B = `Button B`
Buttons/1 = `Button X`
Buttons/2 = `Button Y`
Buttons/- = `Button L`
Buttons/+ = `Button R`
Buttons/Home = `Button START`
D-Pad/Up = `Button D_UP`
D-Pad/Down = `Button D_DOWN`
D-Pad/Left = `Button D_LEFT`
D-Pad/Right = `Button D_RIGHT`
Classic/Buttons/A = `Button A`
Classic/Buttons/B = `Button B`
Classic/Buttons/X = `Button X`
Classic/Buttons/Y = `Button Y`
Classic/Buttons/ZL = `Button Z`
Classic/Buttons/ZR = `Button L`
Classic/Buttons/+ = `Button R`
Classic/Buttons/- = `Button START`
Classic/Triggers/L = `Button L`
Classic/Triggers/R = `Button R`
Classic/D-Pad/Up = `Button D_UP`
Classic/D-Pad/Down = `Button D_DOWN`
Classic/D-Pad/Left = `Button D_LEFT`
Classic/D-Pad/Right = `Button D_RIGHT`
Classic/Left Stick/Up = `Axis MAIN Y +`
Classic/Left Stick/Down = `Axis MAIN Y -`
Classic/Left Stick/Left = `Axis MAIN X -`
Classic/Left Stick/Right = `Axis MAIN X +`
Classic/Right Stick/Up = `Axis C Y +`
Classic/Right Stick/Down = `Axis C Y -`
Classic/Right Stick/Left = `Axis C X -`
Classic/Right Stick/Right = `Axis C X +`
Nunchuk/Buttons/C = `Button X`
Nunchuk/Buttons/Z = `Button Z`
Nunchuk/Stick/Up = `Axis MAIN Y +`
Nunchuk/Stick/Down = `Axis MAIN Y -`
Nunchuk/Stick/Left = `Axis MAIN X -`
Nunchuk/Stick/Right = `Axis MAIN X +`
'''


class Pad:
    """One named-pipe controller.  Opened lazily: Dolphin creates the pipe when it starts."""

    def __init__(self, path):
        self.path = path
        self.fd = None

    def _open(self):
        if self.fd is None:
            for _ in range(120):
                try:
                    self.fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
                    break
                except OSError:
                    time.sleep(0.5)
            else:
                raise RuntimeError('pipe %s never opened' % self.path)

    def send(self, line):
        self._open()
        os.write(self.fd, (line + '\n').encode())

    def press(self, b): self.send('PRESS %s' % b)
    def release(self, b): self.send('RELEASE %s' % b)
    def stick(self, which, x, y): self.send('SET %s %.3f %.3f' % (which, (x + 1) / 2, (y + 1) / 2))   # -1..1, y up
    def set(self, axis, v): self.send('SET %s %.3f' % (axis, v))

    def tap(self, b, secs=0.25):
        self.press(b); time.sleep(secs); self.release(b); time.sleep(0.15)

    def clear(self):
        for b in ('A', 'B', 'X', 'Y', 'Z', 'START', 'L', 'R', 'D_UP', 'D_DOWN', 'D_LEFT', 'D_RIGHT'):
            self.release(b)
        self.stick('MAIN', 0, 0); self.stick('C', 0, 0)


class Gdb:
    """Just enough of the GDB remote protocol (Dolphin's stub) to read and write memory."""

    def __init__(self, port=GDB_PORT):
        for _ in range(60):
            try:
                self.s = socket.create_connection(('127.0.0.1', port), timeout=10)
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('no GDB stub on port %d' % port)
        self.buf = b''
        self.running = False

    def _send(self, body):
        b = body.encode()
        self.s.sendall(b'$' + b + b'#' + ('%02x' % (sum(b) & 0xFF)).encode())

    def _recv(self, timeout=10):
        self.s.settimeout(timeout)
        while True:
            if b'$' in self.buf and b'#' in self.buf.split(b'$', 1)[1] and len(self.buf.split(b'#', 1)[1]) >= 2:
                pre, rest = self.buf.split(b'$', 1)
                body, rest = rest.split(b'#', 1)
                self.buf = rest[2:]
                self.s.sendall(b'+')
                return body.decode(errors='replace')
            chunk = self.s.recv(4096)
            if not chunk:
                raise EOFError('GDB stub closed')
            self.buf += chunk

    def halt(self):
        if self.running:
            self.s.sendall(b'\x03')
            time.sleep(0.4)
            try:
                self._recv(3)
            except Exception:
                pass
            self.running = False
        self.buf = b''

    def resume(self):
        if not self.running:
            self._send('c')
            self.running = True

    def read(self, addr, n):
        """Halts the game for the read.  A halt can land inside an interrupt handler (address translation
        off), where the read fails: resume for a moment and try again."""
        was = self.running
        for attempt in range(40):
            self.halt()
            out = b''
            ok = True
            while len(out) < n:
                k = min(512, n - len(out))
                self._send('m%x,%x' % (addr + len(out), k))
                r = self._recv()
                if len(r) != 2 * k or any(c not in '0123456789abcdefABCDEF' for c in r):
                    ok = False          # E00, or a stray stop reply left over from the resume
                    break
                out += bytes.fromhex(r)
            if ok:
                if was:
                    self.resume()
                return out
            self.resume()
            time.sleep(0.05 + 0.02 * attempt)
        raise RuntimeError('read %08X failed' % addr)

    def regs(self):
        """r0..r31 of the halted game, plus pc (GDB register 64) and lr/ctr/cr (66..69)."""
        self.halt()
        self._send('g')
        r = self._recv()
        out = {'r%d' % i: int(r[8 * i:8 * i + 8], 16) for i in range(32)}
        for name, n in (('pc', 0x40), ('msr', 0x41), ('cr', 0x42), ('lr', 0x43), ('ctr', 0x44), ('xer', 0x45)):
            self._send('p%x' % n)
            v = self._recv()
            out[name] = int(v, 16) if v and all(c in '0123456789abcdefABCDEF' for c in v) else None
        return out

    def bp(self, addr, timeout=120):
        """Set a breakpoint, run to it; returns True if hit (game left halted there)."""
        self.halt()
        self._send('Z0,%x,4' % addr); self._recv()
        self._send('c'); self.running = True
        try:
            r = self._recv(timeout)
        except Exception:
            self.running = True
            return False
        self.running = False
        return r.startswith('T') or r.startswith('S')

    def unbp(self, addr):
        self._send('z0,%x,4' % addr); self._recv()

    def write(self, addr, data):
        was = self.running
        self.halt()
        self._send('M%x,%x:%s' % (addr, len(data), data.hex()))
        r = self._recv()
        if r != 'OK':
            raise RuntimeError('write %08X failed: %r' % (addr, r))
        if was:
            self.resume()


class Dolphin:
    def __init__(self, disc, gecko=None, game_id=None, wii_ext=None, sd=False, video='Null', extra=(), gc_ports=(1,)):
        self.disc, self.gecko, self.game_id = disc, gecko, game_id
        self.gc_ports = tuple(gc_ports)           # ports with a GameCube controller plugged in
        self.wii_ext = wii_ext or {}
        self.video, self.extra = video, list(extra)
        self.proc = None
        self.gdb = None

    # -- configuration -------------------------------------------------------
    def _configure(self):
        shutil.rmtree(os.path.join(USER, 'Config'), ignore_errors=True)
        for d in ('Config', 'GameSettings', 'Pipes', 'Wii', 'ScreenShots', 'Logs', 'Dump/Frames'):
            os.makedirs(os.path.join(USER, d), exist_ok=True)
        for f in os.listdir(os.path.join(USER, 'GameSettings')):
            os.remove(os.path.join(USER, 'GameSettings', f))
        cfg = os.path.join(USER, 'Config')
        sides = ''.join('SIDevice%d = %d\n' % (i, 6 if i + 1 in self.gc_ports else 0) for i in range(4))
        open(os.path.join(cfg, 'Dolphin.ini'), 'w').write(
            '[General]\nGDBPort = %d\n[Core]\nCPUCore = 4\nMMU = True\nEnableCheats = True\n%s'
            'WiimoteContinuousScanning = False\n[Interface]\nConfirmStop = False\nUsePanicHandlers = False\n'
            '[DSP]\nBackend = No Audio Output\n[Analytics]\nPermissionAsked = True\nEnabled = False\n'
            '[Input]\nBackgroundInput = True\n' % (GDB_PORT, sides))
        open(os.path.join(cfg, 'GCPadNew.ini'), 'w').write(''.join(GC_MAP % dict(n=n) for n in (1, 2, 3, 4)))
        wm = ''
        for n in (1, 2, 3, 4):
            ext = self.wii_ext.get(n)
            if n in self.wii_ext:
                wm += WII_MAP % dict(n=n, ext=ext or 'None')
            else:
                wm += '[Wiimote%d]\nSource = 0\n' % n
        open(os.path.join(cfg, 'WiimoteNew.ini'), 'w').write(wm)
        open(os.path.join(cfg, 'GFX.ini'), 'w').write('[Settings]\nShowFPS = False\nInternalResolution = 1\n')
        pipes = os.path.join(USER, 'Pipes')
        for p in os.listdir(pipes):
            os.remove(os.path.join(pipes, p))
        for n in (1, 2, 3, 4):
            for kind in ('gc', 'wm'):
                os.mkfifo(os.path.join(pipes, '%s%d' % (kind, n)))

        if self.gecko:
            gid = self.game_id or 'R4QE01'
            open(os.path.join(USER, 'GameSettings', gid + '.ini'), 'w').write(self.gecko_ini())

    def gecko_ini(self):
        """Gecko code text (plain `name\\ncode lines`) -> a GameSettings .ini with the code enabled."""
        lines = self.gecko.strip().splitlines()
        name = lines[0].lstrip('$')
        return '[Gecko]\n$%s\n%s\n[Gecko_Enabled]\n$%s\n' % (name, '\n'.join(lines[1:]), name)

    # -- lifecycle -----------------------------------------------------------
    def __enter__(self):
        self._configure()
        log = open(os.path.join(USER, 'dolphin.log'), 'w')
        self.proc = subprocess.Popen([APP, '-u', USER, '-b', '-e', self.disc, '-v', self.video] + self.extra,
                                     stdout=log, stderr=log)
        self.gc_pads = {n: Pad(os.path.join(USER, 'Pipes', 'gc%d' % n)) for n in (1, 2, 3, 4)}
        self.wii_pads = {n: Pad(os.path.join(USER, 'Pipes', 'wm%d' % n)) for n in (1, 2, 3, 4)}
        self.gdb = Gdb()
        self.gdb.running = False         # Dolphin's stub starts halted, waiting for a debugger
        self.gdb.resume()
        return self

    def __exit__(self, *a):
        try:
            self.gdb.s.close()
        except Exception:
            pass
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def window_ids(self):
        """(window id, width, height) of every window this Dolphin process owns (the render window is the big one).
        Needs tools/dev/winids.swift compiled to $KK_WINIDS (swiftc -O tools/dev/winids.swift -o <path>)."""
        exe = os.environ.get('KK_WINIDS', '/Volumes/SSD/larsen/claude-tmp/winids')
        out = subprocess.run([exe, str(self.proc.pid)], capture_output=True, text=True).stdout
        return [(int(l.split()[0]), float(l.split()[1]), float(l.split()[2])) for l in out.splitlines() if l.strip()]

    def shot(self, name):
        """Screenshot of this Dolphin's render window only (never the rest of the screen); returns the PNG path.
        Dolphin owns several same-sized windows (the render surface is one of them): every candidate is captured and
        the one holding the most image data is kept."""
        wins = [w for w in self.window_ids() if w[1] > 300 and w[2] > 300]
        dst = name if os.path.isabs(name) else os.path.join(ROOT, 'dumps', 'shots', name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        best = None
        for wid, _w, _h in wins:
            tmp = '%s.%d.png' % (dst, wid)
            subprocess.run(['screencapture', '-x', '-o', '-l%d' % wid, tmp], capture_output=True)
            if os.path.exists(tmp):
                if best is None or os.path.getsize(tmp) > os.path.getsize(best):
                    if best:
                        os.remove(best)
                    best = tmp
                else:
                    os.remove(tmp)
        if best:
            shutil.move(best, dst)
            return dst
        return None

    def gc(self, n=1): return self.gc_pads[n]
    def wii(self, n=1): return self.wii_pads[n]
    def read(self, addr, n): return self.gdb.read(addr, n)
    def bp(self, addr, timeout=120): return self.gdb.bp(addr, timeout)
    def regs(self): return self.gdb.regs()
    def resume(self): return self.gdb.resume()
    def unbp(self, addr): return self.gdb.unbp(addr)
    def write(self, addr, data): return self.gdb.write(addr, data)
    def u32(self, addr): return int.from_bytes(self.read(addr, 4), 'big')
    def log(self): return open(os.path.join(USER, 'dolphin.log'), errors='replace').read()


def game_dir(region, dol_path):
    """Boot path for `region` with `dol_path` as its main.dol.

    Dolphin boots an extracted-disc folder through sys/main.dol (it does not follow symlinked folders), so the
    DOL is copied into dumps/fst/<region>/sys.  The retail originals stay in dumps/dols.
    """
    dst = os.path.join(ROOT, 'dumps', 'fst', region, 'sys', 'main.dol')
    shutil.copy(dol_path, dst)
    return dst
