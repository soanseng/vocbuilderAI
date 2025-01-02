#!/usr/bin/env python3
import os
import sys
import time
import atexit
import signal
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
ADDON_NAME = "voc_builder_ai"
ANKI_ADDONS_DIR = os.path.expanduser("~/.local/share/Anki2/addons21")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

class AnkiReloader(FileSystemEventHandler):
    def __init__(self):
        self.last_reload = 0
        self.anki_process = None
        self.setup_addon_symlink()
        self.start_anki()
        atexit.register(self.cleanup)

    def setup_addon_symlink(self):
        addon_path = os.path.join(ANKI_ADDONS_DIR, ADDON_NAME)
        if os.path.exists(addon_path):
            if os.path.islink(addon_path):
                os.unlink(addon_path)
            else:
                print(f"Warning: {addon_path} exists and is not a symlink")
                sys.exit(1)
        os.symlink(PROJECT_DIR, addon_path)
        print(f"Created symlink: {PROJECT_DIR} -> {addon_path}")

    def start_anki(self):
        if self.anki_process:
            self.anki_process.terminate()
            self.anki_process.wait()
        print("Starting Anki...")
        self.anki_process = subprocess.Popen(["anki"])

    def restart_anki(self):
        current_time = time.time()
        if current_time - self.last_reload < 2:  # Debounce reloads
            return
        self.last_reload = current_time
        print("\nRestarting Anki...")
        self.start_anki()

    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f"Detected change in {event.src_path}")
            self.restart_anki()

    def cleanup(self):
        print("\nCleaning up...")
        if self.anki_process:
            self.anki_process.terminate()
            self.anki_process.wait()
        addon_path = os.path.join(ANKI_ADDONS_DIR, ADDON_NAME)
        if os.path.islink(addon_path):
            os.unlink(addon_path)

def main():
    reloader = AnkiReloader()
    observer = Observer()
    observer.schedule(reloader, PROJECT_DIR, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
