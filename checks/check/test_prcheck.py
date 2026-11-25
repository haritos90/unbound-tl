import json
import shutil
import subprocess
import unittest
from pathlib import Path

from test_roots import PROJECT_ROOT

class PrCheckWorkflowTest(unittest.TestCase):
    def setUp(self):
        root = PROJECT_ROOT
        workflow = root / ".github/workflows/pr-check-comment.yml"
        if not workflow.is_file():
            self.skipTest("comment workflow belongs to the project repository")
        self.steps = workflow.read_text(encoding="utf-8").split("      - name: ")[1:]

    def test_artifact_lookup_guards_download_and_comment(self):
        lookup, download, comment = self.steps
        self.assertIn("        id: artifact\n", lookup)
        self.assertIn("        uses: actions/github-script@v8\n", lookup)
        for step in (download, comment):
            self.assertIn("        if: steps.artifact.outputs.result == 'true'\n", step)
            self.assertNotIn("continue-on-error", step)
        self.assertIn("        uses: actions/download-artifact@v7\n", download)
        self.assertIn("          name: pr-check\n", download)
        self.assertIn("          run-id: ${{ github.event.workflow_run.id }}\n", download)

    def run_scripts(self, artifacts, comments=(), error=None, report="Result: passed"):
        if not shutil.which("node"):
            self.skipTest("no node")
        scripts = [step.split("          script: |\n", 1)[1]
                   for step in self.steps if "          script: |\n" in step]
        harness = """
const assert = require('node:assert/strict');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
const calls = [];
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
const files = { number: '7\\n', report: input.report };
const read = module => {
  assert.equal(module, 'fs');
  return { readFileSync: path => {
    calls.push(['read', path]);
    assert.ok(Object.hasOwn(files, path));
    return files[path];
  } };
};
const env = { PR_NUMBER_FILE: 'number', REPORT_FILE: 'report', RUN_ID: '42' };
(async () => {
  const found = await new AsyncFunction('github', 'context', input.scripts[0])(github, context);
  if (found) {
    await new AsyncFunction('github', 'context', 'require', 'process', input.scripts[1])(
      github, context, read, { env });
  }
  process.stdout.write(JSON.stringify({ found, calls }));
})();
"""
        result = subprocess.run(["node", "-e", harness], capture_output=True, text=True,
                                input=json.dumps({"scripts": scripts, "artifacts": artifacts,
                                                  "comments": comments, "error": error, "report": report}))
        if error:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stderr)
            return
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_missing_check_artifact_skips_report_and_comment(self):
        for artifacts in ([], [{"name": "other-report"}]):
            with self.subTest(artifacts=artifacts):
                self.assertEqual(self.run_scripts(artifacts), {"found": False, "calls": []})

    def test_check_artifact_creates_or_updates_comment(self):
        marker = "<!-- gen3tl-pr-check -->"
        for previous in (False, True):
            with self.subTest(previous=previous):
                comments = [{"id": 2, "body": "Unrelated comment"}]
                if previous:
                    comments.append({"id": 3, "body": marker + "old report"})
                result = self.run_scripts([{"name": "other-report"}, {"name": "pr-check"}], comments)
                self.assertTrue(result["found"])
                self.assertEqual(result["calls"][:2], [["read", "number"], ["read", "report"]])
                self.assertEqual(len(result["calls"]), 3)
                action, data = result["calls"][2]
                self.assertEqual(action, "update" if previous else "create")
                self.assertEqual(data["comment_id" if previous else "issue_number"], 3 if previous else 7)
                self.assertEqual(data["body"], marker + "\nResult: passed\n"
                                 "[Download the pr-check artifact with before/after PNGs]"
                                 "(https://github.example/owner/project/actions/runs/42#artifacts)\n")

    def test_oversized_report_posts_its_opening_sections_and_the_artifact(self):
        marker = "<!-- gen3tl-pr-check -->"
        artifact = "(https://github.example/owner/project/actions/runs/42#artifacts)"
        opening = "# Pull request checks\n\n| entry | ok |\n\n## Project checks\n\n- QA: 0 errors\n\n"
        rules = "## Engine language rules\n\n### fills\n\n" + "- entry: blocker\n" * 5000
        for report, kept in ((opening + rules, opening + "## Engine language rules\n\n"),
                             ("# Pull request checks\n\n" + "x" * 70000 + "\n\n" + rules, "")):
            with self.subTest(kept=kept[:30]):
                result = self.run_scripts([{"name": "pr-check"}], report=report)
                action, data = result["calls"][2]
                self.assertEqual(action, "create")
                self.assertLessEqual(len(data["body"]), 65000)
                self.assertEqual(data["body"], marker + "\n" + kept + "\nThe complete report is in the pr-check "
                                 "artifact. [Download the pr-check artifact with before/after PNGs]" + artifact + "\n")

    def test_artifact_lookup_error_remains_a_failure(self):
        self.run_scripts([], error="Artifact API unavailable")
