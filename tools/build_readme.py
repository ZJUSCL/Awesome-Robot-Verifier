#!/usr/bin/env python3
r"""Regenerate README.md from the survey's refs.bib and its section files.

A paper's placement in the reading list is derived from where the manuscript
treats it, so the list and the survey cannot drift apart. Run:

    python3 tools/build_readme.py --survey ../../  --out README.md

--survey points at the LaTeX project root (the directory holding refs.bib and
src/). Both paths default to the layout this repository was generated from.

The rules, in order:

  * every \cite{...} in the section files is collected; % comments and
    \iffalse ... \fi blocks are stripped first, so text the manuscript does not
    typeset contributes no entries;
  * a paper is filed in the FIRST bucket that cites it, walking the bucket list
    top to bottom, so a work cited in both the introduction and §4 lands in §4;
  * within a bucket, papers are grouped by the heading that first cites them,
    at the levels SPLIT_LEVELS declares for that bucket;
  * entries sort newest first, then alphabetically by title.

The section list below tracks the manuscript as it stands: §2 human, §3 rules,
§4 learned, §5 model-intrinsic, §6 validating the verifier, §1 background. The
appendix that used to carry a catalogue of world models, datasets, and adjacent
surveys is gone from the manuscript, and with it those entries; this list holds
what the survey actually cites and nothing else.

No network access. Links come from the `url` or `doi` field when present, then
from an arXiv identifier found in `eprint` or in `journal`/`note`/`pages`, then
from tools/arxiv_ids.json, and fall back to a Google Scholar title search.

tools/arxiv_ids.json maps a citation key to its arXiv identifier. It exists
because refs.bib now records the venue a paper was finally published in, which
overwrites the `arXiv preprint arXiv:NNNN.NNNNN` string the identifier used to
be read out of. The preprint is still the copy a reader can open, so the map
keeps it. Add a line when a new key has an arXiv version; the build prints
every key it could not resolve.
"""
import argparse, json, os, re, urllib.parse

CITE = re.compile(r"\\cite[tp]?\*?(?:\[[^\]]*\])*\{([^}]*)\}")


def parse_bib(path):
    txt = open(path, encoding="utf-8").read()
    entries = {}
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]+),", txt):
        key = m.group(2).strip()
        # take the balanced body
        i = txt.index("{", m.start())
        depth, j = 0, i
        while j < len(txt):
            if txt[j] == "{": depth += 1
            elif txt[j] == "}":
                depth -= 1
                if depth == 0: break
            j += 1
        body = txt[i+1:j]
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*", body):
            fname = fm.group(1).lower()
            k = fm.end()
            while k < len(body) and body[k] in " \t\n": k += 1
            if k >= len(body): continue
            if body[k] == "{":
                d, e = 0, k
                while e < len(body):
                    if body[e] == "{": d += 1
                    elif body[e] == "}":
                        d -= 1
                        if d == 0: break
                    e += 1
                val = body[k+1:e]
            elif body[k] == '"':
                e = body.index('"', k+1)
                val = body[k+1:e]
            else:
                e = k
                while e < len(body) and body[e] not in ",\n": e += 1
                val = body[k:e]
            fields[fname] = val
        entries[key] = fields
    return entries


def clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\\&", "&").replace("~", " ")
    s = re.sub(r"\\['`\"^=.]\{?(\w)\}?", r"\1", s)
    s = s.replace("\\ss", "ss").replace("\\o", "o")
    # Model names carrying inline math ($\pi_0.5$) have to survive as plain text:
    # GitHub does not render math inside link text.
    s = s.replace("$", "").replace("\\pi", "\u03c0")
    s = re.sub(r"[_^]\{([^}]*)\}", r"\1", s)
    s = re.sub(r"[_^](?=[\w*])", "", s)
    return re.sub(r"\s+", " ", s).strip()


def authors_short(a):
    a = clean(a)
    if not a: return ""
    parts = [p.strip() for p in re.split(r"\s+and\s+", a) if p.strip()]
    if not parts: return ""
    first = parts[0]
    if "," in first:  # "Last, First"
        last = first.split(",")[0].strip()
    else:
        last = first.split()[-1]
    if len(parts) > 1 or last.lower() == "others":
        return f"{last} et al."
    return last


ARXIV_IDS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "arxiv_ids.json"), encoding="utf-8"))


def arxiv_id(key, f):
    """-> the arXiv identifier for an entry, or ''.

    Entries added after the bib moved to the eprint/archivePrefix form carry the
    identifier in `eprint` rather than inside a `journal` string, so both shapes
    are read here.
    """
    ep = clean(f.get("eprint", ""))
    if re.fullmatch(r"[0-9]{4}\.[0-9]{4,5}", ep):
        return ep
    blob = " ".join(clean(f.get(k, "")) for k in ("journal", "note", "pages", "booktitle"))
    m = re.search(r"ar[Xx]iv[:\s\-]*([0-9]{4}\.[0-9]{4,5})", blob)
    if m: return m.group(1)
    return ARXIV_IDS.get(key, "")


def link_for(key, f):
    if f.get("url"): return clean(f["url"])
    if f.get("doi"): return "https://doi.org/" + clean(f["doi"])
    aid = arxiv_id(key, f)
    return "https://arxiv.org/abs/" + aid if aid else ""


def venue_for(key, f):
    j = clean(f.get("journal", "") or f.get("booktitle", ""))
    if re.search(r"ar[Xx]iv", j) or not j:
        # A preprint-only entry: journal holds "arXiv preprint arXiv:NNNN.NNNNN",
        # or there is no venue field at all and eprint carries the identifier.
        aid = arxiv_id(key, f)
        return "arXiv:%s" % aid if aid else (j or "")
    return j or clean(f.get("publisher", "")) or clean(f.get("institution", ""))


def strip_inert(text):
    """Drop % comments and \\iffalse ... \\fi blocks: neither reaches the PDF."""
    text = re.sub(r"\\iffalse\b.*?\\fi\b", "", text, flags=re.S)
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("%"))


def cited_in(text):
    keys = []
    for m in CITE.finditer(text):
        for k in m.group(1).split(","):
            k = k.strip()
            if k: keys.append(k)
    return keys


# ======================================================================= buckets
# Order matters: a paper is filed in the first bucket that cites it. The four
# judge-source sections come first, so a method named in the introduction or
# used as an example in §6 still files under the section that describes it.
SECTION_FILES = [
    ("human",      "src/human.tex"),
    ("rules",      "src/rules.tex"),
    ("scorers",    "src/scorers.tex"),
    ("intrinsic",  "src/intrinsic.tex"),
    ("meta",       "src/metaevaluation.tex"),
    ("background", "src/introduction_v2.tex"),
]

# Which heading levels carve a section into groups. §3, §4 and §5 do their real
# dividing at \paragraph, so splitting only at \subsection would collapse them
# into three lists of twenty.
SPLIT_LEVELS = {
    "human":     ("subsection",),
    "rules":     ("subsubsection", "paragraph"),
    "scorers":   ("paragraph",),
    "intrinsic": ("subsection", "paragraph"),
    "meta":      ("subsection", "paragraph"),
    "background": ("subsection",),
}

# The manuscript's headings are written to carry an argument, and several are
# section-local ("Optimization", "Monitoring"). A reader arriving at this list is
# searching, not following the argument, so each group is relabelled to say what
# the methods in it ARE.
SUBGROUP_LABELS = {
    ("human", "Comparing Trajectories"):        "Pairwise preference comparison",
    ("human", "Scoring Trajectories"):          "Scalar and per-timestep annotation",
    ("human", "Intervening During Execution"):  "Human-in-the-loop intervention",
    ("human", "Validating Generated Rollouts"): "Human validation of generated rollouts",

    ("rules", "Temporal-Logic Scoring"):                "Temporal-logic specifications and satisfaction margins",
    ("rules", "Calibrated predictive runtime verification"): "Temporal-logic specifications and satisfaction margins",
    ("rules", "Uncalibrated specification evaluation"): "Temporal-logic specifications and satisfaction margins",
    ("rules", "Geometry-Based Scoring"):                "Trajectory-geometry scoring",
    ("rules", "Optimization"):                          "LLM-written reward and monitor code",
    ("rules", "Monitoring"):                            "LLM-written reward and monitor code",
    ("rules", "Benchmark evaluation"):                  "Goal predicates in simulation benchmarks",
    ("rules", "Synthetic data generation and filtering"): "Predicate-filtered demonstration generation",
    ("rules", "Sparse reward for reinforcement learning"): "Sparse binary reward for policy training",
    ("rules", "An invariance certificate that holds for every trajectory"):
                                                        "Control barrier functions and safety filters",
    ("rules", "A symbolic feasibility check before anything moves"):
                                                        "Symbolic feasibility and task-and-motion planning",

    ("scorers", "Process-level scores within a rollout"):   "Dense and process-level reward models",
    ("scorers", "Trajectory-level outcome judgments"):      "Success detection and trajectory-level judgment",
    ("scorers", "Direct candidate selection"):              "Inference-time candidate ranking",
    ("scorers", "Predictive lookahead with world models"):  "World-model lookahead and failure prediction",
    ("scorers", "Direct reward optimization"):              "Learned reward for policy optimization",
    ("scorers", "Self-improvement and rollout filtering"):  "Self-improvement and rollout filtering",
    ("scorers", "Data curation and demonstration scoring"): "Data curation and demonstration scoring",

    ("intrinsic", "Verifying behavior during execution"):   "Runtime failure detection and gating",
    ("intrinsic", "Verifying candidates before execution"): "Action selection from policy self-consistency",
    ("intrinsic", "Trajectory likelihood"):                 "Generative likelihood and latent discrepancy",
    ("intrinsic", "Latent discrepancy"):                    "Generative likelihood and latent discrepancy",
    ("intrinsic", "Model uncertainty"):                     "Model uncertainty and ensemble disagreement",
    ("intrinsic", "Reachability value"):                    "Reachability values and latent safety filters",
    ("intrinsic", "Beyond Action Verification: Task Selection"): "Task and environment selection",
}

# Papers refiled by WHAT THE PAPER IS. Two things are corrected here.
#
# (1) §6 discusses everything it cites under one argument, so its automatic
#     groups are headings like "What Optimization Requires of a Verifier" — no
#     use to someone searching for reward-hacking work. Its keys are listed by
#     subject instead.
# (2) A handful of papers are discussed inside a family section but are not
#     verifiers: a reward-hacking result used to warn about a goal predicate, a
#     corpus, a generalist policy.
#
# Every entry is a deliberate, reviewable choice; correct it in a PR if a paper
# sits wrong.
OVERRIDES = {
    # -- reward hacking: what a score does once something optimizes against it
    "RMOveroptimization": ("hacking", ""),
    "RubricHacking":      ("hacking", ""),
    "TokenSpaceAttack":   ("hacking", ""),
    "InfoRM":             ("hacking", ""),
    "BNRM":               ("hacking", ""),
    "GamingVerifiers":    ("hacking", ""),
    "GoodhartTaxonomy":   ("hacking", ""),
    "Unhackability":      ("hacking", ""),
    "RewardAsAgent":      ("hacking", ""),
    "guo2026vlaw":        ("hacking", ""),
    "fuzzing_verifiers2026": ("hacking", ""),

    # -- benchmarks whose object is the judge, not the policy
    "RoboReward":          ("vbench", ""),
    "OpenGVL":             ("vbench", ""),
    "GESim2":              ("vbench", ""),
    "wmeval_position2026": ("vbench", ""),
    "ASIMOV":              ("vbench", ""),
    "SafeVLABench":        ("vbench", ""),

    # -- how many rollouts a comparison takes, and what to report about it
    "LBM":                     ("evalmethod", ""),
    "PhAIL":                   ("evalmethod", ""),
    "STEP":                    ("evalmethod", ""),
    "N-SCORE":                 ("evalmethod", ""),
    "ActiveEval":              ("evalmethod", ""),
    "EmpiricalScience":        ("evalmethod", ""),
    "agarwal2021precipice":    ("evalmethod", ""),
    "ramdas2023safeanytime":   ("evalmethod", ""),
    "vincent2024generalizable": ("evalmethod", ""),

    # -- the substrates a policy ranking is actually produced on
    "SIMPLER":            ("evalplatform", ""),
    "ImperfectSim":       ("evalplatform", ""),
    "robochallenge2025":  ("evalplatform", ""),
    "kim2026molmospaces": ("evalplatform", ""),
    "yang2026robolab":    ("evalplatform", ""),
    "yang2025simtorealeval": ("evalplatform", ""),

    # -- distribution-free guarantees, and the shifts that void them
    "ConformalCovShift":   ("uq", ""),
    "ConformalBeyondExch": ("uq", ""),
    "AdaptiveConformal":   ("uq", ""),
    "Performative":        ("uq", ""),

    # -- not verifiers: the policies, corpora, and generators the survey runs on
    "brohan2023rt2":   ("subjects", "Generalist policies and corpora"),
    "kim2024openvla":  ("subjects", "Generalist policies and corpora"),
    "black2025pi0":    ("subjects", "Generalist policies and corpora"),
    "PI05":            ("subjects", "Generalist policies and corpora"),
    "pi07_2026":       ("subjects", "Generalist policies and corpora"),
    "OXE":             ("subjects", "Generalist policies and corpora"),
    "Cosmos":            ("subjects", "World models and simulators"),
    "deepmind2025genie3": ("subjects", "World models and simulators"),
    "InteractiveWS":     ("subjects", "World models and simulators"),
    "SimuScene":         ("subjects", "World models and simulators"),

    # -- §6's preamble names it as its example of a runtime gate, and it is the
    #    only work the section cites that is a verifier rather than a way of
    #    measuring one.
    "aegis2026": ("intrinsic", "Runtime failure detection and gating"),

}

# Cited by the manuscript but deliberately not listed: neighbouring-field work
# that is not a robot verifier and not a way of measuring one. Dropping them is
# why the README no longer claims to hold every paper the survey cites.
EXCLUDE = {
    "DeepSeek-R1",          # LLM RL, cited in §1 as motivation
    "RewardModelingSurvey", # reward modelling for LLM reasoning
    "TAMPSurvey",           # task and motion planning
}


def load_sources(root):
    """-> ordered [(bucket, text, heading levels)]."""
    out = []
    for bucket, rel in SECTION_FILES:
        txt = strip_inert(open(os.path.join(root, rel), encoding="utf-8").read())
        out.append((bucket, txt, SPLIT_LEVELS.get(bucket, ("subsection",))))
    return out


def split_by(txt, levels):
    pat = re.compile(r"\\(" + "|".join(levels) + r")\*?\{([^}]*)\}")
    hits = list(pat.finditer(txt))
    out = []
    if not hits:
        return [("", txt)]
    if hits[0].start() > 0:
        out.append(("", txt[: hits[0].start()]))
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(txt)
        out.append((clean(m.group(2)).rstrip("."), txt[m.end() : end]))
    return out


def norm(s):
    return re.sub(r"\s+", " ", s.replace("\u2011", "-").replace("\u2010", "-")).strip()


def build_catalog(root):
    """-> (records, subgroups, unresolved). subgroups: bucket -> [(label, [keys])]."""
    bib = parse_bib(os.path.join(root, "refs.bib"))
    sources = load_sources(root)

    # 1. automatic pass: first citing section wins, grouped by first citing heading
    assigned, placed, unresolved = {}, {}, set()
    for bucket, txt, _ in sources:
        for key in cited_in(txt):
            if key in bib:
                assigned.setdefault(key, bucket)
            else:
                unresolved.add(key)

    for bucket, txt, levels in sources:
        mine = {k for k, v in assigned.items() if v == bucket}
        seen, from_preamble = set(), set()
        for name, part in split_by(txt, levels):
            name = norm(name)
            for k in dict.fromkeys(cited_in(part)):
                if k not in mine:
                    continue
                if k not in seen:
                    seen.add(k)
                    placed[k] = (bucket, name)
                    if not name:
                        from_preamble.add(k)
                elif name and k in from_preamble:
                    # A section preamble that names its own examples must not
                    # capture them: the heading that actually discusses a paper
                    # wins over the sentence that forward-references it.
                    placed[k] = (bucket, name)
                    from_preamble.discard(k)
        for k in mine - seen:
            placed[k] = (bucket, "")

    # 2. relabel the manuscript's argument-shaped headings
    for k, (bucket, name) in list(placed.items()):
        label = SUBGROUP_LABELS.get((bucket, name))
        if label:
            placed[k] = (bucket, label)

    # 3. per-paper overrides
    for k, dest in OVERRIDES.items():
        if k in bib:
            placed[k] = dest

    # 4. drop the deliberate exclusions before anything is counted
    for k in EXCLUDE:
        placed.pop(k, None)

    # 5. materialise, preserving the declared group order per bucket
    subgroups = {}
    for k, (bucket, name) in placed.items():
        subgroups.setdefault(bucket, {}).setdefault(name, []).append(k)
    subgroups = {b: [(n, ks) for n, ks in g.items()] for b, g in subgroups.items()}

    records = {}
    for key, (bucket, _) in placed.items():
        f = bib[key]
        records[key] = dict(
            key=key, bucket=bucket, title=clean(f.get("title", key)),
            authors=authors_short(f.get("author", "")), year=clean(f.get("year", "")),
            venue=venue_for(key, f), url=link_for(key, f),
        )
    return records, subgroups, sorted(unresolved)


# ======================================================================= display
# Part I mirrors §2-§5 of the manuscript, one bucket per judge source. Part II
# mirrors §6 and adds the works the survey leans on without treating them as
# verifiers.
PART_I = ["human", "rules", "scorers", "intrinsic"]
PART_II = ["vbench", "evalmethod", "evalplatform", "hacking", "uq", "subjects"]

B = {
 "human": dict(head="Human verifiers", anchor="human-verifiers", tag="§2",
   desc="A person supplies the judgment, by comparison, by score, or by taking over the controls.",
   fig="assets/human.png",
   cap="Four roles of the human verifier: comparing trajectories, scoring them, intervening during "
       "execution, and validating generated rollouts.",
   order=["Pairwise preference comparison", "Scalar and per-timestep annotation",
          "Human-in-the-loop intervention", "Human validation of generated rollouts"]),
 "rules": dict(head="Rule-based and formal verifiers", anchor="rule-based-and-formal-verifiers", tag="§3",
   desc="The criterion is written before any candidate exists: a predicate, a temporal-logic "
        "specification, a certificate, or code a model generated.",
   fig="assets/rules.png",
   cap="Rule-based verifiers grouped by what the criterion reads: a full trajectory, the terminal "
       "state, or a model of the physics.",
   order=["Temporal-logic specifications and satisfaction margins", "Trajectory-geometry scoring",
          "LLM-written reward and monitor code", "Goal predicates in simulation benchmarks",
          "Predicate-filtered demonstration generation", "Sparse binary reward for policy training",
          "Control barrier functions and safety filters",
          "Symbolic feasibility and task-and-motion planning"]),
 "scorers": dict(head="Learned and pretrained verifiers", anchor="learned-and-pretrained-verifiers", tag="§4",
   desc="A neural model returns the score, either trained on task-specific robot data or queried "
        "straight from pretraining.",
   fig="assets/scorers.png",
   cap="The three roles a learned verifier plays: measuring an execution, choosing among candidates "
       "at inference time, and feeding a score back into policy training or data curation.",
   order=["Dense and process-level reward models", "Success detection and trajectory-level judgment",
          "Inference-time candidate ranking", "World-model lookahead and failure prediction",
          "Learned reward for policy optimization", "Self-improvement and rollout filtering",
          "Data curation and demonstration scoring"]),
 "intrinsic": dict(head="Model-intrinsic verifiers", anchor="model-intrinsic-verifiers", tag="§5",
   desc="The score is a quantity the policy or the world model already computes; no second model is "
        "trained to produce it.",
   fig="assets/intrinsic.png",
   cap="Signals read out of the robot's own policy or world model, used for failure detection, "
       "candidate selection, outcome verification, and choosing what to train on next.",
   order=["Runtime failure detection and gating", "Action selection from policy self-consistency",
          "Generative likelihood and latent discrepancy", "Model uncertainty and ensemble disagreement",
          "Reachability values and latent safety filters", "Task and environment selection"]),

 "vbench": dict(head="Benchmarks that take the verifier as the system under test", anchor="verifier-benchmarks", tag="§6.1",
   desc="They fix the rollouts, fix a reference judgment for each one, and report how often the verifier "
        "agrees with that reference.", order=[]),
 "hacking": dict(head="Reward hacking and overoptimization", anchor="reward-hacking", tag="§6.3",
   desc="What a score does once a policy is searching against it, and what has been tried in response. "
        "Most of this evidence is still from the language side.", order=[]),
 "evalmethod": dict(head="Statistical policy comparison and evaluation practice",
   anchor="policy-evaluation-methodology", tag="§6.1",
   desc="How many rollouts a comparison takes, what interval belongs around a rate, and what a paper "
        "should report about it.", order=[]),
 "evalplatform": dict(head="Real-robot and sim-to-real evaluation platforms",
   anchor="evaluation-platforms", tag="§6.1",
   desc="The substrates a policy ranking is actually produced on, and the corrections applied when the "
        "ranking comes from a proxy.", order=[]),
 "uq": dict(head="Conformal calibration and distribution shift", anchor="conformal-calibration", tag="§6.3",
   desc="Distribution-free guarantees, the exchangeability they need, and what training a policy "
        "against a calibrated verifier does to it.", order=[]),
 "subjects": dict(head="Policies, corpora, and simulators", anchor="subjects", tag="§1",
   desc="Not verifiers. These are the things a verifier is pointed at, or the generators that produce "
        "the behaviour it reads.",
   order=["Generalist policies and corpora", "World models and simulators"]),
}


def slugify(bucket, name):
    base = re.sub(r"[^a-z0-9]+", "-", (name or "all").lower()).strip("-")
    return "%s.%s" % (bucket, base)


def ordered_groups(bucket, subgroups):
    """Declared order first, then anything unforeseen, so nothing is dropped."""
    got = {n: ks for n, ks in subgroups.get(bucket, [])}
    out = [(n, got.pop(n)) for n in B[bucket]["order"] if n in got]
    out += sorted(got.items(), key=lambda kv: -len(kv[1]))
    return out


# Venues that carry no parenthesised acronym in refs.bib, longest match first.
# Checked before the generic acronym rule, so a tracked variant of a venue keeps
# its track rather than collapsing onto the parent conference, and so
# "Robotics and Automation Letters" is not read as ICRA.
VENUE_SHORT = [
    ("Datasets and Benchmarks",                            "NeurIPS D&B"),
    ("Robotics and Automation Letters",                    "RA-L"),
    ("Transactions on Machine Learning Research",          "TMLR"),
    ("International Journal of Robotics Research",         "IJRR"),
    ("Transactions on Pattern Analysis",                   "TPAMI"),
    ("Transactions on Neural Networks",                    "TNNLS"),
    ("Transactions on Cyber-Physical Systems",             "ACM TCPS"),
    ("Association for Computational Linguistics",          "ACL"),
    ("International Joint Conference on Artificial Intelligence", "IJCAI"),
    ("European Conference on Artificial Intelligence",     "ECAI"),
    ("Artificial Intelligence and Statistics",             "AISTATS"),
    ("AAAI Conference",                                    "AAAI"),
    ("Conference on Lifelong Learning Agents",             "CoLLAs"),
    ("Learning for Dynamics and Control",                  "L4DC"),
    ("Annals of Statistics",                               "Ann. Statistics"),
    ("Annual Review of Control",                           "Annu. Rev. Control"),
    ("European Control Conference",                        "ECC"),
    ("Conference on Decision and Control",                 "CDC"),
    ("International Conference on Machine Learning",       "ICML"),
    ("International Conference on Learning Representations", "ICLR"),
    ("Neural Information Processing Systems",              "NeurIPS"),
    ("Conference on Robot Learning",                       "CoRL"),
    ("Robotics: Science and Systems",                      "RSS"),
    ("Robotics and Automation",                            "ICRA"),
]


SITE_URL = "https://zjuscl.github.io/Awesome-Robot-Verifier/"
CONTACT_EMAIL = "wanyang@zju.edu.cn"


def render(REC, SUB, out_path):
    def venue_tag(r):
        v, y = r["venue"], r["year"]
        if v.startswith("arXiv"):
            return "arXiv %s" % y
        if not v:
            return y or "n.d."
        for long, short in VENUE_SHORT:
            if long in v:
                return "%s %s" % (short, y)
        m = re.search(r"\(([A-Z][A-Za-z]{1,7})\b", v)
        if m:
            return "%s %s" % (m.group(1), y)
        m = re.search(r"\b(ICLR|ICML|NeurIPS|CoRL|RSS|ICRA|IROS|CVPR|TMLR)\b", v)
        if m:
            return "%s %s" % (m.group(1), y)
        return "%s %s" % (v[:28], y)

    def entry(k):
        r = REC[k]
        url = r["url"] or ("https://scholar.google.com/scholar?q=" + urllib.parse.quote(r["title"]))
        a = " *%s*" % r["authors"] if r["authors"] else ""
        return "- **`%s`** [%s](%s).%s `%s`" % (venue_tag(r), r["title"].rstrip("."), url, a, k)

    def sortkey(k):
        return (-int(REC[k]["year"] or 0), REC[k]["title"].lower())

    groups = {b: ordered_groups(b, SUB) for b in PART_I + PART_II}
    counts = {b: sum(len(ks) for _, ks in groups[b]) for b in groups}
    TOTAL = len(REC)
    PART_I_TOTAL = sum(counts[b] for b in PART_I)

    L = []
    w = L.append
    w('<a id="readme-top"></a>\n')
    w('<div align="center">\n')
    w("<h1>🤖&ensp;Awesome Robot Verifier</h1>\n")
    w("<strong>A searchable reading list of <em>verifiers for robot policies</em> — anything that reads a "
      "candidate robot behaviour and returns a score, plus the work that measures how good such a score is."
      "</strong><br>\n")
    # A plain emoji nav row: each label carries the link, no badge images and no
    # URL set as text.
    w('<p align="center">')
    w('🌐 <a href="%s"><b>Website</b></a>&ensp;•&ensp;' % SITE_URL)
    w('🧭 <a href="#how-to-read-an-entry"><b>Taxonomy</b></a>&ensp;•&ensp;')
    w('🗂️ <a href="#contents"><b>Browse</b></a>&ensp;•&ensp;')
    w('🤝 <a href="CONTRIBUTING.md"><b>Contribute</b></a>')
    w('</p>\n')
    w('  <!-- TODO(links): add an arXiv entry to the row above once the preprint is public. -->\n')
    w("</div>\n")
    w("🤝 Contributions are welcome: correct a record the manuscript already uses, or add the paper to the "
      "manuscript before proposing it here.\n")
    w("✉️ Contact: %s\n" % CONTACT_EMAIL)
    w('<div align="center">')
    w('<img src="assets/teaser.png" width="94%" alt="Availability against credibility, across the four judge sources">')
    w("<br>")
    w("<em>The four judge sources, ordered by who supplies the judgment. Availability rises from left to "
      "right and credibility falls with it.</em>")
    w("</div>\n")
    w("---\n")

    # ------------------------------------------------------------ contents
    w('<div id="contents"></div>')
    w('<div id="toc"></div>\n')
    w("## 🗂️ Contents\n")
    w("**Part I** is the survey's four judge sources, §2 to §5 of the paper: every verifier method, filed by "
      "who supplies the judgment. **Part II** is §6 and the background — how a verifier is validated, and "
      "the policies, corpora, and generators it is pointed at.\n")

    def toc(bucket_list, title):
        w("**%s**\n" % title)
        for b in bucket_list:
            m = B[b]
            label = ("%s %s" % (m["tag"], m["head"])).strip()
            w("- [%s](#%s) `%d`" % (label, m["anchor"], counts[b]))
            gs = groups[b]
            if len(gs) > 1 or (gs and gs[0][0]):
                for name, keys in gs:
                    w("  - [%s](#%s) `%d`" % (name or "Other", slugify(b, name), len(keys)))
        w("")

    toc(PART_I, "Part I — verifier methods, by who supplies the judgment")
    toc(PART_II, "Part II — validating a verifier, and what it is pointed at")
    w("Also: [Citation](#citation) · [License](#license)\n")

    # ------------------------------------------------------------ how to read a row
    w("### How to read an entry\n")
    w("```")
    w("- **`arXiv 2026`** [Paper Title](link). *First author et al.* `BibKey`")
    w("       venue+year                                             citation key in the survey")
    w("```\n")
    w("The four judge sources of Part I differ along two properties, and the survey's whole argument is that "
      "they move in opposite directions. **Availability** is how much a verdict costs, how early in a "
      "rollout it arrives, and how often it can be asked for. **Credibility** is how much a high score tells "
      "you about the task.\n")
    w("| Judge source | Availability | Credibility |")
    w("| --- | --- | --- |")
    w("| [Human](#human-verifiers) | costly and sparse; each judgment takes human effort | the most direct reference to what the task was meant to be |")
    w("| [Rule-based and formal](#rule-based-and-formal-verifiers) | inexpensive and repeatable, once the state it reads is available | the strongest guarantees here — but only where the predicate, the state estimate, and the dynamics assumptions represent the task |")
    w("| [Learned and pretrained](#learned-and-pretrained-verifiers) | inexpensive to query, dense across tasks and trajectories | bounded by the data the model was trained and validated on |")
    w("| [Model-intrinsic](#model-intrinsic-verifiers) | cheapest of the four; the model already computes it | describes the model, not the task |")
    w("")
    w('<div align="center">')
    w('<img src="assets/timeline.png" width="94%" alt="Representative systems by judge source and year">')
    w("<br>")
    w("<em>Representative systems by judge source and year. Disc area is the number of papers covered at "
      "that point; a dashed ring on 2026 is the full-year estimate. The search closes in early July 2026."
      "</em>")
    w("</div>\n")
    w('<div align="center">')
    w('<img src="assets/property.png" width="82%" alt="What the score asserts, against the judge source">')
    w("<br>")
    w("<em>What the score asserts, plotted against the judge source supplying the criterion. Fill depth is "
      "the number of papers in the cell.</em>")
    w("</div>\n")
    w("---\n")

    # ------------------------------------------------------------ catalog
    def section(b):
        m = B[b]
        w('<div id="%s"></div>\n' % m["anchor"])
        label = ("%s · %s" % (m["tag"], m["head"])) if m["tag"] else m["head"]
        w('## %s <sub><a href="#toc">↑ contents</a></sub>\n' % label)
        w("> %s\n" % m["desc"])
        if m.get("fig"):
            w('<div align="center">')
            w('<img src="%s" width="88%%" alt="%s">' % (m["fig"], m["head"]))
            w("<br><em>%s</em>" % m["cap"])
            w("</div>\n")
        gs = groups[b]
        named = len(gs) > 1 or (gs and gs[0][0])
        for name, keys in gs:
            w('<div id="%s"></div>\n' % slugify(b, name))
            if named:
                w("### %s\n" % (name or "Other"))
            for k in sorted(keys, key=sortkey):
                w(entry(k))
            w("")
        w("---\n")

    w("# Part I — verifier methods, by who supplies the judgment\n")
    w("`%d` papers across the four judge sources, following §2 to §5 of the survey.\n" % PART_I_TOTAL)
    for b in PART_I:
        section(b)
    w("# Part II — validating a verifier, and what it is pointed at\n")
    w("`%d` papers. The first five groups follow §6, which asks how a verifier's own error is measured. "
      "The last is the things a verifier is run on rather than verifiers themselves.\n"
      % (TOTAL - PART_I_TOTAL))
    for b in PART_II:
        section(b)

    # ------------------------------------------------------------ tail
    w('<div id="citation"></div>\n')
    w('## 📌 Citation <sub><a href="#toc">↑ contents</a></sub>\n')
    w("```bibtex")
    w("@article{wan2026nofreechecker,")
    w("  title   = {No Free Checker: A Survey of Verifiers for Robot Policies},")
    w("  author  = {Yang Wan and Xihang Yue and Zhirui Liu and Ziyuan Chu and")
    w("             Shuxun Wang and Yuhan Chen and Xiaonan Jiang and Xukun Zhu and")
    w("             Yubo Dong and Linchao Zhu},")
    w("  journal = {arXiv preprint},   % TODO(citation): real venue and identifier")
    w("  year    = {2026}")
    w("}")
    w("```\n")
    w('<div id="license"></div>\n')
    w('## ⚖️ License <sub><a href="#toc">↑ contents</a></sub>\n')
    w("Original text and figures are MIT licensed. Linked papers, repositories, project pages, names, and "
      "third-party metadata retain their own terms.\n")
    w('<p align="right"><a href="#readme-top">↑ back to top</a></p>')

    open(out_path, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return TOTAL, counts


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_survey = os.path.abspath(os.path.join(here, "..", "..", ".."))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--survey", default=default_survey,
                    help="LaTeX project root holding refs.bib and src/ (default: %(default)s)")
    ap.add_argument("--out", default=os.path.abspath(os.path.join(here, "..", "README.md")),
                    help="README to write (default: %(default)s)")
    args = ap.parse_args()

    records, subgroups, unresolved = build_catalog(args.survey)
    total, counts = render(records, subgroups, args.out)

    print("wrote %s: %d works" % (args.out, total))
    for b in PART_I + PART_II:
        print("  %-13s %3d" % (b, counts[b]))
    # A key left in a bucket PART_I/PART_II does not display would silently
    # disappear from the README, so name it before the count check trips.
    stray = sorted(k for k, r in records.items() if r["bucket"] not in counts)
    if stray:
        print("UNFILED (bucket has no display entry; add one to B, or an OVERRIDES line): "
              + ", ".join(stray))
    assert sum(counts.values()) == total, "papers lost between buckets and render"
    nolink = sorted(k for k, r in records.items() if not r["url"])
    if nolink:
        print("no resolvable link (Scholar fallback): " + ", ".join(nolink))
    if unresolved:
        print("cited but missing from refs.bib: " + ", ".join(unresolved))


if __name__ == "__main__":
    main()
