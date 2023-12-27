import asyncio
import enum
import functools
import getopt
import logging
import requests
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import config
from recorder.data.ffmetadata import FFMetadata, FFChapter
from recorder.data.twitch import Stream, StreamResponse, OAuthToken
from recorder.ffmpeg import FFMpegRecorder
from recorder.poller import Poller


class TwitchResponseStatus(enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    ERROR = "ERROR"


class TwitchRecorder:
    def __init__(self) -> None:
        # session confguration
        self.root_path = Path(config.storage_dir)
        self.username = ""
        self.refresh = 15

        # streamlink configuration
        self.quality = "best"

        # twitch configuration
        self.client_id = config.client_id
        self.client_secret = config.client_secret
        self.oauth_url = "https://id.twitch.tv/oauth2/token"
        self.api_url = "https://api.twitch.tv/helix/streams"
        self.access_token = ""
        self.oauth_token = config.oauth_token

    def fetch_access_token(self) -> str:
        r = requests.post(f"{self.oauth_url}?client_id={self.client_id}&client_secret={self.client_secret}&grant_type=client_credentials", timeout=15)
        r.raise_for_status()
        token = OAuthToken.create(**r.json())
        return token.access_token

    def fetch_stream(self) -> tuple[TwitchResponseStatus, Stream]:
        info = Stream.create()
        status = TwitchResponseStatus.ERROR
        try:
            headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {self.access_token}"}
            r = requests.get(f"{self.api_url}?user_login={self.username}", headers=headers, timeout=15)
            r.raise_for_status()

            stream = StreamResponse.create(**r.json())
            if stream.data:
                status = TwitchResponseStatus.ONLINE
                info = stream.data[0]
            else:
                status = TwitchResponseStatus.OFFLINE
        except requests.exceptions.RequestException as e:
            logging.error("server error: %s", e)
            if e.response is not None:
                if e.response.status_code == 400:
                    status = TwitchResponseStatus.BAD_REQUEST
                if e.response.status_code == 401:
                    status = TwitchResponseStatus.UNAUTHORIZED
        except Exception as e:
            logging.error("unexpected error: %s", e)
            status = TwitchResponseStatus.ERROR
        return status, info

    def record_stream(self, video_dst_path: Path) -> None:
        options = []
        if self.oauth_token != "":
            options.append(f"--twitch-api-header=Authorization=OAuth {self.oauth_token}")
        subprocess.run([config.streamlink, "--twitch-disable-ads", *options, "--output", video_dst_path, f"twitch.tv/{self.username}", self.quality])

    def process_recorded_file(self, recorded_video_path: Path, processed_video_path: Path) -> None:
        recorded_metadata_path = recorded_video_path.with_suffix(".json")
        processed_metadata_path = processed_video_path.with_suffix(".json")

        # unlink processed files if needed
        processed_video_path.unlink(missing_ok=True)
        processed_metadata_path.unlink(missing_ok=True)

        # use ffmpeg to extract the metadata from the recorded video
        logging.info("extracting ffmetadata from %s", recorded_video_path)
        FFMpegRecorder.get_video_metadata(recorded_video_path, processed_metadata_path)

        # get the video length
        logging.info("getting video info from %s", recorded_video_path)
        video_length = FFMpegRecorder.get_video_length(recorded_video_path)

        # read and update the metadata in the video
        logging.info("extracting metadata from %s", recorded_metadata_path)
        try:
            metadata = FFMetadata.load(recorded_metadata_path)
            metadata.end_time = recorded_video_path.stat().st_mtime
            metadata.start_time = metadata.end_time - video_length
        except Exception:
            logging.error("failed to extract video metadata, please fix the file contents and try again")
            raise

        # append the recorded metadata to the extracted metadata
        logging.info("writing updated metadata to %s", processed_metadata_path)
        metadata.append_ffmetadata(processed_metadata_path)

        # fix errors in the recorded video and add the aggregated metadata
        logging.info("fixing %s", recorded_video_path)
        FFMpegRecorder.fix_video_errors(recorded_video_path, processed_metadata_path, processed_video_path)

        # copy new metadata to the folder
        shutil.copy(recorded_metadata_path, processed_metadata_path)

        # remove temp files
        recorded_video_path.unlink()
        recorded_metadata_path.unlink()
        processed_metadata_path.unlink()

    async def poll_stream_metadata(self, metadata: FFMetadata, metadata_path: Path) -> None:
        prev_stream = Stream()
        while True:
            status, stream = self.fetch_stream()
            currtime = time.time()
            if status == TwitchResponseStatus.UNAUTHORIZED:
                logging.error("unauthorized, attempting to log back in")
                self.access_token = self.fetch_access_token()
            elif status == TwitchResponseStatus.ONLINE:
                if prev_stream.game_name != stream.game_name:
                    logging.info("setting current game to %s", stream.game_name)
                    metadata.categories.append(FFChapter(title=stream.game_name, time=currtime))
                    FFMetadata.dump(metadata, metadata_path)
                if prev_stream.title != stream.title:
                    logging.info("setting current stream title to %s", stream.title)
                    metadata.titles.append(FFChapter(title=stream.title, time=currtime))
                    FFMetadata.dump(metadata, metadata_path)
                prev_stream = stream
                await asyncio.sleep(0)
            else:
                logging.error("unexpected status %s, retrying in %d seconds", status, self.refresh)
                await asyncio.sleep(0)

    def loop_check(self, recorded_dir: Path, processed_dir: Path) -> None:
        self.access_token = self.fetch_access_token()
        while True:
            status, stream = self.fetch_stream()
            if status == TwitchResponseStatus.BAD_REQUEST:
                logging.error("bad request")
                raise Exception(f"twitch API returned bad request error for {self.username}")
            elif status == TwitchResponseStatus.UNAUTHORIZED:
                logging.info("unauthorized, attempting to log back in")
                self.access_token = self.fetch_access_token()
            elif status == TwitchResponseStatus.OFFLINE:
                logging.debug("%s currently offline, checking again in %s seconds", self.username, self.refresh)
                time.sleep(self.refresh)
            elif status == TwitchResponseStatus.ONLINE:
                logging.info("%s is online, stream recording in session", self.username)

                video_filename = f"{stream.user_login}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{stream.id}"
                video_title = stream.title
                video_author = stream.user_name
                video_description = f"Streamed on {stream.started_at.strftime('%Y-%m-%d %H:%M:%S %Z')} at twitch.tv/{stream.user_login}"

                recorded_path = recorded_dir.joinpath(f"{video_filename}.mp4")
                processed_path = processed_dir.joinpath(f"{video_filename}.mp4")
                metadata_path = recorded_dir.joinpath(f"{video_filename}.json")

                # write metadata to file
                metadata = FFMetadata(title=video_title, author=video_author, description=video_description, id=stream.id)
                FFMetadata.dump(metadata, metadata_path)

                # poll for stream metadata on a separate thread
                poller = Poller(target=functools.partial(self.poll_stream_metadata, metadata, metadata_path), interval=self.refresh)

                # run metadata poller and streamlink
                logging.info("recording stream to %s", recorded_path)
                poller.start()
                self.record_stream(recorded_path)
                poller.stop()

                # process the recorded video file
                logging.info("stream finished recording, processing video")
                if recorded_path.exists():
                    try:
                        self.process_recorded_file(recorded_path, processed_path)
                    except Exception as e:
                        logging.error("skipped processing video %s, encountered exception: %s", recorded_path, e)
                else:
                    logging.warning("skipped processing, recorded video does not exist")
                logging.info("finished processing, returning to polling")
            else:
                logging.error("unexpected status %s, retrying in %d seconds", status, self.refresh)
                time.sleep(self.refresh)

    def run(self) -> None:
        # path to recorded streams
        recorded_path = self.root_path.joinpath("recorded", self.username)

        # path to finished videos with errors removed
        processed_path = self.root_path.joinpath("processed", self.username)

        # create video directories if they do not exist
        if not recorded_path.is_dir():
            recorded_path.mkdir(parents=True, exist_ok=True)
        if not processed_path.is_dir():
            processed_path.mkdir(parents=True, exist_ok=True)

        # make sure the interval to check user availability is not less than 15 seconds
        if self.refresh < 15:
            logging.warning("stream polling interval should not be less than 15 seconds")
            self.refresh = 15
            logging.info("set polling interval to 15 seconds")

        # fix videos from previous recording session
        video_list = [f for f in recorded_path.iterdir() if f.is_file() and f.suffix == ".mp4"]
        if len(video_list) > 0:
            logging.info("processing previously recorded files")
        for f in video_list:
            recorded_filename = recorded_path.joinpath(f.name)
            processed_filename = processed_path.joinpath(f.name)
            try:
                self.process_recorded_file(recorded_filename, processed_filename)
            except Exception as e:
                logging.error("skipping video %s, encountered exception: %s", f, e)

        # run polling loop
        logging.info("polling stream for %s every %s seconds, recording with %s quality", self.username, self.refresh, self.quality)
        self.loop_check(recorded_path, processed_path)


def main(argv) -> int:
    usage_hint = "twitch-recorder.py -u <username> [-q <quality>] [-r <refresh>] [-l <log level>]"
    logging.basicConfig(level=logging.INFO, handlers=[])

    try:
        opts, _ = getopt.getopt(argv, "hu:q:l:r:", ["help", "username=", "quality=", "log=", "refresh="])
    except getopt.GetoptError:
        print(usage_hint)
        return 2

    # parse args
    twitch_recorder = TwitchRecorder()
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print(usage_hint)
            return 0
        elif opt in ("-u", "--username"):
            twitch_recorder.username = arg.lower()
        elif opt in ("-q", "--quality"):
            twitch_recorder.quality = arg
        elif opt in ("-l", "--logging"):
            logging_level = getattr(logging, arg.upper(), None)
            if not isinstance(logging_level, int):
                print(usage_hint)
                print(f"Invalid log level: {arg.upper()}")
                return 2
            logging.getLogger().setLevel(logging_level)
            print("log level set to {arg.upper()}")
        elif opt in ("-r", "--refresh"):
            twitch_recorder.refresh = int(arg)

    # check mandatory args
    if twitch_recorder.username == "":
        print(usage_hint)
        return 2

    # setup logging
    config.logging_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(Path(config.logging_dir, f"{twitch_recorder.username}.log"))
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s:%(message)s", datefmt="[%Y-%m-%d %H:%M:%S]"))
    logging.getLogger().addHandler(file_handler)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="[%Y-%m-%d %H:%M:%S]"))
    logging.getLogger().addHandler(stdout_handler)

    # run twitch recorder
    twitch_recorder.run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        logging.info("keyboard interrupt received by main thread, exiting")
        sys.exit(0)
    except Exception as e:
        logging.exception("unrecoverable exception: %s")
        sys.exit(1)
