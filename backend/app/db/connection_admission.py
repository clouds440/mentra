"""FIFO admission to the configured pool; connection limits never increase."""
from collections import deque
from functools import wraps
from threading import Condition
from time import monotonic
from sqlalchemy import event
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import TimeoutError


class ConnectionAdmission:
    def __init__(self,capacity,timeout):
        self.capacity,self.timeout=capacity,timeout
        self.condition=Condition();self.waiting=deque();self.borrowed=set()

    def acquire(self):
        ticket=object();deadline=monotonic()+self.timeout
        with self.condition:
            self.waiting.append(ticket)
            try:
                while self.waiting[0] is not ticket or len(self.borrowed)>=self.capacity:
                    remaining=deadline-monotonic()
                    if remaining<=0: raise TimeoutError('Database connection capacity is busy.')
                    self.condition.wait(remaining)
                self.waiting.popleft();self.borrowed.add(ticket)
                self.condition.notify_all()
                return ticket
            except BaseException:
                if ticket in self.waiting: self.waiting.remove(ticket)
                self.condition.notify_all()
                raise

    def release(self,ticket):
        with self.condition:
            self.borrowed.discard(ticket)
            self.condition.notify_all()


def fair_connection_admission(engine,*,max_overflow=10):
    if not isinstance(engine.pool,QueuePool) or max_overflow<0 or engine.pool.size()==0: return engine
    gate=ConnectionAdmission(engine.pool.size()+max_overflow,engine.pool.timeout())
    original=engine.raw_connection
    from threading import local
    pending=local()
    @wraps(original)
    def acquire(*args,**kwargs):
        ticket=gate.acquire();pending.ticket=ticket
        try:
            return original(*args,**kwargs)
        except BaseException:
            gate.release(ticket)
            raise
        finally: pending.ticket=None
    engine.raw_connection=acquire
    @event.listens_for(engine,'checkout')
    def checkout(connection,record,proxy):
        # record_info survives connection invalidation; info does not.
        record.record_info['mentra_admission_ticket']=getattr(pending,'ticket',None)
    @event.listens_for(engine,'checkin')
    def checkin(connection,record):
        ticket=record.record_info.pop('mentra_admission_ticket',None)
        if ticket is not None: gate.release(ticket)
    return engine
