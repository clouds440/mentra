"""Run selected suites with verbose workflow logs captured, showing failures only.

Usage: python -m testing.run_workflow_regressions tests.test_assessments ...
TEST_DATABASE_URL must explicitly name an isolated test database.
"""
import contextlib
import sys
import tempfile
import unittest


def main():
    with tempfile.TemporaryFile(mode='w+',encoding='utf-8') as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
            result = unittest.TextTestRunner(stream=log,verbosity=1).run(suite)
        print(f'Ran {result.testsRun} tests; failures={len(result.failures)}, errors={len(result.errors)}, skipped={len(result.skipped)}')
        for case,trace in [*result.failures,*result.errors]:
            print(case.id(), trace, sep='\n')
        return 0 if result.wasSuccessful() else 1


if __name__=='__main__': sys.exit(main())
