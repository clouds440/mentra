"""Generate safe execution examples and measure local logger overhead."""
import argparse
import io
import json
import logging
import statistics
import time
from pathlib import Path

from app.core.logging import workflow_logger, configure_logging
from app.core.observability.formatters import EventFormatter


@workflow_logger.connect_module(default_outcome='success')
class ExampleModule:
    def request(self):
        return self.lookup()
    def lookup(self):
        return 3


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('docs/logging-examples'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    configure_logging('verification')
    target=logging.getLogger('mentra.events')
    saved_handlers,saved_propagate=target.handlers,target.propagate
    target.propagate=False
    try:
        for mode in ('console','json'):
            sink=io.StringIO()
            handler=logging.StreamHandler(sink)
            handler.setFormatter(EventFormatter(mode))
            target.handlers=[handler]
            with workflow_logger.workflow('example.request') as run:
                ExampleModule().request()
                with workflow_logger.workflow('example.child') as child:
                    ExampleModule().lookup()
                    child.outcome='success'
                run.outcome='success'
            text=sink.getvalue()
            if mode=='json':
                for line in text.splitlines():json.loads(line)
            (args.output / ('workflow.'+('jsonl' if mode=='json' else 'txt'))).write_text(text,encoding='utf-8')
        # Comparable bounded mock work, no real terminal or provider latency.
        def measure():
            values=[]
            for _ in range(250):
                started=time.perf_counter()
                with workflow_logger.workflow('benchmark') as run:
                    ExampleModule().request()
                    run.outcome='success'
                values.append((time.perf_counter()-started)*1000)
            return dict(median_ms=statistics.median(values),p95_ms=sorted(values)[int(len(values)*.95)])
        target.handlers=[logging.NullHandler()]
        baseline=measure()
        sink=io.StringIO()
        handler=logging.StreamHandler(sink);handler.setFormatter(EventFormatter('json'))
        target.handlers=[handler]
        enabled=measure()
        report=dict(iterations=250,baseline=baseline,json_to_memory=enabled,
                    conditions='Nested mock workflow; real terminal, database and provider latency excluded',
                    budget_pass=all(enabled[key]-baseline[key]<=max(2,baseline[key]*.05) for key in baseline))
        (args.output/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:
        target.handlers,target.propagate=saved_handlers,saved_propagate


if __name__=='__main__':main()
