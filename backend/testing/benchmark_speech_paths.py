"""Same public audio/model, alternating stored versus transient intake.

Storage is instrumented memory storage, not live Cloudinary. Optional transport
delay is a controlled experiment and is always labelled in the result.
"""
import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from statistics import median
from time import perf_counter, sleep
from uuid import uuid4
from app.core.config import Settings
from app.files.provider import CloudinaryProvider
from app.files.service import FilesService
from app.files.transient import transcribe_file
from app.speech.transient import transcribe_direct
from app.speech.service import SpeechService
from testing.files import MemoryFileProvider
from testing.identities import learner_id
from testing.postgres import PostgresSandbox


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('audio',type=Path)
    parser.add_argument('--baseline-source',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=5)
    parser.add_argument('--transport-delay-ms',type=float,default=0)
    args=parser.parse_args()
    config=Settings(local_inference_device='cpu')
    namespace={'__name__':'app.files.speech_baseline_files','__package__':'app.files'}
    exec(compile(args.baseline_source.read_text(encoding='utf-8'),'pre_fix_files_service.py','exec'),namespace)
    data=args.audio.read_bytes()
    class Provider(MemoryFileProvider):
        def upload(self,*values):
            sleep(args.transport_delay_ms/1000)
            return super().upload(*values)
        def stream(self,*values):
            sleep(args.transport_delay_ms/1000)
            return super().stream(*values)
        def verify(self,row):
            return CloudinaryProvider.verify(self,row)
    with PostgresSandbox() as db:
        provider=Provider()
        old=namespace['FilesService'](db.sessions,provider,config)
        new=FilesService(db.sessions,provider,config)
        processor=SpeechService(config)
        rows=[]
        try:
            processor.warm()
            for trial in range(args.repeats):
                for mode in (('stored','direct') if trial%2==0 else ('direct','stored')):
                    before=(provider.uploads,provider.downloads)
                    started=perf_counter()
                    if mode=='stored':
                        file=old.upload(learner_id('alice'),BytesIO(data),'recording.flac','speech',str(uuid4()))
                        result=transcribe_file(old,processor,learner_id('alice'),file['id'])
                    else:
                        result=transcribe_direct(new,processor,learner_id('alice'),str(uuid4()),data)
                    rows.append(dict(mode=mode,trial=trial,wall_seconds=perf_counter()-started,
                        processing_seconds=result['processing_seconds'],language=result['language'],
                        transcript_sha256=hashlib.sha256(result['text'].encode()).hexdigest(),
                        uploads=provider.uploads-before[0],downloads=provider.downloads-before[1]))
            assert len({row['transcript_sha256'] for row in rows})==1, 'Transcript regression'
            medians={mode:median(row['wall_seconds'] for row in rows if row['mode']==mode) for mode in ('stored','direct')}
            print(json.dumps(dict(audio_sha256=hashlib.sha256(data).hexdigest(),baseline_commit='c3f0537',
                backend='CPU INT8',model=config.speech_model,beam=config.speech_beam_size,threads=config.speech_cpu_threads,
                storage='instrumented memory; no live provider',transport_delay_ms=args.transport_delay_ms,
                medians=medians,rows=rows),indent=2))
        finally:
            processor.close()


if __name__=='__main__': main()
