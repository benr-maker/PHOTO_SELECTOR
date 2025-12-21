from tkinter import filedialog, messagebox
import shutil, os
def save_selected(selected_set):
    dest = filedialog.askdirectory(title='Select destination folder to save selected photos')
    if not dest: return 0, None
    saved = 0
    for p in list(selected_set):
        try:
            shutil.copy2(p, os.path.join(dest, os.path.basename(p))); saved += 1
        except Exception:
            pass
    messagebox.showinfo('Saved', f'Saved {saved} files to {dest}')
    return saved, dest
