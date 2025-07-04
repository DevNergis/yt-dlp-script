import sys
import tempfile
import yt_dlp

def main():
    """
    Runs yt-dlp with specific arguments to download a video.
    """
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <video_url>")
        sys.exit(1)

    video_url = sys.argv[1]

    # Get the system's temporary directory
    temp_dir = tempfile.gettempdir()

    # Construct the yt-dlp options
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mkv',
        'downloader': 'aria2c',
        'downloader_args': {'aria2c': ['--dir=' + temp_dir]},
        'live_from_start': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

    except yt_dlp.utils.DownloadError as e:
        print(f"An error occurred during download: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()