"""Keep upstream Silero segmentation, replacing only its ONNX session adapter."""
from functools import lru_cache
from pathlib import Path
from app.core.inference_device import LocalModel


@lru_cache(maxsize=3)
def _configured(preference):
    import onnxruntime as ort
    from faster_whisper.vad import get_vad_model
    from faster_whisper.utils import get_assets_path
    from app.core.config import settings
    model = get_vad_model()
    if not hasattr(model,'_mentra_cpu_session'):
        model._mentra_cpu_session=model.session
    initial = [model._mentra_cpu_session]

    def load(choice):
        if choice.device == 'cpu' and initial:
            return initial.pop()
        options = ort.SessionOptions()
        options.inter_op_num_threads = options.intra_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        options.log_severity_level = 4
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if choice.device == 'cuda' else ['CPUExecutionProvider']
        session = ort.InferenceSession(str(Path(get_assets_path()) / 'silero_vad_v6.onnx'),
                                      providers=providers, sess_options=options)
        if choice.device == 'cuda' and 'CUDAExecutionProvider' not in session.get_providers():
            raise RuntimeError('CUDA execution provider could not initialize')
        return session

    runtime = LocalModel(load, 'onnx', settings.local_inference_device if preference=='auto' else preference)

    class Session:
        def run(self, *args, **kwargs):
            return runtime.run(lambda session: session.run(*args, **kwargs))

    return model,Session(),runtime


def configure_vad(preference='auto'):
    model,session,runtime=_configured(preference)
    model.session=session
    return runtime
