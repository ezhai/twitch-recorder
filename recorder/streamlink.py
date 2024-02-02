import subprocess
from pathlib import Path

import config


class Streamlink:
    """
    Utility class to wrap around streamlink.
    """

    quality = "best"

    @staticmethod
    def record_stream(username: str, video_dst_path: Path) -> None:
        options = ["--twitch-disable-ads"]
        if config.oauth_token != "":
            options.append(f"--twitch-api-header=Authorization=OAuth {config.oauth_token}")
        subprocess.run([config.streamlink, *options, "--output", video_dst_path, f"twitch.tv/{username}", Streamlink.quality])
