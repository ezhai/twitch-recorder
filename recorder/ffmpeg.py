import subprocess
from pathlib import Path

import config


class FFMpegRecorder:
    """
    Utility class to wrap around ffmpeg.
    """

    @staticmethod
    def get_video_metadata(video_src_path: Path, metadata_dst_path: Path) -> None:
        subprocess.run([config.ffmpeg, "-v", "error", "-i", video_src_path, "-f", "ffmetadata", metadata_dst_path], check=True)

    @staticmethod
    def get_video_length(video_src_path: Path) -> float:
        res = subprocess.run([config.ffprobe, "-v", "error", "-i", video_src_path, "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1"], check=True, capture_output=True)
        return float(res.stdout.strip())

    @staticmethod
    def process_video(video_src_path: Path, metadata_src_path: Path, video_dst_path: Path) -> None:
        subprocess.run([config.ffmpeg, "-v", "error", "-i", video_src_path,  "-i", metadata_src_path,
                        "-map_metadata", "1", "-c", "copy", video_dst_path], check=True)
