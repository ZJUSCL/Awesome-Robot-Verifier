# Contributing

Thanks for helping keep this catalog checkable.

An entry does not need to already be cited in the survey. It can enter the
catalog first, through a pull request, and be folded into the next revision
of the paper as the survey catches up.

## What belongs here

A paper belongs in this list if it **produces or validates a verification signal
for robot policies** — anything that reads a candidate robot behaviour and
returns a score, or that measures how good such a score is.

That includes reward models, success detectors, runtime monitors, safety
filters, policy evaluators, and the benchmarks that put those judges on trial.
It does not include policy architectures, control methods, or datasets that
carry no verification signal.

## Placement

Every entry appears **exactly once**, placed by **what it is** — never by the
argument the survey happens to cite it for. If a section heading only makes
sense to someone who has read the survey, it is the wrong heading, and nothing
should be placed under one.

**Part I** is verifier methods, split by who supplies the judgment. These are
§2–§5 of the survey:

| If the judgment comes from | Section |
| --- | --- |
| a person, directly | `§2 · Human verifiers` |
| criteria fixed before any candidate exists — a predicate, a specification, a certificate, or generated code | `§3 · Rule-based and formal verifiers` |
| a neural model, trained for the task or queried from pretraining | `§4 · Learned and pretrained verifiers` |
| a quantity the policy or world model already computes | `§5 · Model-intrinsic verifiers` |

**Part II** is everything that is not itself a verifier method: how a verifier's
own error gets measured (§6), and the things a verifier is pointed at. Pick by
subject:

| If the entry is about | Section |
| --- | --- |
| measuring how often the verifier itself is wrong, or disclosing that error alongside its main result — a benign false-positive rate next to an attack-success rate, for example | `Benchmarks that take the verifier as the system under test` |
| how many rollouts a comparison takes, or what to report about it | `Statistical policy comparison and evaluation practice` |
| a platform a policy ranking is actually produced on, or a correction applied to a proxy ranking | `Real-robot and sim-to-real evaluation platforms` |
| optimizing against a score, or defending a reward model against it | `Reward hacking and overoptimization` |
| distribution-free guarantees and the shifts that void them | `Conformal calibration and distribution shift` |
| a policy architecture, a large corpus, or a generator that produces the behaviour being judged, with no verification signal of its own | `Policies, corpora, and simulators` |

## Opening a pull request

One entry per pull request, in the same format as the surrounding lines:

```markdown
- **`arXiv 2026`** [Paper Title / Tool Name](paper link or code repo). *First Author et al.* `citekey`. optional one-line description.
```

- Use a **canonical** URL: the arXiv abstract page, the DOI, the proceedings
  page, or, for a tool, its repository or project page. Not a PDF mirror, not
  a Semantic Scholar link.
- Keep the entries inside a section sorted **newest first**, then
  alphabetically by title within a year.
- `` `citekey` `` is just the method or system's short, commonly used name.

## Corrections

Corrections are as welcome as additions. The assignment of a paper to a
construction reflects **our reading** rather than the authors'
self-descriptions. If a record is filed under the wrong judge source, or a
guarantee is described more strongly than the paper claims, open an issue and
say what the paper actually reports.
