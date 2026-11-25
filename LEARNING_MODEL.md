# tutor learning model (initial implementation)

This add-on is intentionally separate from the existing problem runner. It adds
namespaced SQLite tables for a generic knowledge graph, evidence, references,
and learner-editable learning paths. It uses only Python's standard library.

## Knowledge representation

A knowledge component is simply a distinguishable, addressable element. `kind`
is optional descriptive metadata, not a closed taxonomy. Components can be
related using free-form relation names. Examples include `refines`, `adjacent`,
`part_of`, `equivalent`, `supports`, `recommends`, and `related`.

`requires` means a directed prerequisite relation and is checked for cycles.
Other relations can be cyclic. A prerequisite is informative, not an access
control: the CLI never blocks a learner from attempting a problem.

Problems can introduce, exercise, assess, or apply multiple components.
Evidence is recorded per component and can be attempted, partial, demonstrated,
or strong. These are observations, not a definitive mastery score.

## Learning paths

Paths are separate from the knowledge graph. They contain ordered problem IDs.
A tutor-generated proposal is stored separately and cannot alter the active path
until explicitly accepted. The learner can edit a pending proposal before
accepting it, or reject it. `path next` only reads the accepted path. Exploration
outside that path is not restricted by this subsystem.

The first suggestion algorithm is deliberately transparent and heuristic: it
ranks linked problems using the latest recorded evidence and their component
roles. It does not claim to infer mastery. It is meant to be replaced or refined
as the actual problem runner starts supplying reliable assessment evidence.

## Resource references

References can be attached to a component, a problem, or both. This is a place to
store curated documentation and search results with attribution. It does not
implement a web search client or fetch documents.

## Initial commands

```sh
tutor-learning init
tutor-learning package add systems.basics "Systems Basics" --version 1.0.0
tutor-learning component add systems.basics:recursion "Recursion" --kind concept --package systems.basics
tutor-learning component add systems.basics:base-case "Base case" --kind concept --package systems.basics
tutor-learning relation add systems.basics:base-case systems.basics:recursion supports

tutor-learning problem link recursion.trace systems.basics:recursion --role assesses
tutor-learning evidence record systems.basics:recursion --outcome partial --problem recursion.trace --method tests --confidence 0.6

tutor-learning path create intro-recursion "Introduction to recursion"
tutor-learning path add intro-recursion recursion.trace
tutor-learning path suggest intro-recursion
tutor-learning proposal show proposal-...
tutor-learning proposal accept proposal-...
tutor-learning path next intro-recursion
```

By default data is stored in `.tutor/learning.sqlite3`. Set
`TUTOR_LEARNING_DB` or pass `--db PATH` to use another SQLite database. Existing
tables are not modified; all new tables use the `tutor_` prefix.
