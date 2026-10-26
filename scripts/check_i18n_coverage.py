import yaml
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
MKDOCS = os.path.join(ROOT, 'mkdocs.yml')


class _MkdocsLoader(yaml.SafeLoader):
    """SafeLoader that knows mkdocs' ``!ENV`` tag.

    ``mkdocs.yml`` uses ``!ENV [VAR, default]`` for values that may come from the
    environment. A coverage check only needs the nav tree, but without a
    constructor the whole load fails -- so the check could not run at all, which
    is a worse outcome than resolving the tag to its default.
    """


def _resolve_env(loader, node):
    values = loader.construct_sequence(node, deep=True)
    for candidate in values:
        if isinstance(candidate, str) and os.environ.get(candidate):
            return os.environ[candidate]
        if isinstance(candidate, str) and not candidate.isupper():
            return candidate  # a literal fallback, e.g. "https://..."
    return values[0] if values else ''


_MkdocsLoader.add_constructor('!ENV', _resolve_env)

with open(MKDOCS, 'r', encoding='utf-8') as f:
    cfg = yaml.load(f, Loader=_MkdocsLoader)

nav = cfg.get('nav', [])

# flatten nav to paths
paths = []

def walk(items):
    for it in items:
        if isinstance(it, dict):
            for k, v in it.items():
                if isinstance(v, str):
                    paths.append(v)
                elif isinstance(v, list):
                    walk(v)
        elif isinstance(it, str):
            paths.append(it)

walk(nav)

missing = []
for p in paths:
    # map to zh path
    if p.startswith('zh/'):
        continue
    zh_p = os.path.join(ROOT, 'docs', 'zh', p)
    if os.path.exists(zh_p):
        continue
    # handle paths like 'work/progress_tracker.md' -> zh/work/progress_tracker.md
    zh_candidate = os.path.join(ROOT, 'docs', 'zh', p)
    if not os.path.exists(zh_candidate):
        missing.append(p)

print('Total nav entries:', len(paths))
print('Missing zh translations for:')
for m in missing:
    print('-', m)

# A checker that always exits 0 is a checker nobody can call from CI. The parity
# test wraps this script today, but anyone running it by hand would read the
# list and then see a success status -- the two disagree.
sys.exit(1 if missing else 0)

