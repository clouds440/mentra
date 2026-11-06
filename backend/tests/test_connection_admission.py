import unittest
from threading import Thread,Event
from time import sleep,monotonic
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError
from app.db.connection_admission import ConnectionAdmission
from app.db.database import build_engine
from testing.postgres import PostgresSandbox


class ConnectionAdmissionTests(unittest.TestCase):
    def test_waiters_are_fifo_and_timed_out_ticket_does_not_block_next_caller(self):
        gate=ConnectionAdmission(1,.15);held=gate.acquire();entered=[];ready=[Event() for _ in range(3)]
        def run(index):
            ready[index].set()
            ticket=gate.acquire();entered.append(index);gate.release(ticket)
        threads=[]
        for index in range(3):
            thread=Thread(target=run,args=(index,));thread.start();threads.append(thread)
            ready[index].wait()
            deadline=monotonic()+1
            while len(gate.waiting)<index+1 and monotonic()<deadline: sleep(.001)
        gate.release(held)
        for thread in threads:thread.join()
        self.assertEqual(entered,[0,1,2])
        held=gate.acquire()
        with self.assertRaises(TimeoutError): gate.acquire()
        gate.release(held)
        ticket=gate.acquire();gate.release(ticket)

    def test_invalidation_disposal_and_failed_connect_do_not_leak_capacity(self):
        with PostgresSandbox() as db:
            engine=build_engine(db.engine.url.render_as_string(hide_password=False),pool_size=1,max_overflow=0,pool_timeout=.1)
            self.addCleanup(engine.dispose)
            with engine.connect() as connection: connection.invalidate()
            with engine.connect() as connection:self.assertEqual(connection.scalar(text('SELECT 1')),1)
            engine.dispose()
            with engine.connect() as connection:self.assertEqual(connection.scalar(text('SELECT 1')),1)
            from unittest.mock import patch
            engine.dispose()
            original=engine.pool._creator
            with patch.object(engine.pool,'_creator',side_effect=RuntimeError('connect failed')):
                with self.assertRaises(RuntimeError):engine.connect()
            with engine.connect() as connection:self.assertEqual(connection.scalar(text('SELECT 1')),1)

    def test_configured_overflow_remains_available_and_capacity_is_not_exceeded(self):
        with PostgresSandbox() as db:
            engine=build_engine(db.engine.url.render_as_string(hide_password=False),pool_size=1,max_overflow=1,pool_timeout=.1)
            self.addCleanup(engine.dispose)
            with engine.connect(),engine.connect():
                self.assertEqual(engine.pool.checkedout(),2)
                with self.assertRaises(TimeoutError):engine.connect()
