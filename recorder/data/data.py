from dataclasses import dataclass
from typing import Self


@dataclass
class Data:
    @classmethod
    def create(cls, **kwargs) -> Self:
        return cls(**{k: kwargs[k] for k in kwargs if k in cls.__match_args__})
