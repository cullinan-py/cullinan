# Cullinan {version} Release Notes

## Overview

Cullinan `{version}` focuses on {summary_en}.

## Highlights

### 1. {highlight_1_title_en}

- {highlight_1_point_1_en}
- {highlight_1_point_2_en}

### 2. {highlight_2_title_en}

- {highlight_2_point_1_en}
- {highlight_2_point_2_en}

### 3. {highlight_3_title_en}

- {highlight_3_point_1_en}
- {highlight_3_point_2_en}

## Compatibility Notes

- {compat_point_1_en}
- {compat_point_2_en}

## Delivery Notes

- {delivery_point_1_en}
- {delivery_point_2_en}

## Upgrade Notes

- {upgrade_point_1_en}
- {upgrade_point_2_en}

## Authoring Rules

- Write the document in English only. Each paragraph or bullet should be clear and concise.
- Do not create separate language sections; the release note is English-primary.
- Prefer concise change summaries tied to actual released work.
- **Compatibility claims describe referents, not only names.** `Nothing removed or renamed` is true of a name that kept its spelling and changed what it points at — a decorator that became a submodule, a function that became a class. Such a change gets its own line in `Compatibility Notes`, next to removed and renamed, so a reader skimming for breakage finds it.
- **Do not offer a symbol count as evidence of compatibility.** `cullinan.__all__` is unchanged at N symbols proves the name set, not the shapes; the break this line has already shipped was invisible to exactly that test. If a count is quoted at all, quote the check that reads shapes beside it.
- **Write every claim so it survives being read alone.** The overview sentence and the section that qualifies it are read by different people on different days; a summary that needs the section to be true is a summary that will be wrong for most readers.
- **Describe what a reader can act on, not how the project's own checks are built.** Names of internal tooling, credentials, exemptions, allowlists and gate outcomes belong in the code that implements them. They are unreadable outside the project, and this note ships with the package. `scripts/check_changelog.py` enforces the same rule on the newest changelog entry: a release note that would fail it is a release note written for the wrong reader.
