/* Entry stubs for the two hooks in bReadPhysicalInputDevices().  Each saves every volatile register, calls the C
 * hook, stores the hook's result back into the saved r3, restores everything and then runs the instruction the hook
 * replaced.  The slot before the last word is that displaced instruction (the builder fills it in); the last word
 * becomes the branch back to site + 4. */
    .macro SAVE
    stwu    1, -0x70(1)
    stw     0, 0x0c(1)
    stw     3, 0x10(1)
    stw     4, 0x14(1)
    stw     5, 0x18(1)
    stw     6, 0x1c(1)
    stw     7, 0x20(1)
    stw     8, 0x24(1)
    stw     9, 0x28(1)
    stw     10, 0x2c(1)
    stw     11, 0x30(1)
    stw     12, 0x34(1)
    mflr    0
    stw     0, 0x38(1)
    mfcr    0
    stw     0, 0x3c(1)
    mfctr   0
    stw     0, 0x40(1)
    mfxer   0
    stw     0, 0x44(1)
    .endm

    .macro RESTORE_ALL
    lwz     0, 0x44(1)
    mtxer   0
    lwz     0, 0x40(1)
    mtctr   0
    lwz     0, 0x3c(1)
    mtcr    0
    lwz     0, 0x38(1)
    mtlr    0
    lwz     3, 0x10(1)
    lwz     4, 0x14(1)
    lwz     5, 0x18(1)
    lwz     6, 0x1c(1)
    lwz     7, 0x20(1)
    lwz     8, 0x24(1)
    lwz     9, 0x28(1)
    lwz     10, 0x2c(1)
    lwz     11, 0x30(1)
    lwz     12, 0x34(1)
    lwz     0, 0x0c(1)
    addi    1, 1, 0x70
    .endm

    .section .gcstart, "ax"
    b       _entry

    .section .gctail, "ax"
    .globl _entry
_entry:
    SAVE
#if defined(HOOK_KPAD)
    /* site: the `stw r3,164(r21)` after KPADRead.  r3 = sample count, r22 = channel + 1, r20 = the sample buffer */
    addi    4, 22, -1
    mr      5, 20
    bl      kk_kpad
#elif defined(HOOK_PROBE)
    /* site: the join after WPADProbe.  r3 = result, r26 = channel, the type sits at r1 + 8 of the hooked function */
    mr      4, 26
    addi    5, 1, 0x78
    bl      kk_probe
#endif
    stw     3, 0x10(1)          /* the hook's result replaces r3 */
    RESTORE_ALL
    .long   0xD15B1ACE          /* the displaced instruction */
    nop                         /* becomes the branch back */
