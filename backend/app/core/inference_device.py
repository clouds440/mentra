"""Backend-aware local device selection and one sticky CPU recovery.

No model downloads, domain writes or provider calls belong in this module.
Callers serialize inference and retain their killable outer deadline.
"""
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class DeviceChoice:
    backend: str
    device: str
    compute_type: str
    reason: str


def select_device(backend, preference='auto'):
    if backend not in ('torch','ctranslate2','onnx','cpu-only'):
        raise ValueError('Unknown inference backend')
    if preference not in ('auto', 'cpu', 'cuda'):
        raise ValueError('Local device must be auto, cpu or cuda')
    cpu = DeviceChoice(backend, 'cpu', 'int8' if backend == 'ctranslate2' else 'float32', 'cpu_requested')
    if preference == 'cpu' or backend == 'cpu-only':
        return cpu
    try:
        if backend == 'torch':
            import torch
            supported = torch.cuda.is_available()
            compute = 'float32'  # Keep embedding/reranking precision unchanged.
        elif backend == 'ctranslate2':
            import ctranslate2
            supported = ctranslate2.get_cuda_device_count() > 0
            types = ctranslate2.get_supported_compute_types('cuda') if supported else set()
            compute = next((kind for kind in ('int8_float16', 'float16', 'float32') if kind in types), None)
            supported = supported and compute is not None
        elif backend == 'onnx':
            import onnxruntime
            supported = 'CUDAExecutionProvider' in onnxruntime.get_available_providers()
            compute = 'float32'
        if supported:
            return DeviceChoice(backend, 'cuda', compute, 'accelerator_available')
    except (ImportError, RuntimeError, OSError, ValueError):
        pass
    return DeviceChoice(cpu.backend, cpu.device, cpu.compute_type, 'accelerator_unavailable')


def device_failure(error):
    """Do not turn malformed inputs, asset failures or arbitrary bugs into retries."""
    if isinstance(error, (ValueError, TypeError, FileNotFoundError)):
        return False
    if not isinstance(error, RuntimeError) and not type(error).__module__.startswith('onnxruntime'):
        return False
    message = str(error).lower()
    return any(term in message for term in ('cuda', 'cublas', 'cudnn', 'device-side', 'gpu', 'out of memory'))


def retry_worker_on_cpu(preference, actual_device, remaining, attempt):
    """Recover a native process exit once, within the original inference deadline."""
    return attempt == 0 and preference != 'cpu' and actual_device != 'cpu' and remaining > 0


class LocalModel:
    """Consume lazy results INSIDE action so generator failures also recover."""
    def __init__(self, loader, backend, preference='auto', on_fallback=None):
        self.loader, self.backend = loader, backend
        self.choice = select_device(backend, preference)
        self.model = None
        self.on_fallback = on_fallback
        self._lock = RLock()

    def _cpu(self):
        self.model = None  # Never reuse an accelerator model after device loss.
        if self.on_fallback:
            self.on_fallback()
        self.choice = DeviceChoice(self.backend, 'cpu', 'int8' if self.backend == 'ctranslate2' else 'float32', 'device_failure')
        from app.core.logging import workflow_logger
        workflow_logger.event('inference.cpu_fallback', backend=self.backend)

    def get(self):
        with self._lock:
            if self.model is None:
                fallback = False
                try:
                    self.model = self.loader(self.choice)
                except Exception as error:
                    if self.choice.device != 'cuda' or not device_failure(error):
                        raise
                    fallback = True
                if fallback:
                    # Leave the exception scope before allocating CPU weights;
                    # the traceback otherwise retains the failed GPU model.
                    self._cpu()
                    self.model = self.loader(self.choice)
            return self.model

    def run(self, action):
        with self._lock:
            model = self.get()
            try:
                return action(model)
            except Exception as error:
                if self.choice.device != 'cuda' or not device_failure(error):
                    raise
                pass
            del model
            self._cpu()
            return action(self.get())
