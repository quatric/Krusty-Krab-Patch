"""Patch a whole disc image: extract with wit, patch sys/main.dol, rebuild.

The rebuilt image replaces the original in place, keeping its filename and
folder (USB loaders key off the `/wbfs/<Title> [ID6]/` layout); the untouched
original is kept next to it as `<name>.bak`.
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features
import patcher
from dol import Dol
from regions import REGIONS


def find_wit():
    """A wit bundled with this app (PyInstaller build) wins over PATH.

    --add-binary'd files land next to sys._MEIPASS: a plain onedir build puts
    them in _internal/, and a windowed macOS .app puts them in
    Contents/Frameworks/ instead of Contents/MacOS/ alongside the binary.
    """
    name = 'wit.exe' if os.name == 'nt' else 'wit'
    if getattr(sys, 'frozen', False):
        for base in (getattr(sys, '_MEIPASS', None), os.path.dirname(sys.executable)):
            if base:
                bundled = os.path.join(base, name)
                if os.path.isfile(bundled):
                    return bundled
    return shutil.which('wit')


def find_file(root, name):
    for r, _, files in os.walk(root):
        if name in files:
            return os.path.join(r, name)
    return None


def read_disc_id(fst):
    boot = find_file(fst, 'boot.bin')
    if not boot:
        return None
    with open(boot, 'rb') as f:
        header = f.read(8)
    return header[0:6].decode('ascii', 'replace'), header[7]


def run_patch(image_path, log, done, which=('cc', 'gc')):
    """Patch `image_path` in place.  `which` names the features."""
    try:
        wit = find_wit()
        if wit is None:
            raise RuntimeError('wit (Wiimms ISO Tool) not found: not bundled with this '
                               'build and not on PATH')
        which = [w for w in patcher.ORDER if w in which]
        if not which:
            raise RuntimeError('nothing selected: tick at least one patch')
        fmt = '--iso' if image_path.lower().endswith('.iso') else '--wbfs'

        with tempfile.TemporaryDirectory(prefix='strikers_patch_') as tmp:
            fst = os.path.join(tmp, 'fst')
            log('extracting %s...' % os.path.basename(image_path))
            r = subprocess.run([wit, 'extract', image_path, '--dest', fst, '--psel', 'data',
                                '--overwrite', '-q'], capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError('extract failed:\n' + (r.stderr or r.stdout))

            got = read_disc_id(fst)
            if not got:
                raise RuntimeError('could not read sys/boot.bin from the extracted disc')
            disc_id = got[0]

            dol_path = find_file(fst, 'main.dol')
            if not dol_path or os.path.basename(os.path.dirname(dol_path)) != 'sys':
                raise RuntimeError('could not find sys/main.dol in the extracted disc')
            dol = Dol(dol_path)

            # the two European discs share an id and version: the main.dol tells them apart
            region = patcher.detect_region(dol, disc_id)
            if region is None:
                raise RuntimeError('%s is not a Mario Strikers Charged release this patcher knows (or its main.dol is '
                                   'already modified by something else).\n\nSupported: %s' % (disc_id, ', '.join(
                                       '%s (%s)' % (v['disc_id'], v['short']) for v in REGIONS.values())))
            log('disc: %s (%s)' % (disc_id, REGIONS[region]['label']))

            have = patcher.status(dol, region)
            todo = []
            for name in which:
                st = have.get(name)
                if st == 'patched':
                    log('%s is already in this disc, skipping' % features.TITLES[name])
                elif st == 'clean':
                    todo.append(name)
                else:
                    raise RuntimeError('the main.dol does not match the retail %s (%s) -- already modified '
                                       'by something else, or not an unmodified dump. Not patching it.'
                                       % (REGIONS[region]['label'], features.TITLES[name]))
            if not todo:
                raise RuntimeError('nothing left to add: the selected patches are already in this disc.')

            if todo:
                for t in patcher.patch(dol, region, todo):
                    log('  added %s' % t)
                dol.save(dol_path)
                log('  patched main.dol')

            staged = os.path.join(tmp, 'patched.img')
            log('rebuilding...')
            cmd = [wit, 'copy', fst, '--dest', staged, fmt, '--overwrite', '-q']
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode:
                raise RuntimeError('rebuild failed:\n' + (r.stderr or r.stdout))

            # Only touch the user's file once the rebuild has actually succeeded.
            backup = image_path + '.bak'
            if os.path.exists(backup):
                log('  backup already exists, keeping it: %s' % os.path.basename(backup))
            else:
                shutil.copyfile(image_path, backup)
                log('  backed up original -> %s' % os.path.basename(backup))
            shutil.move(staged, image_path)
            log('done: patched in place, %s' % os.path.basename(image_path))
            done(True, image_path)
    except Exception as e:
        log('ERROR: %s' % e)
        done(False, str(e))
