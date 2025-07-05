import asyncio
import json
import websockets
import datetime
import logging


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def connect_to_websocket(channel_id, output_file="chat.txt"):
    """
    지정된 URI에 웹소켓 연결을 생성하고, 메시지를 보내고 응답을 수신합니다.
    """
    # HAR 로그에서 추출한 웹소켓 서버 주소
    uri = "wss://kr-ss1.chat.naver.com/chat"

    try:
        # 웹소켓 서버에 연결합니다.
        async with websockets.connect(
            uri,
            user_agent_header="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
            origin="https://chzzk.naver.com",
        ) as websocket:
            print(f"웹소켓 연결 성공: {uri}")

            # 서버에 보낼 메시지 (예시)
            message_to_send = {
                "ver": "3",
                "cmd": 100,
                "svcid": "game",
                "cid": channel_id,
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
            await websocket.send(json.dumps(message_to_send))
            print(f"> 서버로 보낸 메시지: {message_to_send}")

            print(await websocket.recv())

            while True:
                message_str = await websocket.recv(decode=True)
                message = json.loads(message_str)
                # 서버 PING 메시지에 대한 PONG 응답 (연결 유지)
                if message.get("cmd") == 0:
                    await websocket.send('{"ver": "2", "cmd": 10000}')
                    continue

                chat_data = message.get("bdy", [])
                with open(output_file, "a", encoding="utf-8") as f:
                    for chat in chat_data:
                        msg_time_ms = chat.get("msgTime")
                        msg = chat.get("msg")
                        try:
                            profile_json = json.loads(chat.get("profile", "{}"))
                            nickname = profile_json.get("nickname", "익명")
                            if msg_time_ms and msg:
                                # 타임스탬프를 사람이 읽을 수 있는 시간 포맷으로 변경
                                dt_object = datetime.datetime.fromtimestamp(
                                    msg_time_ms / 1000
                                )
                                formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
                                log_message = f"[{formatted_time}] {nickname}: {msg}\n"
                                f.write(log_message)
                                print(log_message.strip())
                        except Exception:
                            continue

    except websockets.exceptions.ConnectionClosed as e:
        logging.warning(f"웹소켓 연결이 닫혔습니다: {e}")
    except Exception as e:
        logging.error(f"오류 발생: {e}", exc_info=True)


async def main():
    # 요청에 제공된 채널 ID('cid')를 사용합니다.
    # 실제 다른 방송에 연결하려면 해당 방송의 채널 ID로 변경해야 합니다.
    # 일반적으로 치지직 API를 통해 동적으로 얻어와야 합니다.
    channel_id = "N1tBQQ"

    # 프로그램이 중단되지 않는 한, 연결이 끊어지면 5초 후 자동으로 재연결을 시도합니다.
    while True:
        await connect_to_websocket(channel_id)
        logging.info("5초 후 재연결을 시도합니다...")
        await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
