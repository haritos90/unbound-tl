"""Run the repository checks with explicit input roots."""
import argparse
import atexit
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
parser = argparse.ArgumentParser()
parser.add_argument('--module', type=Path)
parser.add_argument('--jobs', type=int, default=4)
parser.add_argument('--project-root', type=Path)
parser.add_argument('--rom', type=Path)
parser.add_argument('--collect', action='store_true')
parser.add_argument('--results', type=Path)
parser.add_argument('--python-only', action='store_true')
args = parser.parse_args()
if args.jobs < 1:
    parser.error('jobs: positive integer required')
if args.module:
    args.module = args.module.resolve()
if args.results:
    args.results = args.results.resolve()
if args.project_root:
    os.environ['GEN3TL_UNBOUND_PROJECT'] = str(args.project_root.resolve())
if args.rom:
    os.environ['GEN3TL_TEST_ROM'] = str(args.rom.resolve())
if (ROOT / 'src').is_dir():
    sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(HERE / 'support'))
for path in sorted(HERE.rglob('*.py')):
    if path.parent.name != 'fixtures':
        sys.path.append(str(path.parent))
from gen3tl import TOOLKIT_ROOT
os.environ['GEN3TL_WEB_ROOT_URL'] = (TOOLKIT_ROOT / 'web').as_uri() + '/'
opened = set()
def audit(event, arguments):
    if event == 'open' and isinstance(arguments[0], (str, bytes)):
        path = os.path.abspath(os.fsdecode(arguments[0]))
        if '/fixtures/' in path:
            opened.add(path)
sys.addaudithook(audit)
def save_opens():
    if os.environ.get('GEN3TL_FIXTURE_AUDIT'):
        Path(os.environ['GEN3TL_FIXTURE_AUDIT']).write_text(json.dumps(sorted(opened), indent=2))
atexit.register(save_opens)
os.chdir(ROOT)
if os.environ.get('GEN3TL_TEST_ROM') and not args.collect:
    from rom_support import prepare_inputs
    prepare_inputs()
suite = unittest.TestSuite()
roots = [HERE]
for folder in roots:
    loader = unittest.TestLoader()
    if args.module:
        module = args.module.resolve()
        if not module.is_relative_to(folder) or module.suffix != '.py':
            continue
        suite.addTests(loader.discover(str(module.parent), pattern=module.name, top_level_dir=str(ROOT)))
    else:
        suite.addTests(loader.discover(str(folder), top_level_dir=str(ROOT)))
def flatten(items):
    for item in items:
        if isinstance(item, unittest.TestSuite): yield from flatten(item)
        else: yield item
ids = [item.id() for item in flatten(suite)]
if args.collect:
    print(json.dumps(ids))
    raise SystemExit(any('_FailedTest' in value for value in ids))
if not args.module and args.jobs > 1 and not any('_FailedTest' in value for value in ids):
    import collections
    from concurrent.futures import ThreadPoolExecutor
    import tempfile

    modules = sorted({Path(sys.modules[item.__class__.__module__].__file__).resolve()
                      for item in flatten(suite)})
    combined = {'ids': [], 'run': 0, 'records': {}, 'failures': [], 'errors': [], 'skipped': []}
    with tempfile.TemporaryDirectory(prefix='gen3tl-checks-') as temporary:
        temporary = Path(temporary)

        def run_module(index_path):
            index, path = index_path
            report = temporary / f'{index}.json'
            audit_path = temporary / f'{index}-opens.json'
            environment = dict(os.environ, GEN3TL_FIXTURE_AUDIT=str(audit_path))
            command = [sys.executable, str(Path(__file__).resolve()), '--module', str(path),
                       '--python-only', '--results', str(report)]
            run = subprocess.run(command, env=environment, capture_output=True, text=True)
            data = json.loads(report.read_text()) if report.is_file() else {
                'ids': [], 'run': 0, 'records': {}, 'failures': [],
                'errors': [(str(path), run.stdout + run.stderr)], 'skipped': []}
            fixtures = json.loads(audit_path.read_text()) if audit_path.is_file() else []
            return path, run, data, fixtures

        exits = []
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for path, run, data, fixtures in pool.map(run_module, enumerate(modules)):
                opened.update(fixtures)
                exits.append(run.returncode)
                combined['run'] += data['run']
                combined['records'].update(data['records'])
                for name in ('ids', 'failures', 'errors', 'skipped'):
                    combined[name].extend(data[name])
                print(f'module       {path.relative_to(ROOT)}: {data["run"]} tests, exit {run.returncode}', flush=True)
                if run.returncode:
                    print(run.stdout + run.stderr, end='', flush=True)
    if collections.Counter(ids) != collections.Counter(combined['ids']):
        combined['errors'].append(('discovery', 'registered test multiplicity differs'))
        exits.append(1)
    if args.results:
        args.results.write_text(json.dumps(combined, indent=2))
    node = HERE / 'web'
    code = subprocess.call(['node', '--test', str(node)]) if node.is_dir() and not args.python_only else 0
    for reason, count in sorted(collections.Counter(reason for _, reason in combined['skipped']).items()):
        print(f'skipped      {count} tests: {reason}')
    print(f'python       {combined["run"]} tests, {len(combined["failures"])} failures, {len(combined["errors"])} errors, {len(combined["skipped"])} skipped')
    raise SystemExit(int(any(exits) or code != 0))

class Results(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = {}
    def _exc_info_to_string(self, error, test):
        message = super()._exc_info_to_string(error, test)
        if isinstance(error[1], subprocess.CalledProcessError):
            for value in (error[1].stdout, error[1].stderr):
                if value:
                    message += "\n" + (value.decode(errors='replace') if isinstance(value, bytes) else value)
        return message
    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.setdefault(test.id(), {'status': 'passed'})
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records[test.id()] = {'status': 'skipped', 'reason': reason}
    def addError(self, test, error):
        super().addError(test, error)
        self.records[test.id()] = {'status': 'errors', 'message': self._exc_info_to_string(error, test)}
    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.records[test.id()] = {'status': 'failed', 'message': self._exc_info_to_string(error, test)}
    def addSubTest(self, test, subtest, error):
        super().addSubTest(test, subtest, error)
        if error:
            self.records[test.id()] = {'status': 'failed' if issubclass(error[0], test.failureException) else 'errors',
                                      'message': self._exc_info_to_string(error, test)}
result = unittest.TextTestRunner(verbosity=2, resultclass=Results).run(suite)
if args.results:
    args.results.write_text(json.dumps({'ids': ids, 'run': result.testsRun, 'records': result.records,
        'failures': [(case.id(), message) for case, message in result.failures],
        'errors': [(case.id(), message) for case, message in result.errors],
        'skipped': [(case.id(), reason) for case, reason in result.skipped]}, indent=2))
node = HERE / 'web'
if args.module:
    module = args.module.resolve()
    node = module if module.suffix == '.mjs' and module.is_relative_to(node) else None
code = subprocess.call(['node', '--test', str(node)]) if node and node.exists() and not args.python_only else 0
if args.module and not ids and not node:
    parser.error('module: outside this test tree or no registered tests')
missing = any(any(word in reason.lower() for word in ('no rom', 'no base rom', 'no unbound', 'catalog.pot', 'inventory.json', 'no published project datasets', 'publication guard is absent', 'project repository', 'no scenarios', 'missing study'))
              for _, reason in result.skipped)
raise SystemExit(int(not result.wasSuccessful() or code != 0 or missing))
