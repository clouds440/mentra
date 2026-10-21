"""Short, explicitly scoped read sessions; writes retain their own transactions."""
from contextlib import contextmanager


class ReadSessions:
    def __init__(self, factory, session):
        self.factory, self.session = factory, session

    @contextmanager
    def __call__(self):
        yield self.session

    def begin(self):
        # A domain write must never accidentally commit the enclosing read.
        self.session.rollback()
        return self.factory.begin()


@contextmanager
def read_sessions(factory):
    with factory() as session:
        yield ReadSessions(factory, session)
