import sys
import tempfile
import yt_dlp
import typer
import streamlink
import os
from typing_extensions import Annotated


temp = os.path.join(tempfile.gettempdir(), "Anya")
app = typer.Typer()


def download_video(video_url: str, cookies_file: str | None = None):
    """
    주어진 URL의 비디오를 yt-dlp를 사용하여 다운로드합니다.
    사용자가 Ctrl+C를 누르면 다운로드를 중단합니다.

    :param video_url: 다운로드할 비디오의 URL
    :param cookies_file: 사용할 쿠키 파일의 경로
    """
    # 시스템의 임시 디렉토리 가져오기
    temp_dir = tempfile.gettempdir()

    # yt-dlp 옵션 구성
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mkv",
        "downloader": "aria2c",
        "downloader_args": {"aria2c": ["--dir=" + temp_dir]},
        "live_from_start": True,
        "no_warnings": True,
    }

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        print("yt-dlp로 다운로드를 시작합니다... (중단하려면 Ctrl+C를 누르세요)")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        print(f"\n비디오 다운로드 성공: {video_url}")
    except KeyboardInterrupt:
        print("\n다운로드가 사용자에 의해 중단되었습니다.", file=sys.stderr)
        # yt-dlp는 일반적으로 .part 파일을 스스로 정리하므로 별도 조치는 불필요합니다.
        sys.exit(130)
    except yt_dlp.utils.DownloadError as e:
        print(f"다운로드 중 오류가 발생했습니다: {e}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"예상치 못한 오류가 발생했습니다: {e}", file=sys.stderr)
        raise


def download_live_stream(video_url: str, cookies_file: str | None = None):
    """
    주어진 URL의 라이브 스트림을 streamlink를 사용하여 다운로드합니다.
    yt-dlp를 사용하여 제목을 먼저 추출합니다.
    사용자가 Ctrl+C를 누르면 다운로드를 중단하고 정리합니다.

    :param video_url: 다운로드할 라이브 스트림의 URL
    :param cookies_file: 사용할 쿠키 파일의 경로
    """

    try:
        # 1. yt-dlp를 사용하여 비디오 제목 추출
        title = "livestream"
        try:
            ydl_opts = {"quiet": True, "skip_download": True, "no_warnings": True}
            if cookies_file:
                ydl_opts["cookiefile"] = cookies_file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                title = info.get("title", "livestream")
        except Exception as e:
            print(
                f"경고: yt-dlp로 제목을 가져오는 데 실패했습니다. 기본 파일명을 사용합니다. 오류: {e}",
                file=sys.stderr,
            )

        # 2. streamlink로 다운로드 준비
        session = streamlink.Streamlink()
        if cookies_file:
            session.set_option("http-cookie-file", cookies_file)
        streams = session.streams(video_url)

        if not streams:
            print("스트림을 찾을 수 없습니다.", file=sys.stderr)
            sys.exit(1)

        best_stream = streams["best"]
        print(
            "최고 화질 스트림을 다운로드합니다... (중단하려면 Ctrl+C를 5초간 누르세요)"
        )

        safe_filename = (
            "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).rstrip()
            + ".ts"
        )

        print(f"파일 저장 경로: {safe_filename}")

        # 3. 다운로드 시작
        with best_stream.open() as fd, open(safe_filename, "wb") as f:
            for chunk in iter(lambda: fd.read(8192), b""):
                f.write(chunk)

        print(f"\n라이브 스트림 다운로드 성공: {safe_filename}")

    except KeyboardInterrupt:
        print("\n다운로드가 사용자에 의해 중단되었습니다.", file=sys.stderr)
        sys.exit(130)  # Ctrl+C에 대한 표준 종료 코드
    except streamlink.exceptions.NoPluginError:
        print(
            f"'{video_url}'에 대한 Streamlink 플러그인을 찾을 수 없습니다.",
            file=sys.stderr,
        )
        raise
    except Exception as e:
        print(
            f"라이브 스트림 다운로드 중 예상치 못한 오류가 발생했습니다: {e}",
            file=sys.stderr,
        )
        raise


@app.command()
def main(
    video_url: Annotated[
        str, typer.Argument(help="다운로드할 비디오 또는 스트림의 URL")
    ],
    live: Annotated[
        bool,
        typer.Option(
            "-l", "--live", help="streamlink를 사용하여 라이브 스트림을 다운로드합니다."
        ),
    ] = False,
    cookies: Annotated[
        str,
        typer.Option(
            "-c",
            "--cookies",
            help="yt-dlp 및 streamlink에 전달할 쿠키 파일의 경로입니다.",
        ),
    ] = None,
):
    try:
        if live:
            print("라이브 모드: streamlink를 사용하여 다운로드합니다.")
            download_live_stream(video_url, cookies)
        else:
            print("일반 모드: yt-dlp를 사용하여 다운로드합니다.")
            download_video(video_url, cookies)
    except Exception:
        # 각 다운로드 함수에서 구체적인 오류를 출력하므로 여기서는 종료만 합니다.
        sys.exit(1)


if __name__ == "__main__":
    app()
