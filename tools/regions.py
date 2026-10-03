"""The retail releases of SpongeBob SquarePants: Creature from the Krusty Krab (Wii).

Each release has its own disc id, so a disc is told apart by the id in its boot.bin; the patcher also checks
the retail bytes at every site before it touches anything.  The game was only released as one disc per region
(USA, Europe); no other region was available to build or test against.
"""
REGIONS = {
    'RQ4E78': dict(disc_id='RQ4E78', label='SpongeBob SquarePants: Creature from the Krusty Krab (USA)',
                   short='USA', dol_size=5380768),
    'RQ4P78': dict(disc_id='RQ4P78', label='SpongeBob SquarePants: Creature from the Krusty Krab (Europe)',
                   short='Europe', dol_size=5386624),
}


def for_disc(disc_id):
    """Regions that share a disc id."""
    return [r for r, v in REGIONS.items() if v['disc_id'] == disc_id]
