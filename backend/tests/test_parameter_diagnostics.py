import json
import logging
import unittest
from pydantic import BaseModel
from app.core.logging import workflow_logger
from app.core.observability.payloads import capture


class Handler(logging.Handler):
    def __init__(self): super().__init__(); self.items=[]
    def emit(self,record):
        if hasattr(record,'workflow_event'): self.items.append(record.workflow_event)


class ParameterTests(unittest.TestCase):
    def setUp(self):
        self.target=logging.getLogger('mentra.events'); self.handler=Handler()
        self.old=(self.target.handlers,self.target.level,self.target.propagate)
        self.target.handlers=[self.handler]; self.target.setLevel(logging.INFO); self.target.propagate=False
    def tearDown(self):
        self.target.handlers,self.target.level,self.target.propagate=self.old

    def test_contract_supplied_defaulted_and_explicit_null(self):
        class Request(BaseModel):
            query: str
            topic: str|None=None
            count: int=5
            grounded: bool=False
        value=capture(Request(query='PRIVATE QUERY',topic=None))
        self.assertEqual(value['supplied'],['query','topic'])
        self.assertEqual(value['defaulted'],['count','grounded'])
        self.assertEqual(value['fields']['topic']['type'],'null')
        self.assertFalse(value['fields']['grounded']['value'])
        self.assertNotIn('PRIVATE QUERY',json.dumps(value))

    def test_query_size_and_collection_count_are_bounded_without_content(self):
        value=capture({'query':'private '*100000,'documents':[],'sources':[{'excerpt':'never logged','id':'source-1'}]*1000})
        self.assertEqual(value['fields']['query']['characters'],800000)
        self.assertEqual(value['fields']['sources']['count'],1000)
        self.assertTrue(value['fields']['documents']['empty'])
        self.assertNotIn('never logged',json.dumps(value))
        self.assertLess(len(json.dumps(value)),1500)

    def test_registered_function_passed_and_skipped_parameters(self):
        @workflow_logger.connect_module(default_outcome='success')
        class Service:
            def run(self,query,topic=None,count=5): return {'answer':'PRIVATE ANSWER','outcome':'rejected'}
        Service().run('PRIVATE QUERY',topic=None)
        start=next(x for x in self.handler.items if x['event']=='step.started')
        end=next(x for x in self.handler.items if x['event']=='step.completed')
        self.assertEqual(start['input']['skipped_parameters'],['count'])
        self.assertEqual(start['request']['supplied'],['query','topic'])
        self.assertEqual(end['outcome'],'rejected')
        self.assertIn('execution_ms',end)
        self.assertIn('exclusive_ms',end)
        self.assertNotIn('PRIVATE QUERY',json.dumps(self.handler.items))
        self.assertNotIn('PRIVATE ANSWER',json.dumps(self.handler.items))

    def test_failure_keeps_reason_and_redacts_secret_input(self):
        @workflow_logger.connect_module()
        class Service:
            def fail(self,password): raise ValueError('Invalid date; password='+password)
        with self.assertRaises(ValueError): Service().fail('opaque-credential-123')
        end=next(x for x in self.handler.items if x['event']=='step.completed')
        self.assertIn('Invalid date',end['error']['reason'])
        self.assertTrue(end['error']['frames'])
        self.assertNotIn('opaque-credential-123',json.dumps(self.handler.items))
