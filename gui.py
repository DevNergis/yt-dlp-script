import sys
import tempfile

import streamlink
import yt_dlp
from PySide6.QtCore import QThread, QObject, Signal, Slot, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
)
from qfluentwidgets import (
    FluentWindow,
    LineEdit,
    PrimaryPushButton,
    CheckBox,
    TextEdit,
    CardWidget,
    setTheme,
    Theme,
    BodyLabel,
    CaptionLabel,
    SwitchButton,
)


class Stream(QObject):
    """
    stdout, stderr의 출력을 캡처하여 signal로 보내는 클래스
    """

    new_text = Signal(str)

    def write(self, text):
        self.new_text.emit(str(text))

    def flush(self):
        pass


class Worker(QObject):
    """
    별도의 스레드에서 다운로드 작업을 처리하는 클래스
    """

    finished = Signal()
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, video_url, live, cookies_file):
        super().__init__()
        self.video_url = video_url
        self.live = live
        self.cookies_file = cookies_file

    @Slot()
    def run(self):
        """
        다운로드 작업을 시작합니다.
        """
        try:
            if self.live:
                self.progress.emit("라이브 모드: streamlink를 사용하여 다운로드합니다.")
                self.download_live_stream()
            else:
                self.progress.emit("일반 모드: yt-dlp를 사용하여 다운로드합니다.")
                self.download_video()
            self.progress.emit("✅ 다운로드 완료")
        except Exception as e:
            self.error.emit(f"❌ 오류 발생: {e}")
        finally:
            self.finished.emit()

    def download_video(self):
        """
        yt-dlp를 사용하여 비디오를 다운로드합니다.
        """
        temp_dir = tempfile.gettempdir()
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mkv",
            "downloader": "aria2c",
            "downloader_args": {"aria2c": ["--dir=" + temp_dir]},
            "live_from_start": True,
            "no_warnings": True,
        }
        if self.cookies_file:
            ydl_opts["cookiefile"] = self.cookies_file

        try:
            self.progress.emit("yt-dlp로 다운로드를 시작합니다...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.video_url])
        except yt_dlp.utils.DownloadError as e:
            raise RuntimeError(f"yt-dlp 다운로드 오류: {e}")
        except Exception as e:
            raise RuntimeError(f"예상치 못한 오류: {e}")

    def download_live_stream(self):
        """
        streamlink를 사용하여 라이브 스트림을 다운로드합니다.
        """
        title = "livestream"
        try:
            ydl_opts = {"quiet": True, "skip_download": True, "no_warnings": True}
            if self.cookies_file:
                ydl_opts["cookiefile"] = self.cookies_file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.video_url, download=False)
                title = info.get("title", "livestream")
        except Exception as e:
            self.progress.emit(
                f"경고: yt-dlp로 제목 가져오기 실패. 기본 파일명 사용. 오류: {e}"
            )

        session = streamlink.Streamlink()
        if self.cookies_file:
            session.set_option("http-cookie-file", self.cookies_file)

        streams = session.streams(self.video_url)
        if not streams:
            raise RuntimeError("스트림을 찾을 수 없습니다.")

        best_stream = streams["best"]
        self.progress.emit("최고 화질 스트림을 다운로드합니다...")

        safe_filename = (
            "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).rstrip()
            + ".ts"
        )
        self.progress.emit(f"파일 저장 경로: {safe_filename}")

        try:
            with best_stream.open() as fd, open(safe_filename, "wb") as f:
                while True:
                    chunk = fd.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception as e:
            raise RuntimeError(f"스트림 데이터 쓰기 중 오류 발생: {e}")


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.thread = None
        self.setWindowTitle("Video Downloader")
        self.setWindowIcon(QIcon("logo.ico"))
        self.setGeometry(100, 100, 700, 550)

        # Central widget and layout
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)
        # self.setCentralWidget(self.main_widget) # This line should be removed

        # --- Input Card ---
        self.input_card = CardWidget()
        self.input_layout = QVBoxLayout(self.input_card)

        self.url_input = LineEdit()
        self.url_input.setPlaceholderText("다운로드할 비디오 또는 스트림의 URL")
        self.input_layout.addWidget(BodyLabel(text="비디오 URL"))
        self.input_layout.addWidget(self.url_input)

        self.main_layout.addWidget(self.input_card)

        # --- Options Card ---
        self.options_card = CardWidget()
        self.options_layout = QVBoxLayout(self.options_card)

        # Live Stream Option
        self.live_checkbox = CheckBox(text="라이브 스트림")
        self.live_checkbox.setToolTip(
            "streamlink를 사용하여 라이브 스트림을 다운로드합니다."
        )
        self.options_layout.addWidget(self.live_checkbox)

        # Cookies Option
        cookies_layout = QHBoxLayout()
        self.cookies_button = PrimaryPushButton(text="쿠키 파일 선택")
        self.cookies_label = LineEdit()
        self.cookies_label.setPlaceholderText("쿠키 파일 경로 (선택 사항)")
        self.cookies_label.setReadOnly(True)
        cookies_layout.addWidget(self.cookies_button)
        cookies_layout.addWidget(self.cookies_label)
        self.options_layout.addLayout(cookies_layout)

        self.main_layout.addWidget(self.options_card)

        # --- Download Button ---
        self.download_button = PrimaryPushButton(text="다운로드")
        self.download_button.setMinimumHeight(40)
        self.main_layout.addWidget(self.download_button)

        # --- Status Area ---
        self.status_card = CardWidget()
        self.status_layout = QVBoxLayout(self.status_card)
        self.status_output = TextEdit()
        self.status_output.setReadOnly(True)
        self.status_layout.addWidget(BodyLabel(text="상태"))
        self.status_layout.addWidget(self.status_output)
        self.main_layout.addWidget(self.status_card, 1)  # Stretch status card

        # --- Theme Switcher ---
        theme_layout = QHBoxLayout()
        theme_layout.setAlignment(Qt.AlignRight)
        self.theme_label = CaptionLabel(text="Dark Mode")
        self.theme_switch = SwitchButton()
        self.theme_switch.setChecked(True)
        theme_layout.addWidget(self.theme_label)
        theme_layout.addWidget(self.theme_switch)
        self.main_layout.addLayout(theme_layout)

        # Add the main widget to the stacked widget
        self.stackedWidget.addWidget(self.main_widget)

        # Signals and Slots
        self.download_button.clicked.connect(self.start_download)
        self.cookies_button.clicked.connect(self.browse_cookies)
        self.theme_switch.checkedChanged.connect(self.toggle_theme)

        # Redirect stdout/stderr to status output
        sys.stdout = Stream(new_text=self.update_status)
        sys.stderr = Stream(new_text=self.update_status)

    @Slot()
    def start_download(self):
        video_url = self.url_input.text()
        if not video_url:
            self.update_status("비디오 URL을 입력하세요.")
            return

        self.download_button.setEnabled(False)
        self.status_output.clear()
        self.update_status("다운로드를 준비 중입니다...")

        self.thread = QThread()
        self.worker = Worker(
            video_url=video_url,
            live=self.live_checkbox.isChecked(),
            cookies_file=self.cookies_label.text() or None,
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(lambda: self.download_button.setEnabled(True))

        self.worker.progress.connect(self.update_status)
        self.worker.error.connect(self.update_status)

        self.thread.start()

    @Slot()
    def browse_cookies(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "쿠키 파일 선택", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.cookies_label.setText(file_path)

    @Slot(str)
    def update_status(self, text):
        self.status_output.append(text.strip())

    @Slot(bool)
    def toggle_theme(self, checked):
        if checked:
            setTheme(Theme.DARK)
            self.theme_label.setText("Dark Mode")
        else:
            setTheme(Theme.LIGHT)
            self.theme_label.setText("Light Mode")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
