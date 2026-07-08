#!/usr/bin/env python3
"""
YouTube Downloader - A powerful GUI application for downloading YouTube videos
Supports single video, playlists, batch downloads with multithreading
Uses yt-dlp (free, open-source)
"""

import os
import sys
import threading
import queue
from datetime import datetime
import customtkinter as ctk
from tkinter import filedialog, scrolledtext, StringVar
import logging

# Import yt-dlp
try:
    import yt_dlp
except ImportError:
    print("Installing yt-dlp...")
    os.system(f"{sys.executable} -m pip install yt-dlp")
    import yt_dlp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DownloadManager:
    """Manages downloads with multithreading support"""

    def __init__(self, output_path: str, max_threads: int = 4):
        self.output_path = output_path
        self.max_threads = max_threads
        self.download_queue = queue.Queue()
        self.download_threads = []
        self.is_running = False
        self.completed_count = 0
        self.failed_count = 0
        self.total_count = 0
        self.progress_callback = None
        self.status_callback = None

    def set_output_path(self, path: str):
        self.output_path = path
        os.makedirs(path, exist_ok=True)

    def add_to_queue(self, url: str, quality: str = "best", format_type: str = "mp4"):
        self.download_queue.put({
            'url': url,
            'quality': quality,
            'format_type': format_type,
            'status': 'pending'
        })

    def add_playlist_to_queue(self, playlist_url: str, quality: str = "best",
                               format_type: str = "mp4", start: int = 1, end: int = None):
        try:
            ydl_opts = {'quiet': True, 'extract_flat': 'in_playlist'}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                entries = info.get('entries', [])
                if end is None:
                    end = len(entries)
                for i, entry in enumerate(entries, 1):
                    if start <= i <= end:
                        video_url = f"https://www.youtube.com/watch?v={entry['id']}"
                        self.download_queue.put({
                            'url': video_url,
                            'quality': quality,
                            'format_type': format_type,
                            'playlist_index': i,
                            'playlist_total': len(entries),
                            'status': 'pending'
                        })
        except Exception as e:
            logger.error(f"Error extracting playlist: {e}")
            raise

    def start_workers(self):
        self.is_running = True
        self.download_threads = []
        for i in range(min(self.max_threads, self.download_queue.qsize() or 1)):
            thread = threading.Thread(target=self._worker, name=f"Worker-{i+1}", daemon=True)
            self.download_threads.append(thread)
            thread.start()

    def _worker(self):
        while self.is_running and not self.download_queue.empty():
            try:
                item = self.download_queue.get_nowait()
                self._download_video(item)
                self.download_queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")

    def _download_video(self, item: dict):
        url = item['url']
        quality = item['quality']
        format_type = item.get('format_type', 'mp4')
        playlist_index = item.get('playlist_index')

        os.makedirs(self.output_path, exist_ok=True)
        output_template = f"%(playlist_index)s - %(title)s.%(ext)s" if playlist_index else "%(title)s.%(ext)s"
        output_path = os.path.join(self.output_path, output_template)

        ydl_opts = {
            'format': self._get_format_string(quality, format_type),
            'outtmpl': output_path,
            'progress_hooks': [lambda d: self._progress_hook(d, item)],
            'retries': 3,
            'extractor_retries': 3,
        }

        if format_type in ['mp3', 'wav']:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type,
                'preferredquality': quality if quality.isdigit() else '192',
            }]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                item['status'] = 'completed'
                item['title'] = info.get('title', 'Unknown')
                self.completed_count += 1
                if self.status_callback:
                    self.status_callback(f"✓ Completed: {info.get('title', 'Unknown')}")
        except Exception as e:
            item['status'] = 'failed'
            item['error'] = str(e)
            self.failed_count += 1
            if self.status_callback:
                self.status_callback(f"✗ Failed: {url} - {str(e)}")

    def _get_format_string(self, quality: str, format_type: str) -> str:
        if format_type in ['mp3', 'wav']:
            return 'bestaudio/best'
        if quality == "best":
            return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        elif quality == "1080p":
            return 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best'
        elif quality == "720p":
            return 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best'
        elif quality == "480p":
            return 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best'
        elif quality == "360p":
            return 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best'
        else:
            return 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

    def _progress_hook(self, d: dict, item: dict):
        if d['status'] == 'downloading' and self.progress_callback:
            total = d.get('total_bytes', 1)
            downloaded = d.get('downloaded_bytes', 0)
            progress = (downloaded / total) * 100 if total else 0
            self.progress_callback({
                'progress': progress,
                'total': total,
                'downloaded': downloaded,
                'item': item
            })

    def wait_for_completion(self):
        self.download_queue.join()
        self.is_running = False


class YouTubeDownloaderGUI:
    def __init__(self):
        self.app = ctk.CTk()
        self.app.title("YouTube Downloader - Pro Edition")
        self.app.geometry("900x700")
        self.app.minsize(800, 600)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.download_path = os.path.expanduser("~/Documents/YoutubeDownloader")
        os.makedirs(self.download_path, exist_ok=True)

        self.max_threads = 4
        self.current_quality = StringVar(value="1080p")
        self.current_format = StringVar(value="mp4")
        self.download_manager = None
        self.is_downloading = False
        self.batch_button = None  # Will hold the batch file button when in batch mode

        self.setup_ui()

    def setup_ui(self):
        self.app.grid_rowconfigure(0, weight=1)
        self.app.grid_columnconfigure(0, weight=1)

        main_frame = ctk.CTkFrame(self.app, fg_color="#1a1a2e", corner_radius=15)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_frame.grid_rowconfigure(6, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        # Header
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        title_label = ctk.CTkLabel(header_frame, text="🎬 YouTube Downloader Pro",
                                   font=ctk.CTkFont(size=24, weight="bold"), text_color="#e94560")
        title_label.pack(side="left")
        settings_btn = ctk.CTkButton(header_frame, text="⚙️", width=40, height=40,
                                     corner_radius=20, command=self.show_settings)
        settings_btn.pack(side="right")

        # URL Input Section - ALWAYS VISIBLE (except in batch mode we replace it temporarily)
        input_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        input_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 20))
        input_frame.grid_columnconfigure(1, weight=1)

        url_label = ctk.CTkLabel(input_frame, text="URL:", font=ctk.CTkFont(weight="bold"))
        url_label.grid(row=0, column=0, sticky="w", pady=5)

        self.url_entry = ctk.CTkEntry(input_frame, placeholder_text="Enter YouTube URL...",
                                      height=45, font=ctk.CTkFont(size=14))
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.url_entry.bind('<Return>', lambda e: self.process_url())

        # Mode selection
        mode_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        mode_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 15))

        mode_label = ctk.CTkLabel(mode_frame, text="Mode:", font=ctk.CTkFont(weight="bold"))
        mode_label.pack(side="left", padx=(0, 10))

        self.mode_var = StringVar(value="single")
        modes = [("Single Video", "single"), ("Playlist", "playlist"), ("Batch (File)", "batch")]
        for text, value in modes:
            rb = ctk.CTkRadioButton(mode_frame, text=text, variable=self.mode_var,
                                    value=value, command=self.update_ui_for_mode)
            rb.pack(side="left", padx=10)

        # Options frame
        options_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        options_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(5, 15))
        options_frame.grid_columnconfigure(1, weight=1)

        quality_label = ctk.CTkLabel(options_frame, text="Quality:", font=ctk.CTkFont(weight="bold"))
        quality_label.grid(row=0, column=0, sticky="w", pady=5)
        quality_options = ["1080p", "720p", "480p", "360p", "Best"]
        self.quality_combo = ctk.CTkComboBox(options_frame, values=quality_options,
                                             variable=self.current_quality, width=100)
        self.quality_combo.grid(row=0, column=1, sticky="w", padx=(10, 30))

        format_label = ctk.CTkLabel(options_frame, text="Format:", font=ctk.CTkFont(weight="bold"))
        format_label.grid(row=0, column=2, sticky="w", pady=5)
        format_options = ["mp4", "mp3", "wav"]
        self.format_combo = ctk.CTkComboBox(options_frame, values=format_options,
                                            variable=self.current_format, width=80)
        self.format_combo.grid(row=0, column=3, sticky="w", padx=(10, 0))

        path_label = ctk.CTkLabel(options_frame, text="Save to:", font=ctk.CTkFont(weight="bold"))
        path_label.grid(row=1, column=0, sticky="w", pady=5)
        self.path_entry = ctk.CTkEntry(options_frame, height=30)
        self.path_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(10, 10))
        self.path_entry.insert(0, self.download_path)
        path_btn = ctk.CTkButton(options_frame, text="📁", width=40, height=30, command=self.browse_folder)
        path_btn.grid(row=1, column=3, sticky="e", padx=(5, 0))

        # Playlist range frame (hidden by default)
        self.playlist_range_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        self.playlist_range_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=(10, 0), pady=(10, 0))
        self.playlist_range_frame.grid_columnconfigure(3, weight=1)
        range_label = ctk.CTkLabel(self.playlist_range_frame, text="Range:", font=ctk.CTkFont(weight="bold"))
        range_label.grid(row=0, column=0, sticky="w")
        self.start_entry = ctk.CTkEntry(self.playlist_range_frame, placeholder_text="Start", width=60)
        self.start_entry.grid(row=0, column=1, padx=(5, 5))
        self.start_entry.insert(0, "1")
        self.end_entry = ctk.CTkEntry(self.playlist_range_frame, placeholder_text="End", width=60)
        self.end_entry.grid(row=0, column=2, padx=(5, 10))
        self.playlist_range_frame.grid_remove()  # Initially hidden

        # Download button
        self.download_btn = ctk.CTkButton(main_frame, text="⬇ Download Now",
                                          font=ctk.CTkFont(size=16, weight="bold"), height=50,
                                          command=self.start_download, fg_color="#e94560", hover_color="#c73e54")
        self.download_btn.grid(row=4, column=0, sticky="ew", padx=20, pady=(10, 20))

        # Progress area
        progress_container = ctk.CTkFrame(main_frame, fg_color="transparent")
        progress_container.grid(row=5, column=0, sticky="ew", padx=20, pady=(5, 10))
        progress_container.grid_columnconfigure(0, weight=1)

        self.progress_label = ctk.CTkLabel(progress_container, text="Ready to download", font=ctk.CTkFont(size=12))
        self.progress_label.grid(row=0, column=0, sticky="w")
        self.progress_bar = ctk.CTkProgressBar(progress_container, height=10)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.progress_bar.set(0)

        status_frame = ctk.CTkFrame(progress_container, fg_color="transparent")
        status_frame.grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.status_label = ctk.CTkLabel(status_frame, text="0/0 completed", font=ctk.CTkFont(size=11, weight="bold"))
        self.status_label.pack(side="left", padx=(0, 20))
        self.cancel_btn = ctk.CTkButton(status_frame, text="✖ Cancel", font=ctk.CTkFont(size=12), height=25,
                                        command=self.cancel_download, fg_color="#5a5a5a", hover_color="#7a7a7a")
        self.cancel_btn.pack(side="left")
        self.cancel_btn.configure(state="disabled")

        # Log area
        log_frame = ctk.CTkFrame(main_frame, fg_color="#16213e", corner_radius=10)
        log_frame.grid(row=6, column=0, sticky="nsew", padx=20, pady=(5, 20))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, bg="#0f0f1b", fg="#00ff88",
                                                  font=("Consolas", 10), relief="flat", wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        clear_btn = ctk.CTkButton(log_frame, text="Clear Log", font=ctk.CTkFont(size=10), height=25, command=self.clear_log)
        clear_btn.grid(row=1, column=0, sticky="e", padx=10, pady=5)

        # Status bar
        status_bar = ctk.CTkFrame(self.app, fg_color="#111", height=25)
        status_bar.grid(row=1, column=0, sticky="ew")
        self.thread_count_label = ctk.CTkLabel(status_bar, text=f"Threads: {self.max_threads}", font=ctk.CTkFont(size=10))
        self.thread_count_label.pack(side="left", padx=15)

        # Final UI initialization
        self.update_ui_for_mode()

    def update_ui_for_mode(self):
        """Handle mode switching: show/hide playlist range and batch file button"""
        mode = self.mode_var.get()

        # Playlist range visibility
        if mode == "playlist":
            self.playlist_range_frame.grid()
        else:
            self.playlist_range_frame.grid_remove()

        # Batch mode: replace URL entry with file selection button
        if mode == "batch":
            # Hide the URL entry
            self.url_entry.grid_remove()
            # Create batch button if not exists, else show it
            if self.batch_button is None:
                # Create button in the same parent frame (input_frame)
                self.batch_button = ctk.CTkButton(
                    self.url_entry.master,
                    text="📂 Select Batch File",
                    command=self.select_batch_file,
                    height=45,
                    font=ctk.CTkFont(size=14)
                )
                self.batch_button.grid(row=0, column=1, sticky="ew", padx=(10, 0))
            else:
                self.batch_button.grid()
        else:
            # Single or Playlist mode: show URL entry, hide batch button
            self.url_entry.grid(row=0, column=1, sticky="ew", padx=(10, 0))
            if self.batch_button is not None:
                self.batch_button.grid_remove()
            # Clear any previously loaded batch file
            if hasattr(self, 'batch_file'):
                delattr(self, 'batch_file')

    def select_batch_file(self):
        file_path = filedialog.askopenfilename(
            title="Select file with URLs",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.batch_file = file_path
            self.log(f"Loaded batch file: {file_path}")

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_path, title="Select Download Folder")
        if folder:
            self.download_path = folder
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)

    def show_settings(self):
        settings = ctk.CTkToplevel(self.app)
        settings.title("Settings")
        settings.geometry("400x300")
        settings.transient(self.app)
        settings.grab_set()

        content = ctk.CTkFrame(settings, fg_color="transparent")
        content.pack(padx=20, pady=20, fill="both", expand=True)

        threads_label = ctk.CTkLabel(content, text="Max Threads:", font=ctk.CTkFont(weight="bold"))
        threads_label.grid(row=0, column=0, sticky="w", pady=10)
        threads_scale = ctk.CTkSlider(content, from_=1, to=8, number_of_steps=7)
        threads_scale.set(self.max_threads)
        threads_scale.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        threads_value_label = ctk.CTkLabel(content, text=str(self.max_threads))
        threads_value_label.grid(row=0, column=2, padx=10)

        def update_threads(value):
            val = int(float(value))
            threads_value_label.configure(text=str(val))
            self.max_threads = val
            self.thread_count_label.configure(text=f"Threads: {val}")

        threads_scale.configure(command=update_threads)

        path_label = ctk.CTkLabel(content, text="Default Path:", font=ctk.CTkFont(weight="bold"))
        path_label.grid(row=1, column=0, sticky="w", pady=10)
        path_display = ctk.CTkEntry(content, text_color="#aaa")
        path_display.grid(row=1, column=1, sticky="ew", pady=10)
        path_display.insert(0, self.download_path)

        def change_path():
            folder = filedialog.askdirectory(initialdir=self.download_path)
            if folder:
                path_display.delete(0, "end")
                path_display.insert(0, folder)
                self.download_path = folder

        path_btn = ctk.CTkButton(content, text="Browse", command=change_path, width=80)
        path_btn.grid(row=1, column=2, padx=(10, 0))

        close_btn = ctk.CTkButton(settings, text="Close", command=settings.destroy)
        close_btn.pack(pady=20)

    def process_url(self):
        url = self.url_entry.get().strip()
        if not url:
            self.log("Error: Please enter a URL")
            return

        self.log(f"Processing: {url}")
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    title = info.get('title', 'Unknown Playlist')
                    entry_count = len(info['entries'])
                    self.log(f"Playlist found: {title}")
                    self.log(f"Total videos: {entry_count}")
                else:
                    title = info.get('title', 'Unknown')
                    duration = info.get('duration', 0)
                    duration_str = f"{duration // 60}:{duration % 60:02d}"
                    self.log(f"Video found: {title}")
                    self.log(f"Duration: {duration_str}")
                    self.log(f"Views: {info.get('view_count', 'N/A')}")
        except Exception as e:
            self.log(f"Error processing URL: {e}")

    def start_download(self):
        if self.is_downloading:
            self.log("Download already in progress!")
            return

        mode = self.mode_var.get()
        url = self.url_entry.get().strip()

        if mode != "batch" and not url:
            self.log("Error: Please enter a URL")
            return
        if mode == "batch" and not hasattr(self, 'batch_file'):
            self.log("Error: No batch file selected")
            return

        self.download_path = self.path_entry.get().strip()
        os.makedirs(self.download_path, exist_ok=True)

        self.download_manager = DownloadManager(self.download_path, max_threads=self.max_threads)
        self.download_manager.progress_callback = self.update_progress
        self.download_manager.status_callback = self.update_status

        self.is_downloading = True
        self.download_btn.configure(state="disabled", text="⬇ Downloading...")
        self.cancel_btn.configure(state="normal")

        if mode == "batch":
            self._download_batch()
        elif mode == "playlist":
            self._download_playlist(url)
        else:
            self._download_single(url)

    def _download_single(self, url: str):
        self.log(f"Starting download: {url}")
        self.download_manager.total_count = 1
        quality = self.current_quality.get()
        format_type = self.current_format.get()
        self.download_manager.add_to_queue(url, quality, format_type)
        self.download_manager.start_workers()
        threading.Thread(target=self._monitor_download, daemon=True).start()

    def _download_playlist(self, url: str):
        self.log(f"Starting playlist download: {url}")
        quality = self.current_quality.get()
        format_type = self.current_format.get()
        start = int(self.start_entry.get() or 1)
        end_input = self.end_entry.get()
        end = int(end_input) if end_input else None
        try:
            self.download_manager.add_playlist_to_queue(url, quality, format_type, start, end)
            self.download_manager.total_count = len(self.download_manager.download_queue.queue)
            self.log(f"Added {self.download_manager.total_count} videos to queue")
            self.download_manager.start_workers()
            threading.Thread(target=self._monitor_download, daemon=True).start()
        except Exception as e:
            self.log(f"Error adding playlist: {e}")
            self._finish_download()

    def _download_batch(self):
        batch_file = getattr(self, 'batch_file', None)
        if not batch_file:
            self.log("Error: No batch file selected")
            self._finish_download()
            return
        self.log(f"Starting batch download from: {batch_file}")
        try:
            with open(batch_file, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
            if not urls:
                self.log("Error: No URLs found in batch file")
                self._finish_download()
                return
            self.download_manager.total_count = len(urls)
            self.log(f"Found {len(urls)} URLs in batch file")
            quality = self.current_quality.get()
            format_type = self.current_format.get()
            for url in urls:
                self.download_manager.add_to_queue(url, quality, format_type)
            self.download_manager.start_workers()
            threading.Thread(target=self._monitor_download, daemon=True).start()
        except Exception as e:
            self.log(f"Error reading batch file: {e}")
            self._finish_download()

    def _monitor_download(self):
        self.download_manager.wait_for_completion()
        self._finish_download()

    def _finish_download(self):
        self.is_downloading = False
        self.download_btn.configure(state="normal", text="⬇ Download Now")
        self.cancel_btn.configure(state="disabled")
        total = self.download_manager.total_count if self.download_manager else 0
        completed = self.download_manager.completed_count if self.download_manager else 0
        failed = self.download_manager.failed_count if self.download_manager else 0
        self.log("=" * 50)
        self.log(f"Download Complete! Total: {total} | Completed: {completed} | Failed: {failed}")
        self.log("=" * 50)

    def cancel_download(self):
        if self.download_manager:
            self.download_manager.is_running = False
            self.log("Download cancelled by user")
        self._finish_download()

    def update_progress(self, data: dict):
        if self.download_manager:
            total = self.download_manager.total_count or 1
            completed = self.download_manager.completed_count
            failed = self.download_manager.failed_count
            progress = (completed + failed) / total
            self.progress_bar.set(progress)
            self.status_label.configure(text=f"{completed + failed}/{total} | Completed: {completed} | Failed: {failed}")

    def update_status(self, message: str):
        self.log(message)

    def log(self, message: str):
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.configure(state="disabled")
        self.log("Log cleared")

    def run(self):
        self.app.mainloop()


def main():
    try:
        import yt_dlp
    except ImportError:
        print("Installing yt-dlp...")
        os.system(f"{sys.executable} -m pip install yt-dlp")
    app = YouTubeDownloaderGUI()
    app.run()


if __name__ == "__main__":
    main()