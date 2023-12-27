from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Self

from recorder.data.data import Data


@dataclass
class Stream(Data):
    id: str = field(default="")
    title: str = field(default="")
    user_login: str = field(default="")
    user_name: str = field(default="")
    game_name: str = field(default="")
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    tags: list = field(default_factory=list)

    @classmethod
    def create(cls, **kwargs) -> Self:
        new_kwargs: dict[str, Any] = {}
        for k, v in kwargs.items():
            if k == "started_at":
                new_kwargs[k] = datetime.fromisoformat(v)
            elif k in cls.__match_args__:
                new_kwargs[k] = v
        return cls(**new_kwargs)


@dataclass
class StreamPaginator(Data):
    cursor: str = field(default="")


@dataclass
class StreamResponse(Data):
    data: list[Stream] = field(default_factory=list)
    pagination: StreamPaginator = field(default_factory=StreamPaginator)

    @classmethod
    def create(cls, **kwargs) -> Self:
        new_kwargs: dict[str, Any] = {}
        if "data" in kwargs:
            new_kwargs["data"] = [Stream.create(**item) for item in kwargs["data"]]
        if "pagination" in kwargs:
            new_kwargs["pagination"] = StreamPaginator.create(**kwargs["pagination"])
        return cls(**new_kwargs)


@dataclass
class OAuthToken(Data):
    access_token: str
