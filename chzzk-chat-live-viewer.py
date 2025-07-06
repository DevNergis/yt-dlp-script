import asyncio
import json
import websockets
import datetime
import logging
import random
import aiohttp
import aiofiles


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def connect_to_websocket(channel_id, file_stream):
    uri = f"wss://kr-ss{random.randint(1, 10)}.chat.naver.com/chat"
    print(f"웹소켓 URI: {uri}")

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
                message_str = await websocket.recv()
                message = json.loads(message_str)
                # 서버 PING 메시지에 대한 PONG 응답 (연결 유지)
                if message.get("cmd") == 0:
                    await websocket.send('{"ver": "2", "cmd": 10000}')
                    continue

                chat_data = message.get("bdy", [])
                for chat in chat_data:
                    try:
                        msg_time_ms = chat.get("msgTime")
                        msg = chat.get("msg")

                        profile_json = json.loads(chat.get("profile", "{}"))
                        nickname = profile_json.get("nickname", "익명")

                        extras_json = json.loads(chat.get("extras", "{}"))
                        os_type = extras_json.get("osType")
                        pay_amount = extras_json.get("payAmount")

                        if msg_time_ms and msg:
                            # 타임스탬프를 사람이 읽을 수 있는 시간 포맷으로 변경
                            dt_object = datetime.datetime.fromtimestamp(
                                msg_time_ms / 1000
                            )
                            formatted_time = dt_object.strftime("%Y-%m-%d %H:%M:%S")
                            os_info = f" ({os_type})" if os_type else ""

                            if pay_amount and pay_amount > 0:
                                log_message = f"[{formatted_time}] {nickname}{os_info} ({pay_amount}원 후원): {msg}\n"
                            else:
                                log_message = (
                                    f"[{formatted_time}] {nickname}{os_info}: {msg}\n"
                                )

                            await file_stream.write(log_message)
                            await (
                                file_stream.flush()
                            )  # 버퍼를 플러시하여 파일에 즉시 쓰도록 합니다.
                            print(log_message.strip())
                    except Exception:
                        continue

    except websockets.exceptions.ConnectionClosed as e:
        logging.warning(f"웹소켓 연결이 닫혔습니다: {e}")
    except Exception as e:
        logging.error(f"오류 발생: {e}", exc_info=True)


async def main():
    channel_id = input("채널 ID를 입력하세요 (예: affa78....): ")
    output_file = "chat.txt"

    api_url = (
        f"https://api.chzzk.naver.com/polling/v2/channels/{channel_id}/live-status"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                response.raise_for_status()
                data = await response.json()
                content = data.get("content", {})
                chat_channel_id = content.get("chatChannelId")

                if not chat_channel_id:
                    print("라이브 중이 아니거나, chatChannelId를 찾을 수 없습니다.")
                    return

    except aiohttp.ClientError as e:
        logging.error(f"API 요청 중 오류 발생: {e}")
        return

    # 프로그램이 중단되지 않는 한, 연결이 끊어지면 5초 후 자동으로 재연결을 시도합니다.
    async with aiofiles.open(output_file, "a", encoding="utf-8") as f:
        while True:
            await connect_to_websocket(chat_channel_id, f)
            logging.info("5초 후 재연결을 시도합니다...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
