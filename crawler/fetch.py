"""Native fetch operations, independent of HTTP and durable job execution."""

from .contracts import FetchContext, FetchError
from .sources.atcoder import AtCoderSource
from .sources.codeforces import CodeforcesSource
from .sources.qoj import QojSource
from .sources.ojuz import OjuzSource
from .transport import SourceTransport


class FetchService:
    queue_sources = ('cf', 'atcoder', 'qoj', 'ojuz')
    def __init__(self, transport=None, timeout=90):
        self.transport = transport or SourceTransport()
        self.timeout = timeout
        self.adapters = {"cf": CodeforcesSource(self.transport),
                         "atcoder": AtCoderSource(self.transport), "qoj": QojSource(self.transport),
                         "ojuz": OjuzSource(self.transport)}

    def fetch(self, request):
        context = FetchContext(self.timeout)
        try:
            data = getattr(self.adapters[request.source], request.entity)(request, context)
            context.remaining()
            return context.result(data)
        except FetchError as error:
            if error.code == "RESOURCE_NOT_FOUND":
                error.code = request.entity.upper() + "_NOT_FOUND"
            raise
