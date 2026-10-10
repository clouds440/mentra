import inspect
from contextlib import contextmanager, asynccontextmanager
from functools import wraps
from .steps import Operation
from .sanitization import safe_metadata


def operation(function=None, *, module=None, name=None, kind='call', result=None, input=None, outcome=None, transaction=False, quiet=False, request_outcome=False):
    def decorate(fn):
        if getattr(fn, '__mentra_observed__', False):
            return fn
        signature = inspect.signature(fn)
        identity, feature = module or fn.__module__, name or fn.__qualname__
        def make(args, kwargs):
            # Signature keys are code-owned; arbitrary **kwargs names never enter logs.
            try:
                bound = signature.bind_partial(*args, **kwargs)
                shape = [key for key in bound.arguments if key not in ('self', 'cls')]
                metadata = dict(parameters=shape[:30], parameter_count=len(shape),
                                parameter_types={key: type(value).__name__[:80] for key, value in bound.arguments.items() if key in shape[:30]})
                if input:
                    metadata.update(safe_metadata(input(bound.arguments)) or {})
            except Exception:
                metadata = dict(parameters=[])
            return Operation(identity, feature, input=metadata, quiet=quiet)
        def finish(step, value):
            try:
                semantic = outcome(value) if callable(outcome) else outcome
                if semantic is not None and semantic not in ('success','rejected','failed','degraded','skipped','cancelled','timeout','deferred','unknown'):
                    semantic = 'unknown'
                step.result(result(value) if result else dict(return_type=type(value).__name__),
                            semantic if step.entry['outcome'] == 'unknown' else None)
                if request_outcome and step.collector.workflow == 'http.request':
                    step.collector.outcome = step.entry['outcome']
            except Exception:
                step.result(dict(metadata_unavailable=True))
            if transaction:
                from .events import emit
                emit('transaction.committed')
        if kind in ('contextmanager', 'scope'):
            @wraps(fn)
            @contextmanager
            def wrapped(*args, **kwargs):
                with make(args, kwargs) as step:
                    try:
                        with fn(*args, **kwargs) as value:
                            yield value
                    except BaseException:
                        from .events import emit
                        emit('transaction.rolled_back' if kind == 'contextmanager' else 'scope.failed')
                        raise
                    else:
                        from .events import emit
                        emit('transaction.committed' if kind == 'contextmanager' else 'scope.completed')
                        step.result(dict(domain_status='committed' if kind == 'contextmanager' else 'staged'), 'success')
        elif kind == 'asynccontextmanager':
            @wraps(fn)
            @asynccontextmanager
            async def wrapped(*args, **kwargs):
                async with make(args, kwargs) as step:
                    async with fn(*args, **kwargs) as value:
                        yield value
                    step.result(dict(domain_status='closed'), 'success')
        elif inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                async with make(args, kwargs) as step:
                    try:
                        value = await fn(*args, **kwargs)
                    except BaseException:
                        if transaction:
                            from .events import emit
                            emit('transaction.rolled_back')
                        raise
                    finish(step, value)
                    return value
        else:
            @wraps(fn)
            def wrapped(*args, **kwargs):
                with make(args, kwargs) as step:
                    try:
                        value = fn(*args, **kwargs)
                    except BaseException:
                        if transaction:
                            from .events import emit
                            emit('transaction.rolled_back')
                        raise
                    finish(step, value)
                    return value
        wrapped.__mentra_observed__ = True
        # Resolve forward references with the original globals for tool/FastAPI consumers.
        try:
            annotations = inspect.get_annotations(fn, eval_str=True)
            wrapped.__annotations__ = annotations
            wrapped.__signature__ = signature.replace(parameters=[p.replace(annotation=annotations.get(p.name, p.annotation)) for p in signature.parameters.values()], return_annotation=annotations.get('return', signature.return_annotation))
        except (NameError, TypeError):
            wrapped.__signature__ = signature
        return wrapped
    return decorate(function) if function is not None else decorate


def connect_module(*, policies=None, include_inherited=False, ignore=(), default_outcome=None):
    def decorate(cls):
        if isinstance(cls, dict):
            return {key: operation(fn, **(policies or {}).get(key, {})) for key, fn in cls.items()}
        policies_by_name = policies or {}
        members = dict(vars(cls))
        if include_inherited:
            for base in cls.__mro__[1:]:
                for key, value in vars(base).items():
                    members.setdefault(key, value)
        for key, descriptor in members.items():
            if key.startswith('_') or key in ignore:
                continue
            mode = staticmethod if isinstance(descriptor, staticmethod) else classmethod if isinstance(descriptor, classmethod) else None
            fn = descriptor.__func__ if mode else descriptor
            if not inspect.isfunction(fn) or getattr(fn, '__isabstractmethod__', False):
                continue
            policy = dict(policies_by_name.get(key, {}))
            if default_outcome:
                policy.setdefault('outcome', default_outcome)
            raw = inspect.unwrap(fn)
            if inspect.isgeneratorfunction(raw) or inspect.isasyncgenfunction(raw):
                if raw is not fn and 'kind' not in policy:
                    import contextlib
                    if fn.__code__.co_filename != contextlib.__file__:
                        raise TypeError(f'{cls.__name__}.{key}: declare a lifecycle kind for a decorated generator')
                    policy['kind'] = 'asynccontextmanager' if inspect.isasyncgenfunction(raw) else 'scope'
                elif raw is fn:
                    policy.setdefault('result', lambda value: dict(lazy_result=True))
                    policy['outcome'] = None
            wrapped = operation(fn, module=fn.__module__, **policy)
            setattr(cls, key, mode(wrapped) if mode else wrapped)
        return cls
    return decorate
