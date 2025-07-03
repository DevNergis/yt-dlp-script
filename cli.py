import subprocess
import sys
import os
import glob
import tempfile

def main():
    """
    Runs yt-dlp with specific arguments to download a video and cleans up
    temporary files upon successful completion.
    """
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <video_url>")
        sys.exit(1)

    video_url = sys.argv[1]

    # Get the system's temporary directory
    temp_dir = tempfile.gettempdir()

    # Construct the yt-dlp command
    command = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mkv",
        "--downloader", "aria2c",
        "--downloader-args", f"aria2c:--dir={temp_dir}",
        "--live-from-start",
        "--no-warnings",
        video_url
    ]

    try:
        # Execute the command
        subprocess.run(command, check=True)

    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running yt-dlp: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'yt-dlp' or 'aria2c' command not found.", file=sys.stderr)
        print("Please ensure yt-dlp and aria2c are installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
