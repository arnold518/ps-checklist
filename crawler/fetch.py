"""Native fetch operations, independent of HTTP and durable job execution."""

from .contracts import FetchContext, FetchError
from .sources.atcoder import AtCoderSource
from .sources.boj import BojSource
from .sources.codeforces import CodeforcesSource
from .sources.doj import DojSource
from .sources.qoj import QojSource
from .sources.ojuz import OjuzSource
from .sources.solvedac import SolvedAcSource
from .transport import SourceTransport


class FetchService:
    queue_sources = ('cf', 'atcoder', 'qoj', 'ojuz', 'boj', 'solvedac', 'doj')

    def __init__(self, transport=None, timeout=90, *, boj_content=True):
        self.transport = transport or SourceTransport()
        self.timeout = timeout
        self.boj_content = boj_content
        self.adapters = {"cf": CodeforcesSource(self.transport),
                         "atcoder": AtCoderSource(self.transport), "qoj": QojSource(self.transport),
                         "ojuz": OjuzSource(self.transport), "boj": BojSource(self.transport),
                         "doj": DojSource(self.transport),
                         "solvedac": SolvedAcSource(getattr(self.transport, 'credentials_path', None))}

    def fetch(self, request, *, timeout=None):
        context = FetchContext(self.timeout if timeout is None else timeout)
        try:
            data = getattr(self.adapters[request.source], request.entity)(request, context)
            if not self.boj_content and (request.source, request.entity) == ("boj", "problem"):
                for field in ('statement', 'samples', 'scoring'):
                    data[field] = None
                if data.get('submission'):
                    data['submission']['instructionsHtml'] = None
                context.warn('STATEMENT_LINK_ONLY', 'data.statement',
                             'Open the BOJ problem link for the statement and examples.', partial=False)
            context.remaining()
            return context.result(data)
        except FetchError as error:
            if error.code == "RESOURCE_NOT_FOUND":
                error.code = request.entity.upper() + "_NOT_FOUND"
            raise
