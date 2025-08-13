## VideoClipper

Drag-and-drop MP4 trimmer that exports to a specific file size (MB) on Windows. Uses ffmpeg two-pass encoding, adjusts audio bitrate, and will downscale if needed to fit your target size while keeping the video playable.

### Features
- Drag-and-drop a `.mp4` file or browse
- Set start and end times for trimming (supports `HH:MM:SS.mmm`, `MM:SS`, or seconds like `12.5`)
- Choose a target size in MB
- Exports `MP4 (H.264 + AAC)` to your `Downloads` folder
- Uses 2-pass bitrate encoding to hit your target size; auto downscales if the bitrate is too low for the source resolution

### Requirements
- Windows 10/11
- Python 3.9+
- ffmpeg (and ffprobe) installed and on PATH
  - Download from `https://www.gyan.dev/ffmpeg/builds/` (or your preferred source)
  - Ensure `ffmpeg.exe` and `ffprobe.exe` are accessible in a terminal (`ffmpeg -version`)
 - Optional for drag-and-drop: `tkinterdnd2` (auto-installed via requirements)
 - Optional for preview player: `VLC` desktop app installed (`python-vlc` uses the system VLC libraries) DOWNLOAD HERE: https://www.videolan.org/vlc/

### Setup
1. Open a terminal in this folder
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   For preview, install VLC from `https://www.videolan.org/vlc/`.
3. Run the app:
   ```bash
   python app.py
   ```

### Usage
1. Drag a `.mp4` onto the window (or click Browse). If DnD is unavailable on your system, use Browse.
2. Adjust Start and End times (End defaults to the video duration)
3. Enter a Target Size (MB)
4. Use Play/Pause, the scrubber, and Set Start/Set End to pick the exact range
5. Click Export
5. The trimmed output will be saved to your `Downloads` folder

### Notes
- The final size should be very close to your target (two-pass helps). Container overhead and complexity may cause a small variance (typically within a few percent).
- The app may downscale the video to maintain a reasonable bits-per-pixel at low bitrates.
- Audio is encoded to AAC with an automatically chosen bitrate; at very small sizes, mono and lower bitrates may be used.


