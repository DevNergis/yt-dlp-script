import sys
import tempfile
import asyncio
import json
import datetime
import random
import aiohttp

import streamlink
import yt_dlp
import websockets
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
    FluentIcon,
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
        except Exception as e:
            raise RuntimeError(f"yt-dlp 다운로드 오류: {e}")

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


class ChatWorker(QObject):
    """
    별도의 스레드에서 치지직 채팅 수신을 처리하는 클래스
    """

    finished = Signal()
    error = Signal(str)
    chat_message = Signal(str)
    status_message = Signal(str)

    def __init__(self, channel_id, save_to_file=False, file_path="chat.txt"):
        super().__init__()
        self.channel_id = channel_id
        self.save_to_file = save_to_file
        self.file_path = file_path
        self.running = True
        self.file_handle = None

    @Slot()
    def run(self):
        """
        채팅 수신을 시작합니다.
        """
        try:
            asyncio.run(self._async_run())
        except Exception as e:
            self.error.emit(f"❌ 오류 발생: {e}")
        finally:
            self.finished.emit()

    async def _async_run(self):
        """
        비동기로 채팅을 수신합니다.
        """
        try:
            # chatChannelId 가져오기
            chat_channel_id = await self._get_chat_channel_id()
            if not chat_channel_id:
                self.error.emit("라이브 중이 아니거나, chatChannelId를 찾을 수 없습니다.")
                return

            # 파일 열기 (저장 옵션이 활성화된 경우)
            if self.save_to_file:
                self.file_handle = open(self.file_path, "a", encoding="utf-8")

            # 웹소켓 연결 (재연결 로직 포함)
            while self.running:
                try:
                    await self._connect_to_websocket(chat_channel_id)
                except Exception as e:
                    if self.running:
                        self.status_message.emit(f"연결 끊김. 5초 후 재연결... ({e})")
                        await asyncio.sleep(5)
                    else:
                        break

        finally:
            if self.file_handle:
                self.file_handle.close()

    async def _get_chat_channel_id(self):
        """
        API를 통해 chatChannelId를 가져옵니다.
        """
        api_url = f"https://api.chzzk.naver.com/polling/v2/channels/{self.channel_id}/live-status"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    content = data.get("content", {})
                    return content.get("chatChannelId")
        except Exception as e:
            self.error.emit(f"API 요청 중 오류: {e}")
            return None

    async def _connect_to_websocket(self, chat_channel_id):
        """
        웹소켓에 연결하여 채팅을 수신합니다.
        """
        uri = f"wss://kr-ss{random.randint(1, 10)}.chat.naver.com/chat"
        self.status_message.emit(f"웹소켓 연결 중: {uri}")

        async with websockets.connect(
            uri,
            user_agent_header="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
            origin="https://chzzk.naver.com",
        ) as websocket:
            self.status_message.emit("✅ 웹소켓 연결 성공")

            # 초기 연결 메시지
            connect_message = {
                "ver": "3",
                "cmd": 100,
                "svcid": "game",
                "cid": chat_channel_id,
                "bdy": {
                    "uid": None,
                    "devType": 2001,
                    "accTkn": "",
                    "auth": "READ",
                    "libVer": "4.9.3",
                    "osVer": "Windows/10",
                    "devName": "Mozilla Firefox/140.0",
                    "locale": "ko-KR",
                    "timezone": "Asia/Seoul",
                },
                "tid": 1,
            }
            await websocket.send(json.dumps(connect_message))
            await websocket.recv()  # 첫 번째 응답 무시

            # 채팅 수신 루프
            while self.running:
                message_str = await websocket.recv()
                message = json.loads(message_str)

                # 서버 PING 메시지에 대한 PONG 응답
                if message.get("cmd") == 0:
                    await websocket.send('{"ver": "2", "cmd": 10000}')
                    continue

                # 채팅 메시지 처리
                chat_data = message.get("bdy", [])
                for chat in chat_data:
                    await self._process_chat(chat)

    async def _process_chat(self, chat):
        """
        개별 채팅 메시지를 처리합니다.
        """
        try:
            msg_time_ms = chat.get("msgTime")
            msg = chat.get("msg")

            if not msg_time_ms or not msg:
                return

            profile_json = json.loads(chat.get("profile", "{}"))
            nickname = profile_json.get("nickname", "익명")

            extras_json = json.loads(chat.get("extras", "{}"))
            os_type = extras_json.get("osType")
            pay_amount = extras_json.get("payAmount")

            # 타임스탬프 포맷팅
            dt_object = datetime.datetime.fromtimestamp(msg_time_ms / 1000)
            formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
            os_info = f" ({os_type})" if os_type else ""

            # 메시지 포맷팅
            if pay_amount and pay_amount > 0:
                log_message = f"[{formatted_time}] {nickname}{os_info} ({pay_amount}원 후원): {msg}"
            else:
                log_message = f"[{formatted_time}] {nickname}{os_info}: {msg}"

            # 채팅 표시
            self.chat_message.emit(log_message)

            # 파일 저장
            if self.file_handle:
                self.file_handle.write(log_message + "\n")
                self.file_handle.flush()

        except Exception:
            pass

    def stop(self):
        """
        채팅 수신을 중지합니다.
        """
        self.running = False



class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.thread = None
        self.chat_worker = None
        self.chat_thread = None
        self.setWindowTitle("Video Downloader & Chat Viewer")
        self.setWindowIcon(QIcon("logo.ico"))
        self.setGeometry(100, 100, 800, 600)

        # 다운로더 탭 생성
        self.create_downloader_tab()
        
        # 채팅 뷰어 탭 생성
        self.create_chat_viewer_tab()

        # 네비게이션 인터페이스 추가
        self.addSubInterface(self.downloader_widget, FluentIcon.DOWNLOAD, "다운로더")
        self.addSubInterface(self.chat_widget, FluentIcon.CHAT, "채팅 뷰어")

        # Redirect stdout/stderr to status output
        sys.stdout = Stream()
        sys.stdout.new_text.connect(self.update_download_status)
        sys.stderr = Stream()
        sys.stderr.new_text.connect(self.update_download_status)

    def create_downloader_tab(self):
        """다운로더 탭을 생성합니다."""
        self.downloader_widget = QWidget()
        self.downloader_widget.setObjectName("downloader")
        main_layout = QVBoxLayout(self.downloader_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- Input Card ---
        input_card = CardWidget()
        input_layout = QVBoxLayout(input_card)

        self.url_input = LineEdit()
        self.url_input.setPlaceholderText("다운로드할 비디오 또는 스트림의 URL")
        input_layout.addWidget(BodyLabel(text="비디오 URL"))
        input_layout.addWidget(self.url_input)

        main_layout.addWidget(input_card)

        # --- Options Card ---
        options_card = CardWidget()
        options_layout = QVBoxLayout(options_card)

        # Live Stream Option
        self.live_checkbox = CheckBox(text="라이브 스트림")
        self.live_checkbox.setToolTip(
            "streamlink를 사용하여 라이브 스트림을 다운로드합니다."
        )
        options_layout.addWidget(self.live_checkbox)

        # Cookies Option
        cookies_layout = QHBoxLayout()
        self.cookies_button = PrimaryPushButton(text="쿠키 파일 선택")
        self.cookies_label = LineEdit()
        self.cookies_label.setPlaceholderText("쿠키 파일 경로 (선택 사항)")
        self.cookies_label.setReadOnly(True)
        cookies_layout.addWidget(self.cookies_button)
        cookies_layout.addWidget(self.cookies_label)
        options_layout.addLayout(cookies_layout)

        main_layout.addWidget(options_card)

        # --- Download Button ---
        self.download_button = PrimaryPushButton(text="다운로드")
        self.download_button.setMinimumHeight(40)
        main_layout.addWidget(self.download_button)

        # --- Status Area ---
        status_card = CardWidget()
        status_layout = QVBoxLayout(status_card)
        self.status_output = TextEdit()
        self.status_output.setReadOnly(True)
        status_layout.addWidget(BodyLabel(text="상태"))
        status_layout.addWidget(self.status_output)
        main_layout.addWidget(status_card, 1)  # Stretch status card

        # --- Theme Switcher ---
        theme_layout = QHBoxLayout()
        theme_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.theme_label = CaptionLabel(text="Dark Mode")
        self.theme_switch = SwitchButton()
        self.theme_switch.setChecked(True)
        theme_layout.addWidget(self.theme_label)
        theme_layout.addWidget(self.theme_switch)
        main_layout.addLayout(theme_layout)

        # Signals and Slots
        self.download_button.clicked.connect(self.start_download)
        self.cookies_button.clicked.connect(self.browse_cookies)
        self.theme_switch.checkedChanged.connect(self.toggle_theme)

    def create_chat_viewer_tab(self):
        """채팅 뷰어 탭을 생성합니다."""
        self.chat_widget = QWidget()
        self.chat_widget.setObjectName("chat_viewer")
        main_layout = QVBoxLayout(self.chat_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- Channel ID Input Card ---
        input_card = CardWidget()
        input_layout = QVBoxLayout(input_card)

        self.channel_id_input = LineEdit()
        self.channel_id_input.setPlaceholderText("치지직 채널 ID 입력 (예: affa78...)")
        input_layout.addWidget(BodyLabel(text="채널 ID"))
        input_layout.addWidget(self.channel_id_input)

        main_layout.addWidget(input_card)

        # --- Chat Options Card ---
        options_card = CardWidget()
        options_layout = QVBoxLayout(options_card)

        # Save to file option
        self.save_chat_checkbox = CheckBox(text="채팅을 파일로 저장")
        self.save_chat_checkbox.setChecked(True)
        options_layout.addWidget(self.save_chat_checkbox)

        # File path selection
        file_layout = QHBoxLayout()
        self.chat_file_button = PrimaryPushButton(text="저장 경로 선택")
        self.chat_file_label = LineEdit()
        self.chat_file_label.setText("chat.txt")
        self.chat_file_label.setPlaceholderText("채팅 저장 파일 경로")
        file_layout.addWidget(self.chat_file_button)
        file_layout.addWidget(self.chat_file_label)
        options_layout.addLayout(file_layout)

        main_layout.addWidget(options_card)

        # --- Control Buttons ---
        button_layout = QHBoxLayout()
        self.start_chat_button = PrimaryPushButton(text="채팅 뷰어 시작")
        self.start_chat_button.setMinimumHeight(40)
        self.stop_chat_button = PrimaryPushButton(text="중지")
        self.stop_chat_button.setMinimumHeight(40)
        self.stop_chat_button.setEnabled(False)
        button_layout.addWidget(self.start_chat_button)
        button_layout.addWidget(self.stop_chat_button)
        main_layout.addLayout(button_layout)

        # --- Chat Display Area ---
        chat_card = CardWidget()
        chat_layout = QVBoxLayout(chat_card)
        self.chat_output = TextEdit()
        self.chat_output.setReadOnly(True)
        chat_layout.addWidget(BodyLabel(text="채팅"))
        chat_layout.addWidget(self.chat_output)
        main_layout.addWidget(chat_card, 1)  # Stretch chat card

        # --- Status Area ---
        status_card = CardWidget()
        status_layout = QVBoxLayout(status_card)
        self.chat_status_output = TextEdit()
        self.chat_status_output.setReadOnly(True)
        self.chat_status_output.setMaximumHeight(80)
        status_layout.addWidget(BodyLabel(text="상태"))
        status_layout.addWidget(self.chat_status_output)
        main_layout.addWidget(status_card)

        # Signals and Slots
        self.start_chat_button.clicked.connect(self.start_chat_viewer)
        self.stop_chat_button.clicked.connect(self.stop_chat_viewer)
        self.chat_file_button.clicked.connect(self.browse_chat_file)

    @Slot()
    def start_download(self):
        video_url = self.url_input.text()
        if not video_url:
            self.update_download_status("비디오 URL을 입력하세요.")
            return

        self.download_button.setEnabled(False)
        self.status_output.clear()
        self.update_download_status("다운로드를 준비 중입니다...")

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

        self.worker.progress.connect(self.update_download_status)
        self.worker.error.connect(self.update_download_status)

        self.thread.start()

    @Slot()
    def start_chat_viewer(self):
        channel_id = self.channel_id_input.text()
        if not channel_id:
            self.update_chat_status("채널 ID를 입력하세요.")
            return

        self.start_chat_button.setEnabled(False)
        self.stop_chat_button.setEnabled(True)
        self.chat_output.clear()
        self.chat_status_output.clear()
        self.update_chat_status("채팅 뷰어를 시작합니다...")

        self.chat_thread = QThread()
        self.chat_worker = ChatWorker(
            channel_id=channel_id,
            save_to_file=self.save_chat_checkbox.isChecked(),
            file_path=self.chat_file_label.text() or "chat.txt",
        )
        self.chat_worker.moveToThread(self.chat_thread)

        self.chat_thread.started.connect(self.chat_worker.run)
        self.chat_worker.finished.connect(self.chat_thread.quit)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        self.chat_thread.finished.connect(self.chat_thread.deleteLater)
        self.chat_thread.finished.connect(self.on_chat_finished)

        self.chat_worker.chat_message.connect(self.update_chat_message)
        self.chat_worker.status_message.connect(self.update_chat_status)
        self.chat_worker.error.connect(self.update_chat_status)

        self.chat_thread.start()

    @Slot()
    def stop_chat_viewer(self):
        if self.chat_worker:
            self.update_chat_status("채팅 뷰어를 중지합니다...")
            self.chat_worker.stop()
            self.stop_chat_button.setEnabled(False)

    @Slot()
    def on_chat_finished(self):
        self.start_chat_button.setEnabled(True)
        self.stop_chat_button.setEnabled(False)
        self.update_chat_status("채팅 뷰어가 중지되었습니다.")

    @Slot()
    def browse_cookies(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "쿠키 파일 선택", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.cookies_label.setText(file_path)

    @Slot()
    def browse_chat_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "채팅 저장 파일 선택", "chat.txt", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.chat_file_label.setText(file_path)

    @Slot(str)
    def update_download_status(self, text):
        self.status_output.append(text.strip())

    @Slot(str)
    def update_chat_message(self, text):
        self.chat_output.append(text.strip())

    @Slot(str)
    def update_chat_status(self, text):
        self.chat_status_output.append(text.strip())

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
