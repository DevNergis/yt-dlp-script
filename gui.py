import sys
import tempfile
import yt_dlp
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QTextEdit
from PyQt6.QtCore import QThread, pyqtSignal

class DownloadThread(QThread):
    """
    A QThread that runs the yt-dlp download process.
    """
    download_finished = pyqtSignal(str)
    download_error = pyqtSignal(str)

    def __init__(self, video_url):
        super().__init__()
        self.video_url = video_url

    def run(self):
        """
        Runs the yt-dlp download.
        """
        try:
            temp_dir = tempfile.gettempdir()
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mkv',
                'downloader': 'aria2c',
                'downloader_args': {'aria2c': ['--dir=' + temp_dir]},
                'live_from_start': True,
                'no_warnings': True,
                'progress_hooks': [self.on_progress],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.video_url])
            
            self.download_finished.emit("Download finished successfully.")

        except yt_dlp.utils.DownloadError as e:
            self.download_error.emit(f"An error occurred during download: {e}")
        except Exception as e:
            self.download_error.emit(f"An unexpected error occurred: {e}")

    def on_progress(self, d):
        if d['status'] == 'finished':
            self.download_finished.emit(f"Finished downloading and converting {d['filename']}")

class MainWindow(QMainWindow):
    """
    The main window for the yt-dlp GUI.
    """
    def __init__(self):
        super().__init__()

        self.setWindowTitle("yt-dlp GUI")
        self.setGeometry(100, 100, 800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout(self.central_widget)

        # URL input
        self.url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter video URL")
        self.download_button = QPushButton("Download")
        self.url_layout.addWidget(self.url_input)
        self.url_layout.addWidget(self.download_button)
        self.layout.addLayout(self.url_layout)

        # Output console
        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        self.layout.addWidget(self.output_console)

        # Connect signals
        self.download_button.clicked.connect(self.start_download)

    def start_download(self):
        video_url = self.url_input.text()
        if not video_url:
            self.output_console.append("Please enter a video URL.")
            return

        self.output_console.clear()
        self.output_console.append(f"Starting download for: {video_url}")
        self.download_button.setEnabled(False)

        self.thread = DownloadThread(video_url)
        self.thread.download_finished.connect(self.on_download_finished)
        self.thread.download_error.connect(self.on_download_error)
        self.thread.start()

    def on_download_finished(self, message):
        self.output_console.append(message)
        self.download_button.setEnabled(True)

    def on_download_error(self, error_message):
        self.output_console.append(error_message)
        self.download_button.setEnabled(True)


def main():
    """
    Runs the PyQt application.
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
