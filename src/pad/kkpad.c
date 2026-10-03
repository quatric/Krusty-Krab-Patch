/* Classic Controller and GameCube controller support for SpongeBob SquarePants: Creature from the Krusty Krab (Wii).
 *
 * The game wraps the Wii Remote SDK (KPAD) in its own device layer, bReadPhysicalInputDevices(), which runs once per
 * frame: KPADRead for the four channels, then WPADProbe per channel to learn what is plugged in, then bPadCopy to turn
 * the newest sample into the pad records the rest of the engine reads.  It understands a Wii Remote with or without a
 * Nunchuk and nothing else: a Classic Controller is dropped on the floor, and a channel with no Wii Remote is "empty".
 *
 * Both hooks sit inside that function, so everything downstream (button channels, the stick, the motion detectors
 * that read the accelerometer history) keeps working unchanged and sees a Wii Remote with a Nunchuk:
 *
 *   KPAD   right after KPADRead (just before the sample count is stored)
 *            - a Wii Remote with a Classic Controller: the samples are rewritten as Nunchuk samples
 *            - no Wii Remote (or one with no extension) and a GameCube pad on the same port: three fresh samples
 *              are written and the count says so
 *   PROBE  right after WPADProbe: a Classic Controller is reported as a Nunchuk; a pad on a channel with no Wii Remote
 *            makes the probe succeed with a Nunchuk
 *
 * Buttons and sticks land where the same press on a Wii Remote + Nunchuk would; the motion gestures the game asks for
 * (swinging the remote, shaking the Nunchuk) are played back as accelerometer samples when their button goes down.
 *
 * The game links the SI library but not PAD, so nothing polls the pads: poll_all() drives the Serial Interface's
 * auto-poller itself (the approach of the other patches in this family, which was checked on a console).  Addresses
 * arrive as -D macros, resolved per release by tools/anchors.py.
 */
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned char u8;
typedef signed char s8;

#define R32(a) (*(volatile u32 *)(a))
#define SI_OUT(c)  (0xCD006400u + 12u * (c))
#define SI_INH(c)  (0xCD006404u + 12u * (c))
#define SI_INL(c)  (0xCD006408u + 12u * (c))
#define SI_POLL    (0xCD006430u)
#define SI_COMCSR  (0xCD006434u)
#define SI_SR      (0xCD006438u)

#define TB_PROBE   15187500u      /* 0.25 s: re-probe an empty port at most this often */
#define TB_NOREP   9112500u       /* 0.15 s of NOREP before a pad counts as unplugged */
#define TB_BUSY    60750000u      /* 1 s: an SI transfer that long is wedged */
#define TB_POLL    30000u         /* the poller itself runs at most every 0.5 ms */

struct ch {
    u32 prev_hold;      /* Wii Remote button word of the previous frame (for trig / release) */
    u32 prev_cc;        /* Classic button word of the previous frame (edge detection for gestures) */
    u32 swing_t;        /* samples left in a running Wii Remote swing */
    u32 shake_t;        /* samples left in a running Nunchuk shake */
    u32 bump_t;         /* samples left in a running downward thrust (butt bounce) */
    u32 phase;          /* running sample counter, for the oscillating part of a gesture */
};

struct st {
    u32 probe_tb[4];    /* last SIGetType per port */
    u32 norep_tb[4];    /* when NOREP was first seen on a port (0 = not seen) */
    u32 busy_tb;        /* when si:: was first seen busy (0 = idle) */
    u32 poll_tb;        /* last poller run */
    u32 mode[4];        /* what drives each channel this frame: 0 nothing, 1 Classic Controller, 2 GameCube pad */
    struct ch ch[4];
};
#define ST ((volatile struct st *)STATE)

static inline u32 tb(void)
{
    u32 t;
    __asm__ volatile("mftb %0" : "=r"(t));
    return t;
}

static inline int confirmed(u32 type)
{
    return !(type & 0x80) && (type & 0x18000000u) == 0x08000000u;
}

/* ------------------------------------------------------------------ SI poller */
static void poll_all(void)
{
    volatile u32 *types = (volatile u32 *)SI_TYPES;
    u32 now = tb(), sisr, mask, poll, c;
    s32 busy;

    if (now - ST->poll_tb < TB_POLL)
        return;
    ST->poll_tb = now;

    /* probe every port that has no confirmed pad, at most every 0.25 s each: probing every frame collided with the
     * pad's own polling on hardware */
    for (c = 0; c < 4; c++) {
        if (!confirmed(types[c]) && now - ST->probe_tb[c] >= TB_PROBE) {
            ST->probe_tb[c] = now;
            ((u32 (*)(u32))FN_SIGETTYPE)(c);
        }
    }

    /* an unplugged pad latches NOREP; si:: never reads it (no PAD library), so copy a persistent one into the type
     * cache ourselves, which makes SIGetType probe the port again once a pad is plugged back in */
    sisr = R32(SI_SR);
    for (c = 0; c < 4; c++) {
        if ((sisr >> (24 - 8 * c)) & 8u) {
            if (!ST->norep_tb[c])
                ST->norep_tb[c] = now | 1;
            else if (now - ST->norep_tb[c] >= TB_NOREP)
                types[c] = 8;
        } else {
            ST->norep_tb[c] = 0;
        }
    }

    R32(SI_OUT(0)) = 0x00400300u;                    /* poll command */
    R32(SI_OUT(1)) = 0x00400300u;
    R32(SI_OUT(2)) = 0x00400300u;
    R32(SI_OUT(3)) = 0x00400300u;
    R32(SI_SR) = (sisr & 0x0F0F0F0Fu) | 0x80000000u; /* ack errors, latch the OUT buffers */

    /* poll (and copy on vblank) only the ports with a confirmed pad: a port can only be probed successfully
     * while it is not being polled */
    mask = 0;
    for (c = 0; c < 4; c++)
        if (confirmed(types[c]))
            mask |= 0x88u >> c;
    poll = R32(SI_POLL) & ~0xFFu;
    if (!(poll & 0xFF00u))
        poll |= 0x0100u;
    R32(SI_POLL) = poll | mask;
    /* si:: rewrites SIPOLL from its own shadow on every retrace */
    R32(SI_SHADOW) = (R32(SI_SHADOW) & ~0xFFu) | mask;

    /* a pad unplugged mid-transfer leaves si::'s global busy flag wedged (nothing times it out): force it idle
     * after a second */
    busy = (s32)R32(SI_BUSY);
    if (busy == -1) {
        ST->busy_tb = 0;
    } else if (ST->busy_tb == 0) {
        ST->busy_tb = now | 1;
    } else if (now - ST->busy_tb >= TB_BUSY) {
        u32 lvl = ((u32 (*)(void))FN_OSDISABLE)();
        R32(SI_BUSY) = (u32)-1;
        R32(SI_COMCSR) = 0x80000000u;
        ((void (*)(u32))FN_OSRESTORE)(lvl);
        ST->busy_tb = 0;
    }
}

/* a valid, error-free pad response on this port */
static inline int pad_in(u32 chan, u32 *h, u32 *l)
{
    u32 v = R32(SI_INH(chan));

    if ((v & 0x80000000u) || !(v & 0x00800000u))
        return 0;
    *h = v;
    *l = R32(SI_INL(chan));
    return 1;
}

/* ------------------------------------------------- float <-> 1/1024 fixed point
 * The hooks are built without an FPU or libgcc, so the few float fields they touch are converted by hand. */
static inline s32 fx(u32 bits)
{
    s32 e = (bits >> 23) & 0xFF, sh, m;

    if (e < 117)                                /* below 2^-10 */
        return 0;
    m = (bits & 0x7FFFFF) | 0x800000;
    sh = e - 127 + 10 - 23;
    if (sh > 4)
        m = 0x7FFFF;                            /* saturate: far outside any real value */
    else if (sh >= 0)
        m <<= sh;
    else if (sh > -32)
        m >>= -sh;
    else
        m = 0;
    return (bits >> 31) ? -m : m;
}

static inline u32 fl(s32 v)
{
    u32 a, s = 0, p, m;

    if (!v)
        return 0;
    if (v < 0) {
        s = 0x80000000u;
        a = (u32)-v;
    } else {
        a = (u32)v;
    }
    p = 31 - __builtin_clz(a);
    m = p <= 23 ? (a << (23 - p)) : (a >> (p - 23));
    return s | ((127 + p - 10) << 23) | (m & 0x7FFFFF);
}

#define ONE 1024
#define W32(b, o, v) (*(volatile u32 *)((b) + (o)) = (v))
#define R32F(b, o) (*(volatile u32 *)((b) + (o)))

/* ------------------------------------------------------- Wii Remote button bits */
#define WB_LEFT  0x0001
#define WB_RIGHT 0x0002
#define WB_DOWN  0x0004
#define WB_UP    0x0008
#define WB_PLUS  0x0010
#define WB_2     0x0100
#define WB_1     0x0200
#define WB_B     0x0400
#define WB_A     0x0800
#define WB_MINUS 0x1000
#define WB_Z     0x2000
#define WB_C     0x4000
#define WB_HOME  0x8000
/* the buttons on the Wii Remote itself (everything but the Nunchuk's Z and C) */
#define WB_REMOTE (WB_LEFT | WB_RIGHT | WB_DOWN | WB_UP | WB_PLUS | WB_2 | WB_1 | WB_B | WB_A | WB_MINUS | WB_HOME)

/* Classic Controller buttons as KPAD reports them */
#define CL_UP    0x0001
#define CL_LEFT  0x0002
#define CL_ZR    0x0004
#define CL_X     0x0008
#define CL_A     0x0010
#define CL_Y     0x0020
#define CL_B     0x0040
#define CL_ZL    0x0080
#define CL_R     0x0200
#define CL_PLUS  0x0400
#define CL_HOME  0x0800
#define CL_MINUS 0x1000
#define CL_L     0x2000
#define CL_DOWN  0x4000
#define CL_RIGHT 0x8000

/* GameCube pad -> Classic Controller buttons.  Z is ZL, Start is Plus, L + R + Start is HOME. */
static __attribute__((noinline)) u32 gc_to_cc(u32 h)
{
    u32 b = 0;

    if (h & 0x01000000u) b |= CL_A;
    if (h & 0x02000000u) b |= CL_B;
    if (h & 0x04000000u) b |= CL_X;
    if (h & 0x08000000u) b |= CL_Y;
    if (h & 0x10000000u) b |= CL_PLUS;
    if (h & 0x00100000u) b |= CL_ZL;
    if (h & 0x00400000u) b |= CL_L;
    if (h & 0x00200000u) b |= CL_R;
    if (h & 0x00080000u) b |= CL_UP;
    if (h & 0x00040000u) b |= CL_DOWN;
    if (h & 0x00020000u) b |= CL_RIGHT;
    if (h & 0x00010000u) b |= CL_LEFT;
    if ((b & (CL_L | CL_R | CL_PLUS)) == (CL_L | CL_R | CL_PLUS))
        b = (b & ~(CL_L | CL_R | CL_PLUS)) | CL_HOME;
    return b;
}

/* Classic Controller buttons -> Wii Remote + Nunchuk buttons.  The three gesture bits (swing, shake, bump) are not
 * buttons on the Wii side; they start the matching accelerometer motion. */
#define G_SWING 1
#define G_SHAKE 2
#define G_BUMP  4

static __attribute__((noinline)) u32 cc_to_wii(u32 cc, u32 *gest)
{
    u32 w = 0, g = 0;

    if (cc & CL_UP)    w |= WB_UP;
    if (cc & CL_DOWN)  w |= WB_DOWN;
    if (cc & CL_LEFT)  w |= WB_LEFT;
    if (cc & CL_RIGHT) w |= WB_RIGHT;
    if (cc & CL_A)     w |= WB_A;
    if (cc & CL_B)     w |= WB_B;
    if (cc & CL_X)     w |= WB_C;
    if (cc & CL_ZL)    w |= WB_Z;
    if (cc & CL_ZR)    w |= WB_2;
    if (cc & CL_PLUS)  w |= WB_PLUS;
    if (cc & CL_MINUS) w |= WB_MINUS;
    if (cc & CL_HOME)  w |= WB_HOME;
    if (cc & CL_Y)     g |= G_SWING;
    if (cc & CL_L)     g |= G_SHAKE;
    if (cc & CL_R)     g |= G_BUMP;
    *gest = g;
    return w;
}

/* --------------------------------------------------------------- KPAD samples */
#define K_SIZE   0x88
#define K_HOLD   0x00
#define K_TRIG   0x04
#define K_REL    0x08
#define K_ACC    0x0C       /* Wii Remote acceleration x, y, z (floats, in g) */
#define K_ACCV   0x18       /* |acceleration| */
#define K_ACCS   0x1C       /* change of |acceleration| since the previous sample */
#define K_TYPE   0x5C       /* extension: 0 none, 1 Nunchuk, 2 Classic Controller */
#define K_FSTK   0x60       /* Nunchuk stick x, y (floats, -1..1) */
#define K_FACC   0x68       /* Nunchuk acceleration x, y, z */
#define K_FACCV  0x74
#define K_FACCS  0x78
#define K_CLHOLD 0x60       /* Classic Controller: buttons, trig, release, left stick, right stick, triggers */
#define K_CLLX   0x6C
#define K_CLLY   0x70
#define K_CLRX   0x74
#define K_CLRY   0x78
#define K_DPD    0x84       /* pointer data valid */

/* one rest sample, as the game sees an idle Wii Remote and Nunchuk (recorded from a real emulated pair) */
static void rest_sample(u8 *s)
{
    u32 i;

    for (i = 0; i < K_SIZE; i += 4)
        W32(s, i, 0);
    W32(s, 0x10, fl(-ONE));
    W32(s, K_ACCV, fl(ONE));
    W32(s, 0x34, fl(ONE));
    W32(s, 0x48, fl(ONE));
    W32(s, 0x54, fl(ONE));
    W32(s, K_TYPE, 1);
    W32(s, K_FACC + 4, fl(-ONE));
    W32(s, K_FACCV, fl(ONE));
}

static inline u32 iabs(s32 v)
{
    return v < 0 ? (u32)-v : (u32)v;
}

/* Add the accelerometer motion of the running gestures to one sample and advance them.  The motions are plain
 * oscillations of large amplitude: the game's detectors look at peaks of |a| and at its change from sample to
 * sample.  ax/ay/az: Wii Remote, nx/ny/nz: Nunchuk, 1/1024 g. */
static void gesture_sample(volatile struct ch *c, s32 *a, s32 *n)
{
    s32 sgn = (c->phase & 1) ? 1 : -1;

    if (c->swing_t) {
        a[0] += sgn * 3 * ONE;
        a[2] += sgn * ONE;
        c->swing_t--;
    }
    if (c->shake_t) {
        n[0] += sgn * 3 * ONE;
        n[1] += sgn * 2 * ONE;
        c->shake_t--;
    }
    if (c->bump_t) {
        a[1] -= 3 * ONE;
        a[2] += sgn * ONE;
        c->bump_t--;
    }
    c->phase++;
}

#define GEST_SAMPLES 12     /* a gesture lasts this many samples (about 4 frames at 3 samples a frame) */

static void write_motion(u8 *s, volatile struct ch *c, s32 *prev)
{
    s32 a[3], n[3];
    u32 i;

    a[0] = 0; a[1] = -ONE; a[2] = 0;
    n[0] = 0; n[1] = -ONE; n[2] = 0;
    gesture_sample(c, a, n);
    for (i = 0; i < 3; i++) {
        W32(s, K_ACC + 4 * i, fl(a[i]));
        W32(s, K_FACC + 4 * i, fl(n[i]));
    }
    {
        u32 ma = iabs(a[0]) + iabs(a[1]) + iabs(a[2]);      /* |a| is only compared against thresholds: the L1 norm is
                                                               close enough and needs no square root */
        u32 mn = iabs(n[0]) + iabs(n[1]) + iabs(n[2]);
        W32(s, K_ACCV, fl(ma));
        W32(s, K_FACCV, fl(mn));
        W32(s, K_ACCS, fl(iabs((s32)ma - prev[0])));
        W32(s, K_FACCS, fl(iabs((s32)mn - prev[1])));
        prev[0] = ma;
        prev[1] = mn;
    }
}

/* Fire the gestures whose button just went down. */
static void gestures(volatile struct ch *c, u32 g_now, u32 g_prev)
{
    u32 edge = g_now & ~g_prev;

    if (edge & G_SWING) c->swing_t = GEST_SAMPLES;
    if (edge & G_SHAKE) c->shake_t = GEST_SAMPLES;
    if (edge & G_BUMP)  c->bump_t = GEST_SAMPLES;
}

/* ------------------------------------------------------------------ the hooks */
static inline s32 stick_gc(u32 raw)
{
    s32 v = ((s32)(raw & 0xFF) - 128) * ONE / 90;

    if (v > ONE)
        v = ONE;
    if (v < -ONE)
        v = -ONE;
    if (v < 61 && v > -61)                      /* ~6%: the pad's own rest wobble */
        v = 0;
    return v;
}

#if defined(HOOK_KPAD)
/* Called with the sample count KPADRead returned for `chan`; returns the count the game should see. */
u32 kk_kpad(u32 count, u32 chan, u8 *buf)
{
    volatile struct ch *c;
    u32 h, l, i;
    s32 prev[2];

    if (chan > 3)
        return count;
    c = &ST->ch[chan];
    poll_all();
    prev[0] = ONE; prev[1] = ONE;

    if (count && (s32)R32F(buf, K_TYPE) == 2) {
        /* Wii Remote + Classic Controller: rewrite every sample as a Nunchuk sample, oldest first (index 0 is the
         * newest), keeping the Wii Remote's own buttons next to the Classic Controller's */
        u32 pw = c->prev_hold;

        for (i = count; i-- > 0;) {
            u8 *s = buf + i * K_SIZE;
            u32 g, w = cc_to_wii(R32F(s, K_CLHOLD) & 0xFFFF, &g) | (R32F(s, K_HOLD) & WB_REMOTE);
            u32 lx = R32F(s, K_CLLX), ly = R32F(s, K_CLLY);

            gestures(c, g, c->prev_cc);
            c->prev_cc = g;
            W32(s, K_HOLD, w);
            W32(s, K_TRIG, w & ~pw);
            W32(s, K_REL, ~w & pw & 0xFFFF);
            pw = w;
            W32(s, K_TYPE, 1);
            W32(s, K_FSTK, lx);
            W32(s, K_FSTK + 4, ly);
            write_motion(s, c, prev);
            W32(s, K_DPD, R32F(s, K_DPD) & 0x00FFFFFFu);
        }
        c->prev_hold = pw;
        ST->mode[chan] = 1;
        return count;
    }

    if ((!count || (s32)R32F(buf, K_TYPE) == 0) && pad_in(chan, &h, &l)) {
        u32 cc = gc_to_cc(h), g, w;
        s32 lx = stick_gc(h >> 8), ly = stick_gc(h);

        w = cc_to_wii(cc, &g);
        gestures(c, g, c->prev_cc);
        c->prev_cc = g;
        for (i = 0; i < 3; i++) {
            u8 *s = buf + i * K_SIZE;

            rest_sample(s);
            W32(s, K_HOLD, w);
            W32(s, K_TRIG, i == 0 ? (w & ~c->prev_hold) : 0);
            W32(s, K_REL, i == 0 ? (~w & c->prev_hold & 0xFFFF) : 0);
            W32(s, K_FSTK, fl(lx));
            W32(s, K_FSTK + 4, fl(ly));
            write_motion(s, c, prev);
        }
        c->prev_hold = w;
        ST->mode[chan] = 2;
        return 3;
    }

    ST->mode[chan] = 0;
    return count;
}
#endif

#if defined(HOOK_PROBE)
/* Called with WPADProbe's result for `chan` and the pointer to the type it reported; returns the result the game
 * should see. */
s32 kk_probe(s32 res, u32 chan, s32 *type)
{
    if (chan > 3)
        return res;
    switch (ST->mode[chan]) {
    case 1:
        if (res == 0 && *type == 2)
            *type = 1;
        break;
    case 2:
        *type = 1;
        res = 0;
        break;
    }
    return res;
}
#endif
