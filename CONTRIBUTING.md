# Contributing

We want you here. Here's how to help.

## Ways to contribute

You don't need to write code. We need:

- **Testers** — run the pipeline on your models, report what breaks. The [test report template](test-samples/TEST-REPORT-template.md) shows what a good bug report looks like.
- **Documenters** — if the docs confused you, fix them. You just became the expert on what a beginner needs.
- **Model donors** — got a tricky STL that breaks things? Share it (if the license allows). Hard cases make the pipeline better.
- **Coders** — pick an issue, open a PR. See below.

## Ground rules

1. **FOSS only.** Every dependency must be free and open-source. No exceptions.
2. **Verify, don't assume.** If you say it works, show the test. If you didn't test it, say so.
3. **Explain why, not just what.** Code comments should tell the next person *why* you made that choice. Write for the stranger modifying this next year.
4. **Privacy is non-negotiable.** No network calls, no telemetry, no phoning home. If your change needs the internet to work, it doesn't belong here.
5. **One variable per change.** Don't fix three things in one PR. We need to know what fixed what.

## Pull requests

- Fork the repo, branch off `main`, open a PR against `main`.
- Describe what you changed and **why**. Link any issues it addresses.
- Include test results. What did you run? What was the output?
- Update CHANGELOG.md under `[Unreleased]`. Write for users, not developers.
- Be patient. We're a two-person team (one human, one raven). We'll get to it.

## Bug reports

Good bug reports have:
- What you ran (exact command)
- What you expected
- What happened (verbatim output, not paraphrased)
- Your OS and Python version
- The file that broke it (if you can share it)

## Code of conduct

Be decent. We're all here because we like building things. Disagree on the technical merits, not on the person. No harassment, no gatekeeping — beginners asking "dumb" questions are the reason the docs exist.

## License

By contributing, you agree your work goes out under the MIT License, same as everything else here.
