import asyncio
import logging
import multiprocessing as mp
from typing import Callable, Coroutine, Never, Optional, TypeVar

T = TypeVar("T")


class Poller:
    """
    Poller is a concurrency construct to run an awaitable on a separate process.
    """

    def __init__(self, target: Optional[Callable[[], Coroutine[Never, Never, T]]] = None, interval: int = 15) -> None:
        self.cv = mp.Condition(lock=mp.Lock())
        self.proc = mp.Process(target=self.run_loop)
        self.terminate = mp.Event()
        self.target = target
        self.interval = interval

    async def poll(self) -> None:
        if self.target is not None:
            await self.target()

    async def wait(self) -> None:
        self.cv.acquire()
        while not self.terminate.is_set():
            self.cv.wait(self.interval)
            self.cv.release()
            await asyncio.sleep(0)
            self.cv.acquire()
        self.cv.release()

    def run_loop(self) -> None:
        try:
            loop = asyncio.new_event_loop()
            task = loop.create_task(self.poll())
            task.add_done_callback(lambda _: loop.stop())
            loop.run_until_complete(self.wait())
        except KeyboardInterrupt:
            logging.info("keyboard interrupt received by poller, attempting to exit gracefully")
        except Exception as e:
            logging.error("exception received by poller: %s", e)
        finally:
            task.cancel()
            loop.run_forever()
            loop.close()

    def start(self) -> None:
        self.proc.start()

    def stop(self) -> None:
        self.cv.acquire()
        self.terminate.set()
        self.cv.notify()
        self.cv.release()
        self.proc.join()
