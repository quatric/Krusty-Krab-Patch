#!/usr/bin/env python3
"""Drag-and-drop patcher: drop an Mario Strikers Charged disc image on the window, done.

Extracts the disc, patches its own main.dol for the options you tick, and
rebuilds the image in the same format.  The rebuilt image replaces the original
in place (USB loaders key off the `/wbfs/<Title> [ID6]/` layout) and the
untouched original is kept alongside as `<name>.bak`.
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disc
import features

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except ImportError:                                    # fall back to click-to-browse
    HAVE_DND = False


def asset(name):
    if getattr(sys, 'frozen', False):
        return os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), 'assets', name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', name)


BASE = TkinterDnD.Tk if HAVE_DND else tk.Tk


class App(BASE):
    def __init__(self):
        super().__init__()
        self.title('Strikers-Patcher')
        self.geometry('620x600')
        self.msgq = queue.Queue()
        self.busy = False

        try:
            img = tk.PhotoImage(file=asset('logo.png'))
            self.logo = img.subsample(max(1, img.width() // 300))
            tk.Label(self, image=self.logo).pack(pady=(10, 0))
        except Exception:                              # the window is fine without its logo
            pass
        tk.Label(self, text='USA / Europe / Japan',
                 font=('Helvetica', 12, 'bold')).pack(pady=(4, 6))

        opts = tk.LabelFrame(self, text='Patches')
        opts.pack(fill='x', padx=10)
        self.cc = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text='Classic Controller', variable=self.cc).pack(anchor='w')
        self.gc = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text='GameCube controller (all four ports)', variable=self.gc).pack(anchor='w')

        hint = ('Drop a .wbfs or .iso here\n\n(or click to choose one)'
                if HAVE_DND else 'Click to choose a .wbfs or .iso')
        self.drop = tk.Label(self, text=hint, relief='ridge', bd=2, padx=10, pady=24, cursor='hand2')
        self.drop.pack(fill='x', padx=10, pady=10)
        self.drop.bind('<Button-1>', lambda e: self.pick())
        if HAVE_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind('<<Drop>>', self.on_drop)

        tk.Label(self, text='The original is kept alongside as <name>.bak', fg='#666').pack()

        self.log = tk.Text(self, height=10, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True, padx=10, pady=10)
        self.after(100, self.poll_queue)

    def on_drop(self, event):
        paths = self.tk.splitlist(event.data)          # handles {braced paths with spaces}
        if paths:
            self.start(paths[0])

    def pick(self):
        if self.busy:
            return
        p = filedialog.askopenfilename(title='Select disc image',
                                       filetypes=[('Wii disc image', '*.wbfs *.iso'), ('All files', '*')])
        if p:
            self.start(p)

    def append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == 'log':
                    self.append_log(payload)
                elif kind == 'done':
                    ok, msg = payload
                    self.busy = False
                    self.drop.configure(state='normal')
                    if ok:
                        messagebox.showinfo('Done', 'Patched in place:\n%s' % msg)
                    else:
                        messagebox.showerror('Patch failed', msg)
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def start(self, image_path):
        if self.busy:
            return
        if not os.path.isfile(image_path):
            messagebox.showerror('Not a file', '%s is not a file.' % image_path)
            return
        which = [n for n, v in (('cc', self.cc), ('gc', self.gc)) if v.get()]
        if not which:
            messagebox.showerror('Nothing selected', 'Tick at least one patch.')
            return
        self.busy = True
        self.drop.configure(state='disabled')
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        threading.Thread(
            target=disc.run_patch,
            args=(image_path, lambda t: self.msgq.put(('log', t)),
                  lambda ok, m: self.msgq.put(('done', (ok, m))), which),
            daemon=True,
        ).start()


if __name__ == '__main__':
    App().mainloop()
