"""Run deterministic tests and optionally save a machine-readable summary."""
import argparse,json,sys,time,unittest
from pathlib import Path

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report');args=parser.parse_args()
 tests=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_*.py')
 started=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(tests)
 summary={'suite':'isolated_backend_regression','passed':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'seconds':round(time.monotonic()-started,3),'failed_tests':[test.id() for test,_ in result.failures+result.errors],'uses_external_api':False,'touches_production_sessions':False}
 if args.report:Path(args.report).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False));return 0 if result.wasSuccessful() else 1

if __name__=='__main__':sys.exit(main())
