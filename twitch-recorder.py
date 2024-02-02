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
from recorder.streamlink import Streamlink
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
        self.username = ""
        self.recorded_dir = Path(config.storage_dir).joinpath("recorded")
        self.processed_dir = Path(config.storage_dir).joinpath("processed")
        self.stream_poll_interval = 15
        self.metadata_poll_interval = 30

        # twitch configuration
        self.oauth_url = "https://id.twitch.tv/oauth2/token"
        self.api_url = "https://api.twitch.tv/helix/streams"
        self.client_id = config.client_id
        self.client_secret = config.client_secret
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
                else:
                    status = TwitchResponseStatus.ERROR
        except Exception as e:
            logging.error("unexpected error: %s", e)
            status = TwitchResponseStatus.ERROR
        return status, info


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

        # add the aggregated metadata
        logging.info("fixing %s", recorded_video_path)
        FFMpegRecorder.process_video(recorded_video_path, processed_metadata_path, processed_video_path)

        # copy new metadata to the folder
        shutil.copy(recorded_metadata_path, processed_metadata_path)

        # remove temp files
        recorded_video_path.unlink()
        recorded_metadata_path.unlink()
        processed_metadata_path.unlink()

    async def poll_metadata(self, metadata: FFMetadata, metadata_path: Path) -> None:
        prev_stream = Stream()
        while True:
            status, stream = self.fetch_stream()
            currtime = time.time()
            match status:
                case TwitchResponseStatus.UNAUTHORIZED:
                    logging.error("unauthorized, attempting to log back in")
                    self.access_token = self.fetch_access_token()
                case TwitchResponseStatus.ONLINE:
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
                case _:
                    logging.error("unexpected status %s while polling metadata, retrying in %d seconds", status, self.metadata_poll_interval)
                    await asyncio.sleep(0)

    def poll_stream(self) -> None:
        self.access_token = self.fetch_access_token()
        while True:
            status, stream = self.fetch_stream()
            match status:
                case TwitchResponseStatus.UNAUTHORIZED:
                    logging.info("unauthorized, attempting to log back in")
                    self.access_token = self.fetch_access_token()
                case TwitchResponseStatus.OFFLINE:
                    logging.debug("%s currently offline, checking again in %s seconds", self.username, self.stream_poll_interval)
                    time.sleep(self.stream_poll_interval)
                case TwitchResponseStatus.ONLINE:
                    logging.info("%s is online, stream recording in session", self.username)

                    video_filename = f"{stream.user_login}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{stream.id}"
                    video_title = stream.title
                    video_author = stream.user_name
                    video_description = f"Streamed on {stream.started_at.strftime('%Y-%m-%d %H:%M:%S %Z')} at twitch.tv/{stream.user_login}"

                    recorded_path = self.recorded_dir.joinpath(f"{video_filename}.mp4")
                    processed_path = self.processed_dir.joinpath(f"{video_filename}.mp4")
                    metadata_path = self.recorded_dir.joinpath(f"{video_filename}.json")

                    # write metadata to file
                    metadata = FFMetadata(title=video_title, author=video_author, description=video_description, id=stream.id)
                    FFMetadata.dump(metadata, metadata_path)

                    # poll for stream metadata on a separate thread
                    poller = Poller(target=functools.partial(self.poll_metadata, metadata, metadata_path), interval=self.metadata_poll_interval)

                    # run metadata poller and streamlink
                    logging.info("recording stream to %s", recorded_path)
                    poller.start()
                    Streamlink.record_stream(self.username, recorded_path)
                    poller.stop()

                    # process the recorded video file
                    logging.info("stream finished recording, processing video")
                    try:
                        self.process_recorded_file(recorded_path, processed_path)
                        logging.info("finished processing video, returning to polling")
                    except Exception as e:
                        logging.error("skipped processing video, encountered exception: %s", e)
                case _:
                    logging.error("unexpected status %s while polling stream, retrying in %d seconds", status, self.stream_poll_interval)
                    time.sleep(self.stream_poll_interval)

    def run(self) -> None:
        # setup storage directory   
        self.recorded_dir = Path(config.storage_dir).joinpath("recorded", self.username)
        self.processed_dir = Path(config.storage_dir).joinpath("processed", self.username)
        if not self.recorded_dir.is_dir():
            self.recorded_dir.mkdir(parents=True, exist_ok=True)
        if not self.processed_dir.is_dir():
            self.processed_dir.mkdir(parents=True, exist_ok=True)

        # fix videos from previous recording session
        print(self.recorded_dir)
        videos = [p for p in self.recorded_dir.iterdir() if p.is_file() and p.suffix == ".mp4"]
        if len(videos) > 0:
            logging.info("processing previously recorded files")
        for video_path in videos:
            recorded_filepath = self.recorded_dir.joinpath(video_path.name)
            processed_filepath = self.processed_dir.joinpath(video_path.name)
            try:
                self.process_recorded_file(recorded_filepath, processed_filepath)
            except Exception as e:
                logging.error("skipped processing %s, encountered exception: %s", video_path, e)

        # poll for streams
        logging.info("polling stream for %s every %s seconds, recording with %s quality", self.username, self.stream_poll_interval, Streamlink.quality)
        self.poll_stream()


def main(argv) -> int:
    usage_hint = "twitch-recorder.py -u <username> [-l <log level>]"
    logging.basicConfig(level=logging.INFO, handlers=[])

    try:
        opts, _ = getopt.getopt(argv, "hu:l:", ["help", "username=",  "log="])
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
        elif opt in ("-l", "--logging"):
            logging_level = getattr(logging, arg.upper(), None)
            if not isinstance(logging_level, int):
                print(usage_hint)
                print(f"Invalid log level: {arg.upper()}")
                return 2
            logging.getLogger().setLevel(logging_level)
            print(f"log level set to {arg.upper()}")

    # check mandatory args
    if twitch_recorder.username == "":
        print(usage_hint)
        return 2
    
    # check executables
    for exe in [config.ffmpeg, config.ffprobe, config.streamlink]:
        if shutil.which(exe) is None:
            print(f"Could not find executable: {exe}")
            return 1

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
        logging.exception("unrecoverable exception: %s", e)
        sys.exit(1)
