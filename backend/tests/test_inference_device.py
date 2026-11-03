import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.core.inference_device import DeviceChoice, LocalModel, select_device


def crash_speech_worker(connection,config):
    import os
    if config['device']!='cpu': os._exit(5)
    try:
        while connection.recv() is not None:
            connection.send(('ok',dict(text='recovered',language='en'), 'cpu'))
    except EOFError: pass
    finally: connection.close()


def crash_embedding_worker(connection,config):
    import os
    connection.send(('ok',dict(model_name=config['model'],model_version='same-revision',dimension=3,max_tokens=512,inference_device=config['device'])))
    try:
        while connection.recv() is not None:
            if config['device']!='cpu': os._exit(5)
            connection.send(('ok',[1.,0.,0.],'cpu'))
    except EOFError: pass
    finally: connection.close()


def crash_reranker_worker(connection,config):
    import os
    if config['device']!='cpu': os._exit(5)
    try:
        while (message:=connection.recv()) is not None:
            connection.send(dict(scores=[1.]*len(message[1]),inference_device='cpu'))
    except EOFError: pass
    finally: connection.close()


GPU = DeviceChoice('torch','cuda','float32','accelerator_available')


class DeviceTests(unittest.TestCase):
    def test_native_speech_exit_recovers_in_a_cpu_process(self):
        from app.core.config import Settings
        from app.speech.service import SpeechService
        service=SpeechService(Settings(_env_file=None,local_inference_device='cuda',speech_timeout_seconds=5),worker_target=crash_speech_worker)
        self.addCleanup(service.close)
        self.assertEqual(service.transcribe(b'audio',None)['text'],'recovered')
        self.assertEqual(service.config['device'],'cpu')

    def test_native_embedding_exit_recovers_without_changing_identity(self):
        from app.core.config import Settings
        from app.rag.embedding_process import ProcessEmbeddingService
        service=ProcessEmbeddingService(Settings(_env_file=None,embedding_device='cuda',embedding_worker_timeout=5),worker_target=crash_embedding_worker)
        self.addCleanup(service.close)
        self.assertEqual(service.embed_query('question'),[1.,0.,0.])
        self.assertEqual(service.model_version,'same-revision')
        self.assertEqual(service.config['device'],'cpu')

    def test_native_reranker_exit_recovers_within_same_request(self):
        from app.rag.reranker import LocalReranker
        service=LocalReranker('unused',5,cold_timeout=5,device='cuda',worker_target=crash_reranker_worker)
        self.addCleanup(service.close)
        self.assertEqual(service.rank('query',['passage']),[1.])
        self.assertEqual(service.device_preference,'cpu')
    def test_backend_probes_are_independent(self):
        with patch.dict('sys.modules', {'ctranslate2':SimpleNamespace(get_cuda_device_count=lambda:1,
                get_supported_compute_types=lambda _: {'int8_float16'})}):
            choice=select_device('ctranslate2')
        self.assertEqual((choice.device,choice.compute_type),('cuda','int8_float16'))
        with patch.dict('sys.modules', {'onnxruntime':SimpleNamespace(get_available_providers=lambda:['CPUExecutionProvider'])}):
            self.assertEqual(select_device('onnx').device,'cpu')

    def test_cpu_choice_never_probes_accelerators(self):
        for backend in ('torch','ctranslate2','onnx','cpu-only'):
            self.assertEqual(select_device(backend,'cpu').device,'cpu')

    def test_missing_accelerator_falls_back(self):
        with patch.dict('sys.modules', {'torch':SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:False))}):
            self.assertEqual(select_device('torch').device,'cpu')

    def test_device_loss_reloads_once_and_stays_on_cpu(self):
        loads=[]
        def load(choice): loads.append(choice.device); return choice.device
        with patch('app.core.inference_device.select_device',return_value=GPU):
            model=LocalModel(load,'torch')
        def infer(device):
            if device=='cuda': raise RuntimeError('CUDA device lost')
            return ['first','second']
        self.assertEqual(model.run(infer),['first','second'])
        self.assertEqual(model.run(infer),['first','second'])
        self.assertEqual(loads,['cuda','cpu'])
        self.assertEqual(model.choice.reason,'device_failure')

    def test_lazy_failure_does_not_publish_partial_results(self):
        def infer(device):
            def values():
                yield 'prefix'
                if device=='cuda': raise RuntimeError('CUDA device lost')
                yield 'suffix'
            return list(values())
        with patch('app.core.inference_device.select_device',return_value=GPU):
            model=LocalModel(lambda choice:choice.device,'torch')
        self.assertEqual(model.run(infer),['prefix','suffix'])

    def test_initialization_device_loss_recovers(self):
        def load(choice):
            if choice.device=='cuda': raise RuntimeError('cuDNN initialization failed')
            return 'cpu model'
        with patch('app.core.inference_device.select_device',return_value=GPU):
            model=LocalModel(load,'torch')
        self.assertEqual(model.get(),'cpu model')

    def test_input_and_asset_errors_are_not_retried(self):
        for error in (ValueError('bad input'), FileNotFoundError('weights'), RuntimeError('shape mismatch')):
            loads=[]
            with patch('app.core.inference_device.select_device',return_value=GPU):
                model=LocalModel(lambda choice:loads.append(choice.device),'torch')
            with self.assertRaises(type(error)):
                model.run(lambda _: (_ for _ in ()).throw(error))
            self.assertEqual(loads,['cuda'])

    def test_failed_cpu_recovery_is_not_a_retry_loop(self):
        loads=[]
        with patch('app.core.inference_device.select_device',return_value=GPU):
            model=LocalModel(lambda choice:loads.append(choice.device),'torch')
        with self.assertRaises(RuntimeError):
            model.run(lambda _: (_ for _ in ()).throw(RuntimeError('CUDA device lost')))
        self.assertEqual(loads,['cuda','cpu'])

    def test_speech_lazy_generator_recovers_without_duplicating_prefix(self):
        from app.speech.engine import FasterWhisperEngine
        loads=[]
        def loader(*args,**kwargs):
            loads.append(kwargs['device'])
            self.assertTrue(kwargs['local_files_only'])
            def transcribe(*args,**kw):
                def segments():
                    if kwargs['device']=='cuda':
                        yield SimpleNamespace(text='partial ')
                        raise RuntimeError('CUDA device lost')
                    yield SimpleNamespace(text='complete transcript')
                return segments(),SimpleNamespace(language='en',language_probability=.9)
            return SimpleNamespace(transcribe=transcribe)
        with (patch('app.core.inference_device.select_device',return_value=DeviceChoice('ctranslate2','cuda','int8_float16','test')),
              patch('faster_whisper.WhisperModel',side_effect=loader)):
            engine=FasterWhisperEngine(dict(model='base',model_path='/local',threads=2,beam_size=3))
            engine.warm()
            self.assertEqual(engine._transcribe_region([],None)['text'],'complete transcript')
        self.assertEqual(loads,['cuda','cpu'])
