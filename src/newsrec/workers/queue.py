import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from newsrec.domain.page import Page
from newsrec.workers.bus import JobBus

logger = logging.getLogger(__name__)
_END = object()


class GPUQueue:
    def __init__(self, workspace, factories, resident=None):
        self.workspace = workspace
        self.repo = workspace.repo
        self.factories = factories
        # Every engine here can be recognised with; at most one is resident in VRAM,
        # and `resident` is the one paid for at startup so the common path is warm.
        self.resident = resident if resident in factories else next(iter(factories), None)
        self.engines = {}
        self.bus = JobBus()
        self.queue = asyncio.Queue()
        self.pending = []
        self.active = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")

    async def call(self, function, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, function, *args)

    async def start(self):
        self.repo.interrupt_jobs()
        try:
            if self.resident:
                self.engines[self.resident] = await self.call(self.factories[self.resident])
        except BaseException:
            await self.close_engines()
            self.executor.shutdown(wait=True)
            raise
        self.task = asyncio.create_task(self.consume())

    async def ensure(self, name, job_id):
        """Swap the resident engine. Two server recognisers do not fit an 8 GB card."""
        if name not in self.engines:
            self.emit(job_id, {"stage": "loading", "engine": name})
            await self.close_engines()
            self.engines.clear()
            self.engines[name] = await self.call(self.factories[name])
        return self.engines[name]

    def emit(self, job_id, data):
        self.repo.append_event(job_id, data)
        self.bus.publish(job_id)

    def enqueue(self, page_id, engine):
        self.repo.page_ref(page_id)
        if engine not in self.factories:
            raise ValueError("engine is not enabled on this server")
        if self.repo.get_corrections(page_id, engine):
            raise ValueError("Undo saved edits before recognizing this page again with the same engine")
        job_id = self.repo.create_job(page_id, engine)
        self.pending.append(job_id)
        self.emit(job_id, {"stage": "queued", "position": len(self.pending) + bool(self.active)})
        self.queue.put_nowait(job_id)
        return job_id

    async def consume(self):
        while True:
            job_id = await self.queue.get()
            if job_id is None:
                self.queue.task_done()
                return
            self.pending.remove(job_id)
            self.active = job_id
            for position, pending in enumerate(self.pending, 2):
                self.emit(pending, {"stage": "queued", "position": position})
            iterator = None
            try:
                job = self.repo.job(job_id)
                self.emit(job_id, {"stage": "started"})
                engine = await self.ensure(job["engine"], job_id)
                iterator = engine.recognize(str(self.workspace.image(job["page_id"])))
                done = False
                while (stage := await self.call(next, iterator, _END)) is not _END:
                    if stage["stage"] == "done":
                        page = Page.from_dict(stage["page"])
                        page.image = f'/api/pages/{job["page_id"]}/image'
                        self.repo.save_page(job["page_id"], page)
                        stage = {**stage, "page": page.to_dict()}
                        done = True
                    self.emit(job_id, stage)
                if not done:
                    raise RuntimeError("recognition ended without a page")
            except Exception:
                logger.exception("Recognition job %s failed", job_id)
                self.emit(job_id, {"stage": "error", "message": "Recognition failed. See server log for details."})
            finally:
                if iterator is not None and hasattr(iterator, "close"):
                    await self.call(iterator.close)
                self.active = None
                self.queue.task_done()

    async def close_engines(self):
        for engine in self.engines.values():
            if hasattr(engine, "close"):
                await self.call(engine.close)

    async def stop(self):
        # Drain authorized uploads before releasing the sole GPU executor.
        await self.queue.put(None)
        await self.task
        await self.close_engines()
        self.executor.shutdown(wait=True)
