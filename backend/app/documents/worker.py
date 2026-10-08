"""Private subprocess entry point; no RAG, database or model initialization."""
import json
import sys
from pathlib import Path
from app.documents import DocumentReadError, create_document_reader


def main():
    try:
        if sys.platform == 'linux':
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
            resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
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
