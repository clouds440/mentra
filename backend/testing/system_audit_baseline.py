"""Run current regressions against frozen pre-fix modules, without checking out files."""
import importlib
import subprocess
import unittest


def main():
    for name in ('app.files.service','app.chat.repositories.postgres',
                 'app.langchain.repositories.evidence','app.speech.service'):
        module=importlib.import_module(name)
        path='backend/'+name.replace('.','/')+'.py'
        source=subprocess.check_output(['git','show','c3f0537:'+path],text=True,encoding='utf-8')
        exec(compile(source,path,'exec'),module.__dict__)
    suite=unittest.defaultTestLoader.loadTestsFromName('backend.tests.test_system_audit_regressions')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())


if __name__=='__main__': main()
