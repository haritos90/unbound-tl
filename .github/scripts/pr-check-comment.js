// Create or update the one check comment of a pull request.
// runs in actions/github-script at the repository root.
// env: PR_NUMBER_FILE, REPORT_FILE, RUN_ID of the run holding the artifact.
const fs = require('fs');

const marker = '<!-- gen3tl-pr-check -->';
// a longer comment body is refused
const limit = 65000;

module.exports = async ({ github, context }) => {
  const prNumber = Number(fs.readFileSync(process.env.PR_NUMBER_FILE, 'utf8').trim());
  if (!Number.isSafeInteger(prNumber) || prNumber < 1) {
    throw new Error('Invalid pull request number in pr-check artifact');
  }
  const report = fs.readFileSync(process.env.REPORT_FILE, 'utf8');
  const artifact = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${process.env.RUN_ID}#artifacts`;
  const download = `[Download the pr-check artifact with before/after PNGs](${artifact})`;
  let body = `${marker}\n${report}\n${download}\n`;
  if (body.length > limit) {
    const note = `The complete report is in the pr-check artifact. ${download}`;
    const room = limit - `${marker}\n\n${note}\n`.length;
    const cuts = [...report.matchAll(/^#{2,} /gm)].map(heading => heading.index).filter(at => at <= room);
    body = `${marker}\n${report.slice(0, cuts.length ? cuts[cuts.length - 1] : 0)}\n${note}\n`;
  }
  const comments = await github.paginate(github.rest.issues.listComments, {
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: prNumber,
    per_page: 100,
  });
  const previous = comments.find(comment => comment.body?.includes(marker));
  if (previous) {
    await github.rest.issues.updateComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      comment_id: previous.id,
      body,
    });
  } else {
    await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: prNumber,
      body,
    });
  }
};
