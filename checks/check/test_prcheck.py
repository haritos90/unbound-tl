import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from test_roots import PROJECT_ROOT

SCRIPT = ".github/scripts/pr-check-comment.js"
CHECK = ".github/workflows/pr-check.yml"
FORK = ".github/workflows/pr-check-comment.yml"
COMMENT = "Create or update the check comment"
MARKER = "<!-- gen3tl-pr-check -->"
DOWNLOAD = ("[Download the pr-check artifact with before/after PNGs]"
            "(https://github.example/owner/project/actions/runs/42#artifacts)")
CALL = ("const comment = require('./.github/scripts/pr-check-comment.js');\n"
        "await comment({ github, context });\n")
# the values the runner gives the step expressions
VALUES = {"github.run_id": "42", "github.event.workflow_run.id": "42"}
HARNESS = """
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
const loads = [];
const calls = [];
const read = fs.readFileSync;
fs.readFileSync = (file, ...rest) => {
  if (String(file).endsWith('.js')) loads.push(file);
  else calls.push(['read', file]);
  return read(file, ...rest);
};
const context = {
  repo: { owner: 'owner', repo: 'project' },
  payload: { workflow_run: { id: 42 } },
  serverUrl: 'https://github.example',
};
const github = {
  rest: {
    actions: { listWorkflowRunArtifacts: 'artifacts' },
    issues: {
      listComments: 'comments',
      createComment: async data => calls.push(['create', data]),
      updateComment: async data => calls.push(['update', data]),
    },
  },
  paginate: async (endpoint, options) => {
    assert.equal(options.owner, 'owner');
    assert.equal(options.repo, 'project');
    assert.equal(options.per_page, 100);
    if (endpoint === 'artifacts') {
      assert.equal(options.run_id, 42);
      if (input.error) throw new Error(input.error);
      return input.artifacts;
    }
    assert.equal(endpoint, 'comments');
    assert.equal(options.issue_number, 7);
    return input.comments;
  },
};
// github-script resolves a relative module against the workspace
const workspace = id => require(id.startsWith('.') ? path.resolve(id) : id);
(async () => {
  const found = input.lookup === null || await new AsyncFunction('github', 'context', input.lookup)(github, context);
  if (found) {
    await new AsyncFunction('github', 'context', 'require', input.script)(github, context, workspace);
  }
  process.stdout.write(JSON.stringify({ found, loads, calls }));
})();
"""


def job_steps(text):
    """The steps of the one job, each from its first key, comments dropped."""
    steps = []
    for line in text.split("\n    steps:\n", 1)[1].splitlines():
        if line.startswith("      - "):
            steps.append([line[8:]])
        elif steps and (line.startswith("        ") or not line.strip()):
            steps[-1].append(line)
    return ["\n".join(step) + "\n" for step in steps]


def named(steps, name):
    return next(step for step in steps if step.startswith(f"name: {name}\n"))


def block(step, key):
    return textwrap.dedent(re.search(rf"^( +){key}: \|\n((?:\1  .*\n|\n)*)", step, re.M).group(2))


def bodies(step):
    """Each run or script value of a step, inline or block."""
    return [found.group(2) + "\n" + found.group(3)
            for found in re.finditer(r"^( *)(?:run|script): ?(.*)\n((?:\1  .*\n|\n)*)", step, re.M)]


def mapping(step, key):
    found = re.search(rf"^        {key}:\n((?:          .*\n)+)", step, re.M)
    return dict(line.strip().split(": ", 1) for line in found.group(1).splitlines())


def evaluate(value, values):
    return re.sub(r"\$\{\{ (.+?) \}\}", lambda found: values[found.group(1)], value)


def condition(text):
    return " ".join(re.search(r"^ +if: (?:>-\n)?((?:.*\n)+?)(?=^ +[a-z-]+:)", text, re.M).group(1).split())


class PrCheckWorkflowTest(unittest.TestCase):
    def setUp(self):
        if not all((PROJECT_ROOT / name).is_file() for name in (SCRIPT, CHECK, FORK)):
            self.skipTest("comment workflow belongs to the project repository")
        self.text = {name: (PROJECT_ROOT / name).read_text(encoding="utf-8") for name in (CHECK, FORK)}
        self.steps = {name: job_steps(text) for name, text in self.text.items()}

    def test_both_workflows_run_the_one_comment_script(self):
        for workflow in (CHECK, FORK):
            with self.subTest(workflow=workflow):
                step = named(self.steps[workflow], COMMENT)
                self.assertIn("        uses: actions/github-script@v8\n", step)
                self.assertEqual(block(step, "script"), CALL)
                self.assertEqual(set(mapping(step, "env")), {"PR_NUMBER_FILE", "REPORT_FILE", "RUN_ID"})
                self.assertNotIn("continue-on-error", step)

    def test_artifact_lookup_guards_download_and_comment(self):
        checkout, lookup, download, comment = self.steps[FORK]
        self.assertTrue(checkout.startswith("uses: actions/checkout@v7\n"))
        self.assertIn("        id: artifact\n", lookup)
        self.assertIn("        uses: actions/github-script@v8\n", lookup)
        for step in (download, comment):
            self.assertEqual(condition(step), "steps.artifact.outputs.result == 'true'")
            self.assertNotIn("continue-on-error", step)
        self.assertIn("        uses: actions/download-artifact@v7\n", download)
        self.assertEqual(mapping(download, "with")["name"], "pr-check")
        self.assertEqual(mapping(download, "with")["run-id"], "${{ github.event.workflow_run.id }}")
        self.assertTrue(comment.startswith(f"name: {COMMENT}\n"))

    def test_comment_workflow_serves_forks_with_default_branch_code(self):
        text = self.text[FORK]
        self.assertIn("\npermissions:\n  contents: read\n  actions: read\n  pull-requests: write\n\njobs:\n", text)
        job = text.split("\njobs:\n  comment:\n", 1)[1]
        self.assertEqual(condition(job), "github.event.workflow_run.head_repository.full_name != github.repository")
        checkout = mapping(self.steps[FORK][0], "with")
        self.assertEqual(checkout, {"ref": "${{ github.event.repository.default_branch }}",
                                    "persist-credentials": "false", "sparse-checkout": ".github/scripts"})
        download = named(self.steps[FORK], "Download report and approximate previews")
        folder = mapping(download, "with")["path"]
        self.assertTrue(folder.startswith("${{ runner.temp }}/"))
        self.assertEqual(mapping(named(self.steps[FORK], COMMENT), "env"),
                         {"PR_NUMBER_FILE": folder + "/pr-number.txt", "REPORT_FILE": folder + "/report.md",
                          "RUN_ID": "${{ github.event.workflow_run.id }}"})

    def test_check_job_comments_pull_requests_of_this_repository(self):
        text = self.text[CHECK]
        self.assertIn("\npermissions:\n  contents: read\n\njobs:\n  check:\n", text)
        self.assertEqual(re.findall(r"^  (\S+):\n", text.split("\njobs:\n", 1)[1], re.M), ["check"])
        job = re.search(r"\n  check:\n((?:    .*\n)+?)    steps:\n", text).group(1)
        self.assertIn("    permissions:\n      contents: read\n      pull-requests: write\n", job)
        steps = self.steps[CHECK]
        upload = named(steps, "Upload report and approximate previews")
        comment = named(steps, COMMENT)
        self.assertEqual(steps.index(comment), steps.index(upload) + 1)
        env = mapping(comment, "env")
        folder = mapping(upload, "with")["path"]
        self.assertEqual(env, {"PR_NUMBER_FILE": folder + "/pr-number.txt", "REPORT_FILE": folder + "/report.md",
                               "RUN_ID": "${{ github.run_id }}"})
        self.assertEqual(condition(comment), "always() && steps.changed.outputs.catalog == 'true'"
                         " && github.event.pull_request.head.repo.full_name == github.repository"
                         f" && hashFiles('{env['REPORT_FILE']}') != ''")
        self.assertTrue(condition(upload).startswith("always() && "))

    def test_no_expression_stands_in_a_run_or_script_body(self):
        for workflow in (CHECK, FORK):
            for step in self.steps[workflow]:
                for body in bodies(step):
                    with self.subTest(workflow=workflow, step=step.splitlines()[0]):
                        self.assertNotIn("${{", body)
        record = named(self.steps[CHECK], "Record pull request number")
        self.assertEqual(mapping(record, "env"), {"PR_NUMBER": "${{ github.event.pull_request.number }}"})
        self.assertIn('"$PR_NUMBER"', block(record, "run"))

    def run_step(self, workflow, artifacts=(), comments=(), error=None, report="Result: passed"):
        """Run the comment step of a workflow as the runner does."""
        if not shutil.which("node"):
            self.skipTest("no node")
        steps = self.steps[workflow]
        comment = named(steps, COMMENT)
        lookup = block(named(steps, "Find the check artifact"), "script") if workflow == FORK else None
        source = named(steps, "Download report and approximate previews" if workflow == FORK
                       else "Upload report and approximate previews")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            values = dict(VALUES, **{"runner.temp": str(Path(temporary) / "runner")})
            (workspace / SCRIPT).parent.mkdir(parents=True)
            shutil.copy(PROJECT_ROOT / SCRIPT, workspace / SCRIPT)
            folder = workspace / evaluate(mapping(source, "with")["path"], values)
            folder.mkdir(parents=True)
            (folder / "pr-number.txt").write_text("7\n", encoding="utf-8")
            (folder / "report.md").write_text(report, encoding="utf-8")
            env = {name: evaluate(value, values) for name, value in mapping(comment, "env").items()}
            loaded = str((workspace / SCRIPT).resolve())
            result = subprocess.run(["node", "-e", HARNESS], cwd=workspace, capture_output=True, text=True,
                                    env={**os.environ, **env},
                                    input=json.dumps({"lookup": lookup, "script": block(comment, "script"),
                                                      "artifacts": list(artifacts), "comments": list(comments),
                                                      "error": error}))
        if error:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stderr)
            return None
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output.pop("loads"), [loaded] if output["found"] else [])
        if output["found"]:
            self.assertEqual(output["calls"][:2], [["read", env["PR_NUMBER_FILE"]], ["read", env["REPORT_FILE"]]])
        return output

    def test_missing_check_artifact_skips_report_and_comment(self):
        for artifacts in ([], [{"name": "other-report"}]):
            with self.subTest(artifacts=artifacts):
                self.assertEqual(self.run_step(FORK, artifacts), {"found": False, "calls": []})

    def test_check_artifact_creates_or_updates_comment(self):
        for workflow in (CHECK, FORK):
            for previous in (False, True):
                with self.subTest(workflow=workflow, previous=previous):
                    comments = [{"id": 2, "body": "Unrelated comment"}]
                    if previous:
                        comments.append({"id": 3, "body": MARKER + "old report"})
                    result = self.run_step(workflow, [{"name": "other-report"}, {"name": "pr-check"}], comments)
                    self.assertTrue(result["found"])
                    self.assertEqual(len(result["calls"]), 3)
                    action, data = result["calls"][2]
                    self.assertEqual(action, "update" if previous else "create")
                    self.assertEqual(data["comment_id" if previous else "issue_number"], 3 if previous else 7)
                    self.assertEqual(data["body"], MARKER + "\nResult: passed\n" + DOWNLOAD + "\n")

    def test_oversized_report_posts_its_opening_sections_and_the_artifact(self):
        opening = "# Pull request checks\n\n| entry | ok |\n\n## Project checks\n\n- QA: 0 errors\n\n"
        rules = "## Engine language rules\n\n### fills\n\n" + "- entry: blocker\n" * 5000
        for workflow in (CHECK, FORK):
            for report, kept in ((opening + rules, opening + "## Engine language rules\n\n"),
                                 ("# Pull request checks\n\n" + "x" * 70000 + "\n\n" + rules, "")):
                with self.subTest(workflow=workflow, kept=kept[:30]):
                    result = self.run_step(workflow, [{"name": "pr-check"}], report=report)
                    action, data = result["calls"][2]
                    self.assertEqual(action, "create")
                    self.assertLessEqual(len(data["body"]), 65000)
                    self.assertEqual(data["body"], MARKER + "\n" + kept + "\nThe complete report is in the pr-check "
                                     "artifact. " + DOWNLOAD + "\n")

    def test_artifact_lookup_error_remains_a_failure(self):
        self.run_step(FORK, error="Artifact API unavailable")
