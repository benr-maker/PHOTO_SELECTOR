# Photo Burst Analyzer — User Manual

---

## What Is This Program?

When you shoot in burst mode, your camera takes 5, 10, or even 20 shots in a single second.
Most of those shots are nearly identical — and picking the sharpest one by eye, across thousands
of photos, is tedious and time-consuming.

**Photo Burst Analyzer does that work for you.**

It scans your photo folder, groups shots that were taken within one second of each other
(a "burst"), analyzes each photo for sharpness and exposure, and presents you with the best
candidate already highlighted. You review one burst at a time, confirm or override the
selection, then export only the photos you want to keep.

A folder of 2,000 photos that would take hours to review manually can be culled in minutes.

---

## The Three Stages at a Glance

```
Your folder  →  Stage 1: Burst Review  →  Stage 2: Final Selection  →  Exported photos
```

| Stage | What happens |
|-------|-------------|
| **Stage 1 — Burst Review** | You see one burst at a time. The sharpest photo is already highlighted. Confirm it, swap it, or keep several. |
| **Stage 2 — Final Selection** | All your chosen photos appear in a grid. Reorder them, drop any last-minute rejects, then export. |

Photos that were **not part of any burst** (single shots) are carried through automatically —
you never need to touch them.

---

## Getting Started

1. Double-click **PhotoBurstAnalyzer** to open the app.
2. Click **Select Photo Folder** on the welcome screen.
3. Navigate to the folder that contains your photos and click **Open**.
4. The app scans and scores your photos. A progress bar shows how far along it is.
5. When the analysis is complete, Stage 1 begins automatically.

> **Tip:** The app reads the date and time stamped inside each photo (EXIF data) to group
> bursts. Photos without this timestamp (screenshots, downloaded images) are treated as
> single shots and kept automatically.

---

## Stage 1 — Burst Review

### What You See

- A **filmstrip** of every photo in the current burst runs across the middle of the screen.
- The photo the computer thinks is sharpest has a **green border** — that is the suggested pick.
- Below each photo are three score bars:
  - **Sharp** — how in-focus the photo is
  - **Expo** — how well exposed it is (not too dark, not blown out)
  - **Score** — the combined overall quality rating
- The status bar shows which burst you are on and how many are left.

### Making Your Decision

**To accept the computer's suggestion** — press the **Space bar** or click **Accept Best**.
The highlighted photo is kept and you move to the next burst.

**To pick a different photo** — click any other photo in the filmstrip. It gets the green
border. Then press Space or click Accept Best to confirm it.

**To keep more than one photo** — hold **Ctrl** and click additional photos. Multiple green
borders will appear. Then press Space to keep all of them.

**To skip the whole burst** — click **Skip** or press **S**. No photo from this burst is kept.

**To keep every photo in the burst** — click **Keep All** or press **A**.

### Comparing Photos Side by Side

Click **Compare** (or press **C**) to open a comparison window.

- All photos in the burst appear side by side in a scrollable row.
- **Click any photo** to select it (green border appears). Click it again to deselect.
- You can select as many photos as you like.
- When you are done choosing, click **Done**, press **Escape**, or close the window.
  Your selections are applied automatically.
- Drag the corner of the comparison window to make it larger — the photos grow with it.
- Check **Rule of Thirds** to overlay compositional guide lines on every photo.

### Navigating Between Photos in a Burst

- **Left / Right arrow keys** — move the highlighted pick one photo to the left or right
  within the filmstrip without accepting yet.

### Keyboard Shortcuts — Stage 1

| Key | Action |
|-----|--------|
| Space | Accept current pick and move to next burst |
| ← → | Shift the highlighted pick left or right |
| C | Open comparison window |
| A | Keep all photos in this burst |
| S | Skip this burst (keep nothing) |
| Ctrl + click | Add a photo to the selection |

---

## Stage 2 — Final Selection

After you finish reviewing all bursts, every photo you accepted — plus all your single shots —
appears here in a scrollable thumbnail grid.

### What You Can Do

**Deselect a photo** — click it. The green border disappears, meaning it will not be exported.
Click it again to re-select it.

**Reorder photos** — click and drag a photo to a new position in the grid.

**Adjust thumbnail size** — drag the **Size** slider in the top-right corner to make
thumbnails larger or smaller.

**Select or deselect everything** — use the **Select All** and **Deselect All** buttons.

### Exporting

1. Make sure the photos you want have green borders.
2. Click **Export Selected**.
3. Choose a destination folder.
4. The app copies your selected photos there. The originals are never moved or deleted.
5. After export, the exported photos are removed from the grid. Any photos you did not
   export remain visible so you can export them separately if needed.

The header shows how many photos are selected: *"47 selected for export"*.

---

## Starting Over with a New Folder

Click **⟳ New Folder** in the top-right corner at any time to choose a different folder.
The button is dimmed while analysis is running — wait for the progress bar to finish first.

---

## Settings

Click **⚙ Settings** in the top-right corner to adjust how the program works.

| Setting | What it does |
|---------|-------------|
| **Burst gap (seconds)** | How close together in time two shots must be to count as a burst. Default is 1 second. Raise it if your camera shoots slowly; lower it if you shoot very fast. |
| **Sharpness weight** | How much focus sharpness counts toward the overall score. |
| **Exposure weight** | How much correct exposure counts toward the overall score. |
| **Face detection** | When on, the app focuses its sharpness test on detected faces rather than the whole image. Useful for portraits. |
| **Top tile %** | When face detection is off, the app tests sharpness using the top-scoring regions of the image. This controls what fraction of regions are included. |
| **Thumbnail size** | Default size of thumbnails in Stage 2. |
| **Worker threads** | How many parallel processes run during analysis. 0 = automatic (uses all available CPU cores). Reduce this if the app slows down your computer too much during analysis. |

---

## Understanding the Score Bars

Each photo gets three scores, shown as colored bars (0–100):

| Color | Meaning |
|-------|---------|
| **Green** | Good (65 or above) |
| **Yellow** | Acceptable (35–64) |
| **Red** | Poor (below 35) |

The **Sharp** bar is usually the most important — a blurry photo is rarely worth keeping
regardless of exposure. The **Score** bar combines both into a single number for easy
comparison.

---

## Tips for Best Results

- **Shoot RAW + JPEG?** Point the app at the JPEG folder for faster analysis, then use the
  filenames to locate the corresponding RAWs for export.
- **Very large folders (5,000+ photos)** will take a few minutes to analyze. The progress bar
  keeps you informed.
- **Face detection** improves accuracy for portraits but is slower. Turn it off in Settings
  for landscape or wildlife sessions where faces aren't the focus.
- **The comparison window** is most useful when several photos in a burst look nearly
  identical. Zoom in on the face or key subject and look at the Sharp bar to decide.
- The app **never deletes or moves** your original photos. Export always copies.

---

## Quick Reference Card

```
STAGE 1 — BURST REVIEW
  Space       Accept highlighted photo, next burst
  ← →         Move highlight left / right
  C           Compare all photos side by side
  A           Keep all photos in burst
  S           Skip burst
  Ctrl+click  Add photo to selection

STAGE 2 — FINAL SELECTION
  Click       Toggle photo in / out of export
  Drag        Reorder photos
  Export Selected → copies chosen photos to a folder you pick
```
