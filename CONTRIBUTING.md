# Contributing

How to contribute to the translations of this project. A web browser, the ROM of the game and a GitHub account are enough.

## Translate in the editor

1. Open the [translation editor](https://haritos90.github.io/gen3tl/editor) and choose the game and the `Catalog language`.
2. Give `Your ROM`: the original Unbound ROM or a translated Unbound ROM. The text in the original language comes only from this file, so without it the editor shows the translations alone. The file stays in the browser locally on your machine.
3. `Open the editor`. Find a text with the search or the filters and type its translation. The line meters show where a line is too wide for its window.
4. The changes stay in the browser as drafts; work can continue later.

| ROM given | The editor shows |
| --- | --- |
| none | the keys of the texts, the translations and their statuses, with approximate widths |
| the original Unbound ROM or a translated one | in addition, the text in the original language, the search by it, the exact glyphs and the checks that need the original text |

## What a translation keeps

- The meaning of the original text in its context: speaker, addressee, map and neighbouring lines.
- The terms and names of the language's `glossary.tsv`, as the editor shows them beside a text.
- Every placeholder and control code of the original text, except those the rules of the entry allow to drop.
- The fixed form of an inserted word: the sentence is built around it.
- A text addressed to the player avoids forms that mark the player's gender: the player character can be of either gender.
- Consistency with the translations of the same original text, which the context pane of the editor lists.

## Submit the changes

1. Press `Submit`. The page lists the drafts; `Notes for the reviewers` is optional.
2. Press `Open a GitHub issue with these changes`. A long submission downloads as a JSON file: drag it into `Export file` on the form. Drag each downloaded picture into `Pictures`.
3. Submit the issue. A check answers on it: a pull request with the changes, or the reason they were not applied. Editing the issue text runs the check again.
4. A maintainer reviews the pull request and merges it. The merged changes enter the next release of the language.

| Submitted | Written into |
| --- | --- |
| changed translations | the PO files of the language: a new translation as translated; a change of an approved text stays approved |
| term edits | the glossary; the lines that use a renamed term are renamed |
| pictures | the translated pictures of the language |
| notes for translators | the note files, as proposals a reviewer accepts or declines |

- Limits: 50 note changes per submission, 4,000 characters per text, 8 evidence captures per note of at most 3 MiB each, 5 MiB per export.
- A refused submission receives an answer on the issue with the reason.

## Add a language

- Open an issue in this repository and name the language, or
- open a pull request that adds the folder of the language, `translation/<code>/` (README, How languages are stored).

The language then appears in the editor and is translated as described above.

## Contribute through a pull request

The files of a language can also be changed directly.

- A PO entry holds the key of a text and its translation. The gettext flag `fuzzy` on an entry stores the status translated; an entry with a translation and without the flag is approved. A new translation carries the flag.
- The editor's `Submit` page also downloads the changes as a file, for a pull request made by hand.
- A change of the editor, the website or the checks belongs to the toolkit repository, [gen3tl](https://github.com/haritos90/gen3tl), under its `CONTRIBUTING.md`.

## Checks

| Workflow | Runs on | Checks |
| --- | --- | --- |
| `Pull request checks` | changes of the translations, glossaries and settings | the PO files, the quality and layout checks |
| `Pull request check comment` | the completion of `Pull request checks` | a comment with the changed entries and approximate before and after previews |
| `Site` | every push to a branch and every pull request | the data of every language and the assembled site |
| `Commit message check` | every pull request | the message of every commit of the pull request |

- No check reads a ROM or the original text of the game.
- The checks cover fit and form; a maintainer reviews the meaning.

## Review and approval

A text is untranslated, translated or approved.

| Status | Meaning | In a release |
| --- | --- | --- |
| untranslated | no translation yet | the game shows the original text |
| translated | a maintainer merged the translation | yes |
| approved | the text was part of a version whose playtest was reported, or it passed the review of the project | yes |

- Merging the pull request is the review of a contribution. A pull request merges with every check passed.
- Pull requests merge by rebase only: each commit reaches the default branch with its message unchanged.
- A playtest of a released version is reported with the `Playtest report` issue form: the language, the version and what was played. A maintainer then marks approved the translated texts that have not changed since that version.
- A later change of an approved text stays approved.

## Commit messages

```text
type(scope): summary (#N)

- a short line of the body
```

- `type` is one of `feat`, `fix`, `refactor`, `docs`, `test`, `chore` and `perf`.
- `scope` is required, in lowercase letters, digits, `.`, `/` and `-`, such as `translation`, `po` or `release`.
- The summary begins with a lowercase imperative verb, holds at most 15 words and ends without a period.
- ` (#N)` names the GitHub issue the change resolves; a commit that resolves none ends with the summary.
- The optional body follows one blank line, in lines of at most 15 words, usually a list of `- ` lines.
- The rules in full, with examples: the `CONTRIBUTING.md` of the toolkit repository.

An editor submission needs none of this: the check writes its commit.

## License

An editor submission and a pull request contribute under the licenses of this repository (README, License).

| Files | License | Text |
| --- | --- | --- |
| outside `.github/` | CC BY-SA 4.0 | `LICENSE` |
| under `.github/` | the MIT License | `.github/LICENSE` |

## AI-assisted contributions

- A change written with an AI tool follows every rule of this document, as any other change does.
- The contributor reviews and understands every line submitted and answers the review.
- The person who submits a contribution is its sole author and answers for it, whatever tools they used.
