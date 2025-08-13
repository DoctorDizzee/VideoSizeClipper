import os
import sys
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox

try:
	import ttkbootstrap as ttk
except Exception:  # Fallback to plain ttk if ttkbootstrap not available
	import tkinter.ttk as ttk  # type: ignore

try:
	from tkinterdnd2 import DND_FILES, TkinterDnD
	dnd_available = True
except Exception:
	DND_FILES = 'DND_Files'  # type: ignore
	TkinterDnD = None  # type: ignore
	dnd_available = False

try:
	import vlc  # type: ignore
	vlc_available = True
except Exception:
	vlc = None  # type: ignore
	vlc_available = False


def is_tool_on_path(tool_name: str) -> bool:
	return shutil.which(tool_name) is not None


def _prepend_to_path(dir_path: Path) -> None:
	os.environ["PATH"] = str(dir_path) + os.pathsep + os.environ.get("PATH", "")


def ensure_ff_tools_on_path() -> bool:
	# If already present, we're good
	if is_tool_on_path("ffmpeg") and is_tool_on_path("ffprobe"):
		return True
	# Try common Windows install locations and local folders
	exe_ffmpeg = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
	exe_ffprobe = "ffprobe.exe" if os.name == "nt" else "ffprobe"
	script_dir = Path(__file__).resolve().parent
	candidates = [
		script_dir,
		script_dir / "bin",
		script_dir / "ffmpeg",
		script_dir / "ffmpeg" / "bin",
		Path.home() / "Downloads" / "ffmpeg" / "bin",
		Path("C:/ffmpeg/bin"),
		Path("C:/Program Files/ffmpeg/bin"),
		Path("C:/Program Files (x86)/ffmpeg/bin"),
		Path("C:/ProgramData/chocolatey/bin"),
	]
	for d in candidates:
		try:
			if d and d.is_dir() and (d / exe_ffmpeg).exists() and (d / exe_ffprobe).exists():
				_prepend_to_path(d)
				if is_tool_on_path("ffmpeg") and is_tool_on_path("ffprobe"):
					return True
		except Exception:
			pass
	return False


def run_command(cmd: list[str]) -> Tuple[int, str, str]:
	process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
	out, err = process.communicate()
	return process.returncode, out, err


def parse_time_to_seconds(value: str) -> float:
	value = value.strip()
	if not value:
		return 0.0
	# Accept HH:MM:SS.mmm, MM:SS, or seconds
	if ":" in value:
		parts = value.split(":")
		parts = [p.strip() for p in parts]
		if len(parts) == 3:
			h, m, s = parts
			return float(h) * 3600 + float(m) * 60 + float(s)
		elif len(parts) == 2:
			m, s = parts
			return float(m) * 60 + float(s)
		else:
			raise ValueError("Invalid time format")
	return float(value)


def format_seconds_to_time(value: float) -> str:
	if value < 0:
		value = 0.0
	hours = int(value // 3600)
	minutes = int((value % 3600) // 60)
	seconds = value % 60
	if hours > 0:
		return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
	return f"{minutes:02d}:{seconds:06.3f}"


def ffprobe_duration_seconds(video_path: Path) -> Optional[float]:
	cmd = [
		"ffprobe",
		"-v",
		"error",
		"-select_streams",
		"v:0",
		"-show_entries",
		"format=duration",
		"-of",
		"json",
		str(video_path),
	]
	code, out, err = run_command(cmd)
	if code != 0:
		return None
	try:
		data = json.loads(out)
		dur = float(data.get("format", {}).get("duration", 0.0))
		return dur if dur > 0 else None
	except Exception:
		return None


def ffprobe_resolution_fps(video_path: Path) -> Tuple[Optional[int], Optional[int], Optional[float]]:
	cmd = [
		"ffprobe",
		"-v",
		"error",
		"-select_streams",
		"v:0",
		"-show_entries",
		"stream=width,height,avg_frame_rate",
		"-of",
		"json",
		str(video_path),
	]
	code, out, err = run_command(cmd)
	if code != 0:
		return None, None, None
	try:
		data = json.loads(out)
		stream = (data.get("streams") or [{}])[0]
		width = int(stream.get("width", 0)) or None
		height = int(stream.get("height", 0)) or None
		fr = stream.get("avg_frame_rate", "0/0")
		if fr and "/" in fr:
			num, den = fr.split("/")
			try:
				fps = float(num) / float(den) if float(den) != 0 else None
			except Exception:
				fps = None
		else:
			fps = None
		return width, height, fps
	except Exception:
		return None, None, None


def compute_target_bitrates(
	clip_seconds: float,
	target_size_mb: float,
	min_audio_kbps: int = 48,
	max_audio_kbps: int = 160,
	container_overhead_ratio: float = 0.98,
) -> Tuple[int, int]:
	# Estimate audio bitrate based on target size and length, clamped to [min, max]
	# Reserve a small portion for container overhead
	target_bits = target_size_mb * 1024 * 1024 * 8 * container_overhead_ratio
	# Start with heuristic: audio ~10% of total but within bounds
	audio_bits_guess = max(min(target_bits * 0.1, max_audio_kbps * 1000 * clip_seconds), min_audio_kbps * 1000 * clip_seconds)
	audio_kbps = max(min(int(audio_bits_guess / 1000 / clip_seconds), max_audio_kbps), min_audio_kbps)
	video_bits_available = max(target_bits - audio_kbps * 1000 * clip_seconds, 1000 * 1000)  # at least ~1 Mb total
	video_kbps = max(int(video_bits_available / 1000 / clip_seconds), 100)
	return video_kbps, audio_kbps


def choose_scaling_for_bitrate(width: Optional[int], height: Optional[int], fps: Optional[float], video_kbps: int) -> Optional[str]:
	# Keep a minimum bits-per-pixel target to avoid extreme artifacts.
	# bpp = (video_kbps * 1000) / (width * height * fps)
	if not width or not height or not fps or fps <= 0:
		return None
	bits_per_pixel = (video_kbps * 1000) / (width * height * fps)
	min_bpp = 0.06  # heuristic for H.264 acceptable quality at low bitrate
	if bits_per_pixel >= min_bpp:
		return None
	# Downscale until bpp threshold is reached (preserve aspect, even dims for H.264)
	scale_factor = math.sqrt(bits_per_pixel / min_bpp)
	new_w = max(160, int((width * scale_factor) // 2 * 2))
	new_h = max(160, int((height * scale_factor) // 2 * 2))
	if new_w < width and new_h < height:
		return f"scale={new_w}:{new_h}:flags=lanczos"
	return None


def build_two_pass_commands(
	src: Path,
	dst: Path,
	ss: Optional[float],
	duration: Optional[float],
	video_kbps: int,
	audio_kbps: int,
	scale_filter: Optional[str],
) -> Tuple[list[str], list[str]]:
	# First pass
	vf = ["-vf", scale_filter] if scale_filter else []
	range_args = []
	if ss is not None:
		range_args += ["-ss", f"{ss:.3f}"]
	if duration is not None:
		range_args += ["-t", f"{duration:.3f}"]
	logfile = str(dst.with_suffix(".log"))
	pass1 = [
		"ffmpeg",
		"-y",
		*range_args,
		"-i",
		str(src),
		*vf,
		"-c:v",
		"libx264",
		"-b:v",
		f"{video_kbps}k",
		"-pass",
		"1",
		"-preset",
		"medium",
		"-pix_fmt",
		"yuv420p",
		"-an",
		"-f",
		"mp4",
		"-passlogfile",
		logfile,
		"NUL" if os.name == "nt" else "/dev/null",
	]
	# Second pass
	pass2 = [
		"ffmpeg",
		"-y",
		*range_args,
		"-i",
		str(src),
		*vf,
		"-c:v",
		"libx264",
		"-b:v",
		f"{video_kbps}k",
		"-pass",
		"2",
		"-preset",
		"medium",
		"-pix_fmt",
		"yuv420p",
		"-c:a",
		"aac",
		"-b:a",
		f"{audio_kbps}k",
		"-movflags",
		"+faststart",
		"-passlogfile",
		logfile,
		str(dst),
	]
	return pass1, pass2


def human_readable_size(bytes_size: int) -> str:
	units = ["B", "KB", "MB", "GB"]
	size = float(bytes_size)
	unit_idx = 0
	while size >= 1024 and unit_idx < len(units) - 1:
		size /= 1024
		unit_idx += 1
	return f"{size:.2f} {units[unit_idx]}"


class VideoClipperApp:
	def __init__(self, root: tk.Tk):
		self.root = root
		self.root.title("VideoClipper - Size Target Trimmer")
		self.root.geometry("1000x720")

		self.src_path_var = tk.StringVar()
		self.start_var = tk.StringVar(value="0")
		self.end_var = tk.StringVar(value="")
		self.size_mb_var = tk.StringVar(value="10")

		self.status_var = tk.StringVar(value="Drop an MP4 or click Browse…" if dnd_available else "Click Browse to select an MP4…")

		self.player: Optional[object] = None
		self.vlc_instance: Optional[object] = None
		self.media_loaded_path: Optional[Path] = None
		self.video_duration_s: Optional[float] = None
		self.seeking_user = False
		self.loop_in_out = False
		self.is_dragging = False

		self.build_ui()
		self.bind_dnd()
		self.root.protocol("WM_DELETE_WINDOW", self.on_close)
		self.ensure_min_window_size()

	def build_ui(self) -> None:
		pad = 10
		frm = ttk.Frame(self.root, padding=pad)
		frm.pack(fill=tk.BOTH, expand=True)

		# File row
		file_row = ttk.Frame(frm)
		file_row.pack(fill=tk.X, pady=(0, pad))
		entry = ttk.Entry(file_row, textvariable=self.src_path_var)
		entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
		browse_btn = ttk.Button(file_row, text="Browse", command=self.on_browse)
		browse_btn.pack(side=tk.LEFT, padx=(pad // 2, 0))

		# Preview area
		preview = ttk.Labelframe(frm, text="Preview")
		preview.pack(fill=tk.BOTH, expand=True, pady=(0, pad))
		self.video_frame = tk.Frame(preview, bg="#000000", height=320)
		self.video_frame.pack(fill=tk.BOTH, expand=True)

		controls = ttk.Frame(preview)
		controls.pack(fill=tk.X, pady=(pad // 2, 0))
		self.play_btn = ttk.Button(controls, text="Play", command=self.on_play_pause)
		self.play_btn.pack(side=tk.LEFT)
		stop_btn = ttk.Button(controls, text="Stop", command=self.on_stop)
		stop_btn.pack(side=tk.LEFT, padx=(5, 10))
		in_btn = ttk.Button(controls, text="Set Start ⟵", command=self.on_set_in)
		in_btn.pack(side=tk.LEFT)
		out_btn = ttk.Button(controls, text="Set End ⟶", command=self.on_set_out)
		out_btn.pack(side=tk.LEFT, padx=(5, 10))
		loop_var = tk.BooleanVar(value=False)
		self.loop_var = loop_var
		loop_chk = ttk.Checkbutton(controls, text="Loop In–Out", variable=self.loop_var, command=self.on_toggle_loop)
		loop_chk.pack(side=tk.LEFT)

		self.pos_var = tk.DoubleVar(value=0.0)
		self.pos_scale = ttk.Scale(preview, from_=0.0, to=1.0, orient=tk.HORIZONTAL, variable=self.pos_var, command=self.on_seek)
		self.pos_scale.pack(fill=tk.X, padx=(2, 2), pady=(5, 0))
		# Bind once: handle drag start/end to avoid fighting with programmatic updates
		self.pos_scale.bind('<ButtonPress-1>', self._on_slider_press)
		self.pos_scale.bind('<ButtonRelease-1>', self._on_slider_release)

		self.time_label = ttk.Label(preview, text="00:00.000 / 00:00.000")
		self.time_label.pack(anchor=tk.E, padx=2)

		# Times
		time_row = ttk.Frame(frm)
		time_row.pack(fill=tk.X, pady=(0, pad))
		start_lbl = ttk.Label(time_row, text="Start")
		start_lbl.pack(side=tk.LEFT)
		start_entry = ttk.Entry(time_row, width=12, textvariable=self.start_var)
		start_entry.pack(side=tk.LEFT, padx=(5, pad))
		end_lbl = ttk.Label(time_row, text="End")
		end_lbl.pack(side=tk.LEFT)
		end_entry = ttk.Entry(time_row, width=12, textvariable=self.end_var)
		end_entry.pack(side=tk.LEFT, padx=(5, pad))

		# Size
		size_row = ttk.Frame(frm)
		size_row.pack(fill=tk.X, pady=(0, pad))
		size_lbl = ttk.Label(size_row, text="Target Size (MB)")
		size_lbl.pack(side=tk.LEFT)
		size_entry = ttk.Entry(size_row, width=10, textvariable=self.size_mb_var)
		size_entry.pack(side=tk.LEFT, padx=(5, pad))

		# Buttons
		btn_row = ttk.Frame(frm)
		btn_row.pack(fill=tk.X, pady=(0, pad))
		export_btn = ttk.Button(btn_row, text="Export", command=self.on_export)
		export_btn.pack(side=tk.LEFT)

		# Status
		status = ttk.Label(frm, textvariable=self.status_var, anchor=tk.W)
		status.pack(fill=tk.X)

		# Initialize VLC player if available
		self.init_player()
		self.root.after(100, self.update_playback_ui)

	def ensure_min_window_size(self) -> None:
		# Ensure the initial window is large enough to reveal bottom controls on various DPI scales
		try:
			self.root.update_idletasks()
			req_w = self.root.winfo_reqwidth()
			req_h = self.root.winfo_reqheight()
			# Set a minimum to at least the requested size
			self.root.minsize(req_w, req_h)
			# If current size is smaller than requested, bump it up
			cur_w = max(self.root.winfo_width(), req_w, 960)
			cur_h = max(self.root.winfo_height(), req_h, 640)
			self.root.geometry(f"{cur_w}x{cur_h}")
		except Exception:
			pass

	def bind_dnd(self) -> None:
		if dnd_available and hasattr(self.root, "drop_target_register"):
			try:
				self.root.drop_target_register(DND_FILES)
				self.root.dnd_bind('<<Drop>>', self.on_drop)
			except Exception:
				pass
		else:
			pass

	def on_drop(self, event):  # type: ignore[no-redef]
		data = getattr(event, "data", "")
		if not data:
			return
		try:
			# Use Tcl's list splitter to handle braces/quotes and spaces in file paths
			items = self.root.tk.splitlist(data)
		except Exception:
			items = [data]
		if not items:
			return
		path = str(items[0]).strip().strip('{}').strip('"')
		if path:
			p = Path(path)
			if not p.suffix and not p.exists():
				cand = p.with_suffix('.mp4')
				if cand.exists():
					p = cand
			self.src_path_var.set(str(p))
			self.status_var.set("Loaded file from drop")
			self.on_new_source_selected(p)

	def on_browse(self) -> None:
		path = filedialog.askopenfilename(filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")])
		if path:
			self.src_path_var.set(path)
			self.status_var.set("Selected file")
			self.on_new_source_selected(Path(path))

	def on_new_source_selected(self, p: Path) -> None:
		# Probe duration and set End default
		dur = ffprobe_duration_seconds(p)
		self.video_duration_s = dur
		if dur and not self.end_var.get().strip():
			self.end_var.set(format_seconds_to_time(dur))
		# Load into player
		self.load_media(p)

	def on_export(self) -> None:
		src = Path(self.src_path_var.get()).expanduser()
		if not src.exists():
			messagebox.showerror("Error", "Please select a valid source MP4 file.")
			return
		# Try to discover ffmpeg/ffprobe locally before failing
		ensure_ff_tools_on_path()
		if not is_tool_on_path("ffmpeg") or not is_tool_on_path("ffprobe"):
			messagebox.showerror("Error", "ffmpeg/ffprobe not found on PATH. Install ffmpeg and try again.")
			return
		try:
			start_s = parse_time_to_seconds(self.start_var.get()) if self.start_var.get().strip() else 0.0
		except Exception:
			messagebox.showerror("Error", "Invalid Start time format.")
			return
		end_raw = self.end_var.get().strip()
		if end_raw:
			try:
				end_s = parse_time_to_seconds(end_raw)
			except Exception:
				messagebox.showerror("Error", "Invalid End time format.")
				return
		else:
			video_dur = ffprobe_duration_seconds(src)
			end_s = video_dur if video_dur else None
		if end_s is not None and end_s < start_s:
			messagebox.showerror("Error", "End must be after Start.")
			return
		try:
			target_mb = float(self.size_mb_var.get())
			if target_mb <= 0:
				raise ValueError
		except Exception:
			messagebox.showerror("Error", "Target size must be a positive number.")
			return

		clip_seconds = (end_s - start_s) if (end_s is not None) else None
		if clip_seconds is None:
			# If End unknown, try to probe and compute
			video_dur = ffprobe_duration_seconds(src)
			if video_dur is None:
				messagebox.showerror("Error", "Could not determine video duration.")
				return
			clip_seconds = max(0.1, video_dur - start_s)
		else:
			clip_seconds = max(0.1, clip_seconds)

		video_w, video_h, fps = ffprobe_resolution_fps(src)
		video_kbps, audio_kbps = compute_target_bitrates(clip_seconds, target_mb)
		scale_filter = choose_scaling_for_bitrate(video_w, video_h, fps, video_kbps)

		downloads = Path.home() / "Downloads"
		downloads.mkdir(exist_ok=True)
		base_name = src.stem + f"_trim_{int(start_s)}-{int(end_s) if end_s is not None else 'end'}_{int(target_mb)}MB.mp4"
		dst = downloads / base_name

		self.status_var.set("Encoding (two-pass)… this may take a moment…")
		self.root.update_idletasks()

		# Downmix to mono at very small audio bitrates for better efficiency
		if audio_kbps <= 64:
			# Add channel param by modifying pass2 after construction
			pass
		pass1, pass2 = build_two_pass_commands(src, dst, start_s, clip_seconds, video_kbps, audio_kbps, scale_filter)
		if audio_kbps <= 64:
			# insert '-ac', '1' before output path
			insert_idx = len(pass2) - 1
			pass2[insert_idx:insert_idx] = ["-ac", "1"]
		code1, out1, err1 = run_command(pass1)
		if code1 != 0:
			messagebox.showerror("ffmpeg error (pass 1)", err1 or out1)
			return
		code2, out2, err2 = run_command(pass2)
		# Clean pass logs
		try:
			for ext in (".log", ".log.mbtree"):  # x264 files
				p = dst.with_suffix(ext)
				if p.exists():
					p.unlink(missing_ok=True)
		except Exception:
			pass
		if code2 != 0:
			messagebox.showerror("ffmpeg error (pass 2)", err2 or out2)
			return

		# Validate size
		try:
			final_size = dst.stat().st_size
			target_bytes = int(target_mb * 1024 * 1024)
			self.status_var.set(f"Done: {dst.name} ({human_readable_size(final_size)})")
			if abs(final_size - target_bytes) / max(target_bytes, 1) > 0.08:
				messagebox.showinfo("Note", "Size differs from target by more than ~8%. This can happen for very short clips or complex content.")
		except Exception:
			self.status_var.set("Done")

	def init_player(self) -> None:
		if not vlc_available:
			self.status_var.set(self.status_var.get() + "  (Install VLC for in-app preview)")
			return
		try:
			# Default to software decoding to avoid GPU/driver timestamp issues
			self._vlc_opts = ["--no-video-title-show", "--avcodec-hw=none"]
			self.vlc_instance = vlc.Instance(self._vlc_opts)
			self.player = self.vlc_instance.media_player_new()
			# Assign output to Tk frame
			self.root.update_idletasks()
			if os.name == "nt":
				self.player.set_hwnd(self.video_frame.winfo_id())
			else:
				self.player.set_xwindow(self.video_frame.winfo_id())  # type: ignore[attr-defined]
		except Exception:
			self.player = None
			self.vlc_instance = None
			self.status_var.set("Preview unavailable (VLC not detected)")

	def _recreate_player_with_fallback(self) -> None:
		# Try a more conservative video output if VLC reports errors
		try:
			# Release existing
			if self.player is not None:
				self.player.stop()
				self.player.release()
			if self.vlc_instance is not None:
				self.vlc_instance.release()
			# Add fallback opts
			fallback_opts = ["--no-video-title-show", "--avcodec-hw=none"]
			if os.name == "nt":
				# Force classic Win32 GDI output to avoid D3D issues
				fallback_opts.append("--vout=win32")
			self._vlc_opts = fallback_opts
			self.vlc_instance = vlc.Instance(self._vlc_opts)
			self.player = self.vlc_instance.media_player_new()
			self.root.update_idletasks()
			if os.name == "nt":
				self.player.set_hwnd(self.video_frame.winfo_id())
			else:
				self.player.set_xwindow(self.video_frame.winfo_id())  # type: ignore[attr-defined]
			# Reload current media if any
			if self.media_loaded_path is not None:
				media = self.vlc_instance.media_new(str(self.media_loaded_path))
				self.player.set_media(media)
				self.show_first_frame()
		except Exception:
			pass

	def load_media(self, path: Path) -> None:
		self.media_loaded_path = path
		if self.player is None or self.vlc_instance is None:
			return
		try:
			media = self.vlc_instance.media_new(str(path))
			self.player.set_media(media)
			self.player.stop()
			self.pos_var.set(0.0)
			# Display first frame after player primes
			self.show_first_frame()
		except Exception:
			pass

	def show_first_frame(self) -> None:
		# Try to display the very first frame upon loading
		if self.player is None:
			return
		try:
			# Start playback briefly to prime the decoder/output, then pause at 0
			self.player.play()
			self.root.after(200, self._pause_and_seek_start)
		except Exception:
			pass

	def _pause_and_seek_start(self) -> None:
		if self.player is None:
			return
		try:
			self.player.set_time(0)
			self.player.pause()
			self.play_btn.configure(text="Play")
			self.pos_var.set(0.0)
		except Exception:
			pass

	def on_play_pause(self) -> None:
		if self.player is None:
			return
		try:
			state = self.player.get_state()
			if state in (vlc.State.Playing, vlc.State.Opening, vlc.State.Buffering):
				self.player.pause()
				self.play_btn.configure(text="Play")
			else:
				self.player.play()
				self.play_btn.configure(text="Pause")
		except Exception:
			pass

	def on_stop(self) -> None:
		if self.player is None:
			return
		try:
			self.player.stop()
			self.play_btn.configure(text="Play")
			self.pos_var.set(0.0)
		except Exception:
			pass

	def on_set_in(self) -> None:
		pos_s = self.get_player_time_seconds()
		if pos_s is not None:
			self.start_var.set(format_seconds_to_time(pos_s))

	def on_set_out(self) -> None:
		pos_s = self.get_player_time_seconds()
		if pos_s is not None:
			self.end_var.set(format_seconds_to_time(pos_s))

	def on_toggle_loop(self) -> None:
		self.loop_in_out = bool(self.loop_var.get())

	def get_player_time_seconds(self) -> Optional[float]:
		if self.player is None:
			return None
		try:
			ms = self.player.get_time()
			if ms is None or ms < 0:
				return None
			return ms / 1000.0
		except Exception:
			return None

	def on_seek(self, _value: str) -> None:
		# Only seek while the user is dragging the thumb
		if self.player is None or not self.is_dragging:
			return
		try:
			val = max(0.0, min(1.0, float(_value)))
			self.player.set_position(val)
		except Exception:
			pass

	def _on_slider_press(self, _event) -> None:
		self.is_dragging = True

	def _on_slider_release(self, _event) -> None:
		# Finalize seek on release and resume programmatic updates
		if self.player is not None:
			try:
				val = max(0.0, min(1.0, float(self.pos_var.get())))
				self.player.set_position(val)
			except Exception:
				pass
		self.is_dragging = False

	def update_playback_ui(self) -> None:
		# Periodically update slider/time and handle loop
		try:
			if self.player is not None:
				# Update position slider from player state
				dur_s = self.video_duration_s
				cur_s = self.get_player_time_seconds()
				# Detect VLC error state and fallback to safer output
				try:
					state = self.player.get_state()
					if state == vlc.State.Error:
						self._recreate_player_with_fallback()
						return
				except Exception:
					pass
				if cur_s is not None:
					if dur_s and dur_s > 0 and not self.is_dragging:
						self.pos_var.set(max(0.0, min(1.0, cur_s / dur_s)))
					# Time label
					end_display = format_seconds_to_time(dur_s) if dur_s else (self.end_var.get() or "00:00.000")
					self.time_label.configure(text=f"{format_seconds_to_time(cur_s)} / {end_display}")
					# Loop handling
					if self.loop_in_out and not self.is_dragging:
						try:
							start_s = parse_time_to_seconds(self.start_var.get()) if self.start_var.get().strip() else 0.0
							end_s = parse_time_to_seconds(self.end_var.get()) if self.end_var.get().strip() else (dur_s or 0.0)
							if end_s > 0 and cur_s >= end_s:
								self.player.set_time(int(start_s * 1000))
						except Exception:
							pass
		except Exception:
			pass
		finally:
			self.root.after(100, self.update_playback_ui)

	def on_close(self) -> None:
		try:
			if self.player is not None:
				self.player.stop()
				self.player.release()
			if self.vlc_instance is not None:
				self.vlc_instance.release()
		except Exception:
			pass
		self.root.destroy()


def main() -> None:
	# Try to make ffmpeg available from common locations before UI starts
	try:
		ensure_ff_tools_on_path()
	except Exception:
		pass
	root = TkinterDnD.Tk() if dnd_available and TkinterDnD is not None else tk.Tk()
	app = VideoClipperApp(root)
	root.mainloop()


if __name__ == "__main__":
	main()


