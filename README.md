# yt-dlp-script

이 프로젝트는 yt-dlp를 사용하여 동영상을 다운로드하고, aria2c를 사용하여 병렬 다운로드를 수행하며, ffmpeg를 사용하여 동영상 파일을 변환하는 스크립트입니다.

## 필요 도구

이 스크립트를 사용하기 위해서는 다음 도구들이 필요합니다:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [aria2c](https://aria2.github.io/)
- [ffmpeg](https://ffmpeg.org/)

## Use

```shell
./Default.sh <URL>
```
- 기본적으로 라이브 스트림은 처음부터 다운로드 됩니다.
