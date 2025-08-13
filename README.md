## VideoClipper (Windows .exe)

VideoClipper is a simple Windows app to trim MP4 videos to a target file size (MB). No Python or ffmpeg install needed — the portable build includes everything required.

### Features
- Drag-and-drop a `.mp4` file or click Browse
- Set Start and End (supports `HH:MM:SS.mmm`, `MM:SS`, or seconds like `12.5`)
- Choose a target size in MB
- Exports `MP4 (H.264 + AAC)` to your `Downloads` folder
- Two-pass encoding to hit target size; auto downscales when needed to keep quality reasonable

### Download and run
- Download entire repository as a zip.
- Then run `VideoClipper\VideoClipper.exe`.

### How to use
1) Drag a `.mp4` onto the window (or click Browse).
2) Set Start/End. If End is empty, it defaults to the full duration.
3) Enter a Target Size (MB).
4) Optionally preview (if VLC is installed). Then click Export. The output appears in your `Downloads` folder.

### Requirements
- Windows 10/11
- No Python or ffmpeg install required for the .exe builds
- Optional: Install VLC (`https://www.videolan.org/vlc/`) for in-app preview

### Troubleshooting
- Windows SmartScreen: If warned about an unknown publisher, click “More info” → “Run anyway”.
- Failed to load Python DLL: Make sure you launched from the extracted `VideoClipper` folder (portable app) or via the installer, not from a `build` folder.
- Missing DLLs after unzip: Some antivirus tools quarantine files. Restore/allow the folder, re-extract the ZIP, and try again.
- No preview: Install VLC. Export works even without preview.

### Uninstall
- Delete the extracted `VideoClipper` folder.

### License
See `LICENSE`.


