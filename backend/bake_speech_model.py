"""Provision once at image build/local setup; requests never download models."""
import os
from faster_whisper.utils import download_model

if __name__ == '__main__':
    model = os.environ.get('SPEECH_MODEL', 'base')
    if model not in {'tiny', 'base', 'small'}:
        raise ValueError('Choose tiny, base, or small multilingual')
    download_model(model, output_dir=os.environ.get('SPEECH_MODEL_PATH', '/opt/mentra/models/speech'))
