import datetime
import logging
import math
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Self
from pathlib import Path

from recorder.data.data import Data


@dataclass
class FFChapter(Data):
    title: str
    time: float


@dataclass
class FFMetadata(Data):
    id: Optional[str] = field(default=None)
    title: Optional[str] = field(default=None)
    author: Optional[str] = field(default=None)
    description: Optional[str] = field(default=None)
    start_time: Optional[float] = field(default=None)
    end_time: Optional[float] = field(default=None)

    categories: list[FFChapter] = field(default_factory=list)
    titles: list[FFChapter] = field(default_factory=list)

    @classmethod
    def create(cls, **kwargs) -> Self:
        new_kwargs: dict[str, Any] = {}
        for k, v in kwargs.items():
            if k in ("categories", "titles"):
                new_kwargs[k] = [FFChapter.create(**item) for item in v]
            elif k in cls.__match_args__:
                new_kwargs[k] = v
        return cls(**new_kwargs)

    def append_ffmetadata(self, path: Path) -> None:
        logging.debug("writing metadata to %s", path)

        with open(path, 'a') as f:
            # Write basic metadata
            if self.title is not None:
                f.write(f"title={self.escape(self.title)}\n")
            if self.author is not None:
                f.write(f"author={self.escape(self.author)}\n")

            # Build description
            description = ""
            if self.description is not None:
                description += self.description
            if self.id is not None:
                description += f"\nID: {self.id}"

            # Add category and title changes
            if self.start_time is not None:
                if len(self.categories) > 0:
                    description += "\nCategories:"
                chapters = [*self.categories, FFChapter(title="end", time=float("inf"))]
                for i in range(len(chapters[:-1])):
                    if chapters[i+1].time <= self.start_time:
                        continue
                    description += f"\n{datetime.timedelta(seconds=round(max(chapters[i].time - self.start_time, 0)))}: {chapters[i].title}"

                if len(self.titles) > 0:
                    description += "\nTitles:"
                chapters = [*self.titles, FFChapter(title="end", time=float("inf"))]
                for i in range(len(chapters[:-1])):
                    if chapters[i+1].time <= self.start_time:
                        continue
                    description += f"\n{datetime.timedelta(seconds=round(max(chapters[i].time - self.start_time, 0)))}: {chapters[i].title}"

            # Write description
            if len(description) > 0:
                f.write(f"description={self.escape(description)}\n")

            # Write chapters based on category changes
            if self.start_time is not None and self.end_time is not None:
                t_start = math.floor(1000 * self.start_time)
                t_curr = t_start
                chapters = [*self.categories, FFChapter(title="end", time=self.end_time)]
                for i in range(len(chapters[:-1])):
                    t_next = math.floor(1000 * chapters[i+1].time)
                    if t_next <= t_start:
                        continue
                    f.write("\n".join([
                        "",
                        "[CHAPTER]",
                        "TIMEBASE=1/1000",
                        f"START={t_curr - t_start}",
                        f"END={t_next - t_start}",
                        f"title={self.escape(chapters[i].title)}",
                        ""
                    ]))
                    t_curr = t_next

    @staticmethod
    def dump(obj: "FFMetadata", path: Path) -> None:
        with open(path, "w") as f:
            json.dump(asdict(obj), f, indent=4)

    @staticmethod
    def load(path: Path) -> "FFMetadata":
        with open(path, "r") as f:
            data = json.load(f)
            return FFMetadata.create(**data)

    @staticmethod
    def escape(s: str) -> str:
        return "".join(f"\\{x}" if x in ["=", ";", "#", "\\", "\n"] else x for x in s)
