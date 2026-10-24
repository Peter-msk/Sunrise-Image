"""Selected-image weighted batch progress; independent from Qt and worker threads."""
from dataclasses import dataclass


@dataclass
class DocumentProgress:
    path: str
    total: int | None
    processed: int = 0
    saved: int = 0
    failed: int = 0
    warned: int = 0
    blocked: int = 0
    state: str = '대기'
    member: str = ''
    ordinal: int = 0

    @property
    def terminal(self):return self.state in {'완료', '일부 완료', '실패'}

    @property
    def remaining(self):return max(0,(self.total or 0)-self.processed-self.blocked)


class BatchProgress:
    def __init__(self,documents):
        self.documents=[DocumentProgress(str(path),total) for path,total in documents]
        self.current_index=None
        self.cancelled=False

    @property
    def current(self):
        return self.documents[self.current_index] if self.current_index is not None else None

    @property
    def total(self):return sum(d.total or 0 for d in self.documents)
    @property
    def processed(self):return sum(d.processed for d in self.documents)
    @property
    def saved(self):return sum(d.saved for d in self.documents)
    @property
    def failed(self):return sum(d.failed for d in self.documents)
    @property
    def warned(self):return sum(d.warned for d in self.documents)
    @property
    def blocked(self):return sum(d.blocked for d in self.documents)
    @property
    def remaining(self):return sum(d.remaining for d in self.documents)
    @property
    def documents_done(self):return sum(d.terminal for d in self.documents)
    @property
    def documents_failed(self):return sum(d.state=='실패' for d in self.documents)
    @property
    def unknown_documents(self):return sum(d.total is None for d in self.documents)
    @property
    def percent(self):
        value=100*(self.processed+self.blocked)/self.total if self.total else 0.0
        if self.documents and self.documents_done==len(self.documents):return 100.0
        return min(99.9,max(0.0,value))

    def start(self,index):
        self.current_index=index;self.documents[index].state='처리 중'

    def begin(self,index,total):
        self.documents[index].total=max(0,int(total))

    def item_start(self,index,ordinal,member):
        d=self.documents[index];d.ordinal=ordinal;d.member=member

    def item_done(self,index,ordinal,status,counts=None):
        d=self.documents[index];d.processed=ordinal
        if counts is not None:
            d.saved, d.failed, d.warned = counts['saved'], counts['failed'], counts['warned']
            return
        if status=='실패':d.failed+=1
        else:d.saved+=1
        if status=='주의':d.warned+=1

    def end(self,index,result=None,error=False):
        d=self.documents[index]
        if error:
            d.blocked=d.remaining;d.state='실패';return
        if result is not None:
            d.total=result['total'];d.processed=result['processed'];d.saved=result['saved'];d.failed=result['failed']
            d.warned=result.get('warned',0)
            d.state = ('중지됨' if result['cancelled'] else
                       ('일부 완료' if d.saved else '실패') if d.failed else '완료')

    def finish(self,cancelled=False):
        self.cancelled=cancelled
        if cancelled:
            for d in self.documents:
                if d.state=='대기':d.state='미처리'
                elif d.state=='처리 중':d.state='중지됨'
