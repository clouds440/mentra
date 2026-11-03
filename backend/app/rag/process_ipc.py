"""Bound both pipe submission and receipt, including a worker that never reads."""
from threading import Event, Thread


def exchange(connection, message, timeout, abort):
    complete=Event()
    result=[]
    def run():
        try:
            connection.send(message)
            result.append((True,connection.recv()))
        except Exception as error:
            result.append((False,error))
        finally:
            complete.set()
    sender=Thread(target=run,daemon=True)
    sender.start()
    if not complete.wait(max(0,timeout)):
        abort()
        sender.join(timeout=1)
        raise TimeoutError('Local inference IPC deadline exceeded.')
    sender.join()
    success,value=result[0]
    if not success:
        raise value
    return value
