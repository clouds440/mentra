"""Private subprocess entry point; no RAG, database or model initialization."""
import json
import sys
from pathlib import Path
from app.documents import DocumentReadError, create_document_reader


def main():
    try:
        if sys.platform == 'linux':
            import resource
            cpu = int(sys.argv[4]) if len(sys.argv) > 4 else 120
            memory = int(sys.argv[5]) if len(sys.argv) > 5 else 1024 ** 3
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        reader = create_document_reader(isolated=False)
        result = reader.read_in_process(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]))
        print(json.dumps(result, ensure_ascii=True))
    except DocumentReadError as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'The file could not be parsed. Upload a valid, unlocked copy.'}))
        sys.exit(1)


if __name__ == '__main__':
    main()
