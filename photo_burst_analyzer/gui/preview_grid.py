import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageOps

class PreviewGrid:
    def __init__(self, parent, thumb_size=160, selected_callback=None):
        self.parent = parent
        self.frame = tk.Frame(parent)
        self.canvas = tk.Canvas(self.frame)
        self.scroll = ttk.Scrollbar(self.frame, orient='vertical', command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas)
        self.canvas.create_window((0,0), window=self.inner, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scroll.pack(side='right', fill='y')
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.thumb_size = thumb_size
        self.selected = set()
        self.bursts = []
        self.selected_callback = selected_callback

    def clear_selection(self):
        self.selected.clear()
        for w in self.inner.winfo_children():
            try: w.config(bd=1, relief='flat')
            except: pass
        if self.selected_callback: self.selected_callback()

    def set_thumb_size(self, size):
        self.thumb_size = int(size)

    def show_bursts(self, bursts):
        self.bursts = bursts
        for w in self.inner.winfo_children():
            w.destroy()
        row = 0
        for idx, b in enumerate(bursts, 1):
            header = tk.Label(self.inner, text=f"Burst {idx} — {len(b.get('burst'))} photos — total {b.get('proc_time'):.3f}s — avg {b.get('avg_proc_time'):.4f}s", font=('Arial',10,'bold'))
            header.grid(row=row, column=0, columnspan=10, sticky='w', pady=(6,2))
            row += 1
            col = 0
            for i, p in enumerate(b.get('burst', [])[:32]):
                try:
                    im = Image.open(p); im = ImageOps.exif_transpose(im); im = im.convert('RGB')
                    im.thumbnail((self.thumb_size, self.thumb_size))
                    tkim = ImageTk.PhotoImage(im)
                    container = tk.Frame(self.inner, bd=1, relief='flat')
                    container.grid(row=row, column=col, padx=6, pady=6)
                    lbl = tk.Label(container, image=tkim)
                    lbl.image = tkim; lbl.path = p
                    lbl.grid(row=0, column=0)
                    blur = b.get('blur_scores', [])
                    sad = b.get('sads', [])
                    blur_val = blur[i] if i < len(blur) else None
                    sad_val = sad[i] if i < len(sad) else None
                    infos = f"Blur: {blur_val:.2f}" if blur_val is not None else 'Blur:N/A'
                    infos += '\n' + (f"SAD→next: {sad_val:.2f}" if sad_val is not None else 'SAD:N/A')
                    info_lbl = tk.Label(container, text=infos, font=('Arial',8), justify='center')
                    info_lbl.grid(row=1, column=0)
                    def on_click(ev, path=p, widget=container):
                        if path in self.selected: self.selected.remove(path); widget.config(bd=1, relief='flat')
                        else: self.selected.add(path); widget.config(bd=2, relief='solid')
                        if self.selected_callback: self.selected_callback()
                    def on_dbl(ev, path=p, b=b):
                        self.open_preview(path, b)
                    container.bind('<Button-1>', on_click); lbl.bind('<Button-1>', on_click); info_lbl.bind('<Button-1>', on_click)
                    container.bind('<Double-Button-1>', on_dbl); lbl.bind('<Double-Button-1>', on_dbl); info_lbl.bind('<Double-Button-1>', on_dbl)
                    if 'selected' in b and p in b['selected']:
                        self.selected.add(p); container.config(bd=2, relief='solid')
                    col += 1
                    if col >= 8:
                        col = 0; row += 1
                except Exception:
                    pass
            row += 1
        if self.selected_callback: self.selected_callback()

    def open_preview(self, path, b):
        try:
            top = tk.Toplevel(self.parent)
            top.title(path)
            from PIL import Image, ImageTk, ImageOps
            im = Image.open(path); im = ImageOps.exif_transpose(im)
            info = ''
            try:
                i = b['burst'].index(path)
                blur = b.get('blur_scores', [])
                sad = b.get('sads', [])
                info = f"Blur: {blur[i] if i < len(blur) and blur[i] is not None else 'N/A'}   SAD→next: {sad[i] if i < len(sad) and sad[i] is not None else 'N/A'}"
            except Exception:
                pass
            tk.Label(top, text=info).pack()
            tkimg = ImageTk.PhotoImage(im)
            lbl = tk.Label(top, image=tkimg); lbl.image = tkimg; lbl.pack(fill='both', expand=True)
        except Exception as e:
            print('preview failed', e)
