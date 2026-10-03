"""Where the hook trampolines live in the injected low-memory section.

Every patch is a set of hooks: one instruction in the game is replaced by a branch to a small self-contained
routine that runs the displaced instruction and branches back.  A Gecko code handler stores those routines
itself (C2 codes); the patched DOL and the Riivolution patch need somewhere to put them, so the patcher adds one
text section at CAVE_BASE.

0x80001800-0x80003000 is the Wii's boot-time scratch area; this game's first DOL section starts at 0x80004000,
so nothing of the game lives below it.  The first 0x20 bytes are skipped: the word at 0x80001800 is overwritten
by the OS early on.

The hooks keep their variables at STATE: 0x80005C00 sits in zero padding between two exception vectors in the
game's first text section (zero in the retail DOL of every release), so a Gecko code can use it without writing
it.
"""
CAVE_BASE = 0x80001820
CAVE_LIMIT = 0x80003000

PAD_BASE = 0x80001820         # hook trampolines
PAD_END = 0x80002C00

WINDOWS = {'pad': (PAD_BASE, PAD_END)}

STATE = 0x80005C00
STATE_SIZE = 0x100
