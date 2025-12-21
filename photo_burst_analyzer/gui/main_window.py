import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .preview_grid import PreviewGrid
from ..core.burst_detector import collect_images, detect_candidates
from ..core.analysis_manager import analyze_photos_and_pairs
from ..core.exif_sorter import get_exif_timestamp
import threading, logging, os
logger = logging.getLogger('pba.gui')

def main():
    app = App(); app.mainloop()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Photo Burst Analyzer v6 - Fixed')
        self.geometry('1200x820')
        self.create_widgets()

    def create_widgets(self):
        top = tk.Frame(self); top.pack(fill='x', padx=8, pady=6)
        tk.Label(top, text='Burst time threshold (s):').pack(side='left')
        self.t_var = tk.DoubleVar(value=1.0)
        tk.Entry(top, textvariable=self.t_var, width=6).pack(side='left', padx=6)
        # checkboxes
        self.do_blur = tk.BooleanVar(value=True); self.do_sad = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text='Blur (Laplacian)', variable=self.do_blur).pack(side='left', padx=6)
        tk.Checkbutton(top, text='SAD (similarity)', variable=self.do_sad).pack(side='left', padx=6)
        tk.Button(top, text='Select Directory & Run', command=self.on_run).pack(side='left', padx=6)
        self.thumb_size = tk.IntVar(value=160)
        tk.Label(top, text='Thumbnail Size:').pack(side='left', padx=(20,4))
        s = ttk.Scale(top, from_=120, to=300, orient='horizontal', command=self.on_slider_move); s.set(self.thumb_size.get()); s.pack(side='left')
        s.bind('<ButtonRelease-1>', self.on_slider_release)
        # progress and cores info
        self.progress = ttk.Progressbar(top, orient='horizontal', length=300, mode='determinate')
        self.progress.pack(side='right', padx=8)
        self.core_info = tk.Label(top, text='Cores: - | Workers: -', font=('Arial',9)); self.core_info.pack(side='right', padx=8)
        self.selected_label = tk.Label(top, text='Selected: 0'); self.selected_label.pack(side='right', padx=10)
        # notebook
        nb = ttk.Notebook(self); nb.pack(fill='both', expand=True)
        self.preview_frame = tk.Frame(nb); nb.add(self.preview_frame, text='Previews')
        self.timeline_frame = tk.Frame(nb); nb.add(self.timeline_frame, text='Timeline')
        self.grid_widget = PreviewGrid(self.preview_frame, thumb_size=self.thumb_size.get(), selected_callback=self.update_selected_count)
        self.grid_widget.frame.pack(fill='both', expand=True)
        self.timeline_canvas = tk.Canvas(self.timeline_frame, bg='#f8f8f8'); self.timeline_canvas.pack(fill='both', expand=True, padx=8, pady=8)
        bottom = tk.Frame(self); bottom.pack(fill='x', padx=8, pady=6)
        tk.Button(bottom, text='Save Selected Best Shots', command=self.on_save_selected).pack(side='left')
        tk.Button(bottom, text='Clear Selection', command=self.on_clear_selection).pack(side='left', padx=6)
        tk.Button(bottom, text='Quit', command=self.quit).pack(side='right')

    def on_run(self):
        d = filedialog.askdirectory(title='Select photo directory')
        if not d: return
        self.input_dir = d; t = self.t_var.get()
        self.progress['value'] = 0; self.core_info.config(text='Cores: - | Workers: -')
        threading.Thread(target=self._analyze, args=(d, t, self.do_blur.get(), self.do_sad.get()), daemon=True).start()

    def _analyze(self, d, t, do_blur, do_sad):
        try:
            files = collect_images(d)
            photos = []
            for f in files:
                ts = get_exif_timestamp(f)
                if ts is not None: photos.append((f, ts))
            candidates = detect_candidates(photos, t)
            unique_photos = []
            pairs = []
            seen = set()
            for c in candidates:
                paths = [p for p,_ in c]
                for p in paths:
                    if p not in seen: seen.add(p); unique_photos.append(p)
                for a,bp in zip(paths, paths[1:]): pairs.append((a,bp))
            total_tasks = (len(unique_photos) if do_blur else 0) + (len(pairs) if do_sad else 0)
            self.after(0, lambda: self.progress.config(maximum=total_tasks))
            def progress_cb(completed, total, pcounts, cores):
                self.after(0, lambda: self._update_progress_ui(completed, total, pcounts, cores))
            augmented = analyze_photos_and_pairs(candidates, do_blur=do_blur, do_sad=do_sad, max_workers=None, progress_callback=progress_cb)
            for a in augmented:
                a['proc_time'] = a.get('proc_time') or 0.0
                a['avg_proc_time'] = a.get('avg_proc_time') or 0.0
            self.after(0, lambda: self.grid_widget.show_bursts(augmented))
            self.after(0, lambda: self.render_timeline(augmented))
        except Exception as e:
            logger.exception('analysis failed'); self.after(0, lambda: messagebox.showerror('Error', str(e)))
        finally:
            self.after(0, lambda: self.progress.stop())

    def _update_progress_ui(self, completed, total, pcounts, cores):
        try:
            self.progress['value'] = completed
            parts = [f'{pid}:{cnt}' for pid,cnt in sorted(pcounts.items())]
            self.core_info.config(text=f'Cores allocated: {cores} | workers: ' + ','.join(parts))
        except Exception:
            pass

    def render_timeline(self, bursts):
        c = self.timeline_canvas; c.delete('all')
        padx=20; pady=20; h=60; y=20
        for idx,b in enumerate(bursts,1):
            paths=b.get('burst',[])
            if not paths: continue
            x0=padx; x1=padx+min(900,len(paths)*60)
            c.create_rectangle(x0,y,x1,y+h,fill='#e6f2ff',outline='#5b9bd5')
            lbl=f'Burst {idx}: {len(paths)} photos, {b.get("proc_time"):.3f}s'
            c.create_text(x0+6,y+h/2,anchor='w',text=lbl)
            tx=x0+6; ty=y+6; thumb_h=h-12
            for p in paths[:12]:
                try:
                    from PIL import Image, ImageOps, ImageTk
                    im=Image.open(p); im=ImageOps.exif_transpose(im); im.thumbnail((thumb_h,thumb_h))
                    tkimg=ImageTk.PhotoImage(im)
                    c.image = getattr(c,'image',[]) + [tkimg]
                    c.create_image(tx,ty,anchor='nw',image=tkimg)
                    tx+=thumb_h+6
                except Exception:
                    pass
            y+=h+pady
        c.config(scrollregion=c.bbox('all'))

    def on_save_selected(self):
        dest = filedialog.askdirectory(title='Select destination folder to save selected photos')
        if not dest: return
        import shutil; saved=0
        for p in list(self.grid_widget.selected):
            try: shutil.copy2(p, os.path.join(dest, os.path.basename(p))); saved+=1
            except Exception: pass
        messagebox.showinfo('Saved', f'Saved {saved} files to {dest}')

    def on_clear_selection(self):
        self.grid_widget.clear_selection(); self.update_selected_count()

    def update_selected_count(self):
        cnt = len(self.grid_widget.selected); self.selected_label.config(text=f'Selected: {cnt}')

    def on_slider_move(self, val): pass
    def on_slider_release(self, event):
        w = event.widget; val = int(float(w.get())); self.thumb_size.set(val); self.grid_widget.set_thumb_size(val); self.grid_widget.show_bursts(self.grid_widget.bursts)
