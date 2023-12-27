import pytest
from pathlib import Path
from typing import NamedTuple

from recorder.data.ffmetadata import FFChapter, FFMetadata


class Case(NamedTuple):
    id: str
    metadata: FFMetadata
    expected: str


class TestFFMetadata():
    testcases = [
        Case(
            id="regular metadata",
            metadata=FFMetadata(
                title="Stole this copy of Mario 64 from a pharaohs tomb and now it's haunting me (SM64 Chaos Edition)", author="batatvideogames", id="40302405061",
                description="Streamed on 2023-12-23 23:42:00 UTC at twitch.tv/batatvideogames", start_time=1703374920.000, end_time=1703393700.000,
                categories=[FFChapter(title="Just Chatting", time=1703374920.000), FFChapter(title="Super Mario 64", time=1703378400.000)],
                titles=[FFChapter(title="Stole this copy of Mario 64 from a pharaohs tomb and now it's haunting me (SM64 Chaos Edition)", time=1703374920.000)]
            ),
            expected="\n".join([
                "title=Stole this copy of Mario 64 from a pharaohs tomb and now it's haunting me (SM64 Chaos Edition)",
                "author=batatvideogames",
                "description=Streamed on 2023-12-23 23:42:00 UTC at twitch.tv/batatvideogames\\",
                "ID: 40302405061\\",
                "Categories:\\",
                "0:00:00: Just Chatting\\",
                "0:58:00: Super Mario 64\\",
                "Titles:\\",
                "0:00:00: Stole this copy of Mario 64 from a pharaohs tomb and now it's haunting me (SM64 Chaos Edition)",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=0",
                "END=3480000",
                "title=Just Chatting",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=3480000",
                "END=18780000",
                "title=Super Mario 64",
                "",
            ])
        ),
        Case(
            id="empty metadata",
            metadata=FFMetadata(),
            expected="\n".join([]),
        ),
        Case(
            id="before start time",
            metadata=FFMetadata(
                title="Merry Christmas!", author="batatvideogames", id="40000000000",
                description="Streamed on 2023-12-25 00:00:00 UTC at twitch.tv/batatvideogames", start_time=1000, end_time=2000,
                categories=[FFChapter(title="Game A", time=900), FFChapter(title="Game B", time=1000), FFChapter(title="Game C", time=1500)]
            ),
            expected="\n".join([
                "title=Merry Christmas!",
                "author=batatvideogames",
                "description=Streamed on 2023-12-25 00:00:00 UTC at twitch.tv/batatvideogames\\",
                "ID: 40000000000\\",
                "Categories:\\",
                "0:00:00: Game B\\",
                "0:08:20: Game C",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=0",
                "END=500000",
                "title=Game B",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=500000",
                "END=1000000",
                "title=Game C",
                "",
            ])
        ),
        Case(
            id="overlapping start time",
            metadata=FFMetadata(
                title="Merry Christmas!", author="batatvideogames", id="40000000000",
                description="Streamed on 2023-12-25 00:00:00 UTC at twitch.tv/batatvideogames", start_time=1000, end_time=2000,
                categories=[FFChapter(title="Game A", time=900), FFChapter(title="Game B", time=1100), FFChapter(title="Game C", time=1500)]
            ),
            expected="\n".join([
                "title=Merry Christmas!",
                "author=batatvideogames",
                "description=Streamed on 2023-12-25 00:00:00 UTC at twitch.tv/batatvideogames\\",
                "ID: 40000000000\\",
                "Categories:\\",
                "0:00:00: Game A\\",
                "0:01:40: Game B\\",
                "0:08:20: Game C",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=0",
                "END=100000",
                "title=Game A",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=100000",
                "END=500000",
                "title=Game B",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=500000",
                "END=1000000",
                "title=Game C",
                "",
            ])
        ),
        Case(
            id="after start time",
            metadata=FFMetadata(
                title="Merry Christmas!", author="batatvideogames", id="40000000000",
                description="Streamed on 2023-12-25 00:00:00 UTC at twitch.tv/batatvideogames", start_time=1000, end_time=2000,
                categories=[FFChapter(title="Game A", time=1200), FFChapter(title="Game B", time=1800)]
            ),
            expected="\n".join([
                "title=Merry Christmas!",
                "author=batatvideogames",
                "description=Streamed on 2023-12-25 00:00:00 UTC at twitch.tv/batatvideogames\\",
                "ID: 40000000000\\",
                "Categories:\\",
                "0:03:20: Game A\\",
                "0:13:20: Game B",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=0",
                "END=800000",
                "title=Game A",
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                "START=800000",
                "END=1000000",
                "title=Game B",
                "",
            ])
        )
    ]

    @pytest.mark.parametrize("id,metadata,expected", testcases, ids=[tc.id for tc in testcases])
    def test_ffmetadata_append(self, tmp_path: Path, id: str, metadata: FFMetadata, expected: str) -> None:
        tmp_file = tmp_path.joinpath("test.dat")

        metadata.append_ffmetadata(tmp_file)
        with open(tmp_file, "r") as f:
            assert f.read() == expected
