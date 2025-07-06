import asyncio
import datetime
import json
import logging
import random
import sys

import aiofiles
import aiohttp
import websockets
from PySide6.QtCore import QThread, QObject, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
)
from qfluentwidgets import (
    FluentWindow,
    LineEdit,
    PrimaryPushButton,
    TextEdit,
    CardWidget,
    setTheme,
    Theme,
    theme,
    BodyLabel,
    CaptionLabel,
    SwitchButton,
    CheckBox,
    InfoBar,
    InfoBarPosition,
    setThemeColor,
)


class Worker(QObject):
    new_message = Signal(str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, channel_id, save_log):
        super().__init__()
        self.channel_id = channel_id
        self.save_log = save_log
        self._is_running = True

    def stop(self):
        self._is_running = False
        self.new_message.emit("연결 종료 중...")

    @Slot()
    def run(self):
        try:
            asyncio.run(self.main())
        except Exception as e:
            if self._is_running:
                self.error.emit(f"작업 실행 중 오류 발생: {e}")
        finally:
            self.finished.emit()

    async def main(self):
        api_url = f"https://api.chzzk.naver.com/polling/v2/channels/{self.channel_id}/live-status"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    content = data.get("content", {})
                    chat_channel_id = content.get("chatChannelId")

                    if not chat_channel_id:
                        self.error.emit(
                            "라이브 중이 아니거나, 유효하지 않은 채널 ID입니다."
                        )
                        return
        except aiohttp.ClientError as e:
            self.error.emit(f"API 요청 오류: {e}")
            return
        except Exception as e:
            self.error.emit(f"채널 정보 확인 오류: {e}")
            return

        self.new_message.emit(f"채팅 채널 ID 확인: {chat_channel_id}")

        file_stream = None
        if self.save_log:
            filename = f"chzzk_chat_{self.channel_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            self.new_message.emit(f"채팅 로그를 '{filename}' 파일에 저장합니다.")
            file_stream = await aiofiles.open(filename, "a", encoding="utf-8")

        try:
            while self._is_running:
                await self.connect_to_websocket(chat_channel_id, file_stream)
                if not self._is_running:
                    break
                self.new_message.emit("5초 후 재연결을 시도합니다...")
                await asyncio.sleep(5)
        finally:
            if file_stream:
                await file_stream.close()

    async def connect_to_websocket(self, chat_channel_id, file_stream):
        uri = f"wss://kr-ss{random.randint(1, 10)}.chat.naver.com/chat"
        try:
            async with websockets.connect(
                uri, origin="https://chzzk.naver.com"
            ) as websocket:
                self.new_message.emit("웹소켓 연결 성공.")
                await websocket.send(
                    json.dumps(
                        {
                            "ver": "3",
                            "cmd": 100,
                            "svcid": "game",
                            "cid": chat_channel_id,
                            "bdy": {
                                "uid": None,
                                "devType": 2001,
                                "accTkn": "",
                                "auth": "READ",
                            },
                            "tid": 1,
                        }
                    )
                )

                while self._is_running:
                    try:
                        message_str = await asyncio.wait_for(
                            websocket.recv(), timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        continue

                    message = json.loads(message_str)

                    if message.get("cmd") == 0:
                        await websocket.send('{"ver": "2", "cmd": 10000}')
                        continue

                    chat_data = message.get("bdy", [])
                    for chat in chat_data:
                        try:
                            msg_time_ms = chat.get("msgTime")
                            msg = chat.get("msg")
                            nickname = json.loads(chat.get("profile", "{}")).get(
                                "nickname", "익명"
                            )
                            extras = json.loads(chat.get("extras", "{}"))
                            pay_amount = extras.get("payAmount")
                            os_type = extras.get("osType")

                            if not (msg_time_ms and msg):
                                continue

                            dt_object = datetime.datetime.fromtimestamp(
                                msg_time_ms / 1000
                            )
                            formatted_time = dt_object.strftime("%H:%M:%S")

                            os_info = f" ({os_type})" if os_type else ""

                            if pay_amount and pay_amount > 0:
                                log_message = f"[{formatted_time}] {nickname}{os_info} ({pay_amount}원 후원): {msg}"
                            else:
                                log_message = (
                                    f"[{formatted_time}] {nickname}{os_info}: {msg}"
                                )

                            self.new_message.emit(log_message)
                            if file_stream:
                                await file_stream.write(log_message + "\n")
                                await file_stream.flush()

                        except json.JSONDecodeError:
                            self.error.emit(f"JSON 파싱 오류: {chat}")
                        except Exception:
                            continue

        except websockets.exceptions.ConnectionClosed as e:
            self.error.emit(f"웹소켓 연결이 닫혔습니다: {e.reason} ({e.code})")
        except Exception as e:
            self.error.emit(f"웹소켓 오류 발생: {e}")


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.thread = None
        self.setWindowTitle("Chzzk Chat Live Viewer")
        self.setGeometry(100, 100, 700, 700)

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # --- Input Card ---
        self.input_card = CardWidget()
        self.input_layout = QVBoxLayout(self.input_card)
        self.input_layout.addWidget(BodyLabel(text="치지직 채널 ID"))
        self.channel_id_input = LineEdit()
        self.channel_id_input.setPlaceholderText("예: affa78fdc92.....")
        self.input_layout.addWidget(self.channel_id_input)
        self.main_layout.addWidget(self.input_card)

        # --- Options & Action Card ---
        self.action_card = CardWidget()
        self.action_layout = QHBoxLayout(self.action_card)
        self.save_log_checkbox = CheckBox(text="채팅 로그 파일로 저장")
        self.action_layout.addWidget(self.save_log_checkbox)
        self.action_layout.addStretch(1)
        self.toggle_button = PrimaryPushButton(text="연결 시작")
        self.toggle_button.setMinimumHeight(30)
        self.action_layout.addWidget(self.toggle_button)
        self.main_layout.addWidget(self.action_card)

        # --- Status Area ---
        self.status_card = CardWidget()
        self.status_layout = QVBoxLayout(self.status_card)
        self.status_output = TextEdit()
        self.status_output.setReadOnly(True)
        self.status_layout.addWidget(BodyLabel(text="실시간 채팅 로그"))
        self.status_layout.addWidget(self.status_output)
        self.main_layout.addWidget(self.status_card, 1)

        # --- Theme Switcher ---
        theme_layout = QHBoxLayout()
        theme_layout.setAlignment(Qt.AlignRight)
        self.theme_label = CaptionLabel()
        self.theme_switch = SwitchButton()

        # 시작 시 현재 테마에 맞게 스위치 상태 설정
        is_dark = theme() == Theme.DARK
        self.theme_switch.setChecked(is_dark)
        self.theme_label.setText("Dark Mode" if is_dark else "Light Mode")

        theme_layout.addWidget(self.theme_label)
        theme_layout.addWidget(self.theme_switch)
        self.main_layout.addLayout(theme_layout)

        self.stackedWidget.addWidget(self.main_widget)

        # Signals and Slots
        self.toggle_button.clicked.connect(self.toggle_worker)
        self.theme_switch.checkedChanged.connect(self.toggle_theme)

    @Slot()
    def toggle_worker(self):
        if self.thread and self.thread.isRunning():
            self.update_status("채팅 수집을 중지합니다.")
            self.toggle_button.setEnabled(False)
            if self.worker:
                self.worker.stop()
        else:
            channel_id = self.channel_id_input.text().strip()
            if not channel_id:
                InfoBar.error(
                    "오류",
                    "채널 ID를 입력하세요.",
                    duration=3000,
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return

            self.status_output.clear()
            self.update_status(f"'{channel_id}' 채널에 연결을 시도합니다...")
            self.toggle_button.setText("연결 중지")

            self.thread = QThread()
            self.worker = Worker(
                channel_id=channel_id,
                save_log=self.save_log_checkbox.isChecked(),
            )
            self.worker.moveToThread(self.thread)

            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.on_worker_finished)
            self.worker.new_message.connect(self.update_status)
            self.worker.error.connect(self.handle_error)

            self.thread.start()

    @Slot()
    def on_worker_finished(self):
        self.update_status("작업이 종료되었습니다.")
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread.deleteLater()
            self.thread = None
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

        self.toggle_button.setText("연결 시작")
        self.toggle_button.setEnabled(True)

    @Slot(str)
    def update_status(self, text):
        self.status_output.append(text.strip())
        self.status_output.verticalScrollBar().setValue(
            self.status_output.verticalScrollBar().maximum()
        )

    @Slot(str)
    def handle_error(self, text):
        self.update_status(f"오류: {text}")
        InfoBar.error(
            "오류", text, duration=5000, parent=self, position=InfoBarPosition.TOP
        )

    @Slot(bool)
    def toggle_theme(self, checked):
        setTheme(Theme.DARK if checked else Theme.LIGHT)
        self.theme_label.setText("Dark Mode" if checked else "Light Mode")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)
    setThemeColor("#aaffaa")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
