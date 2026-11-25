import Std

namespace Syntra

/-! ## Identifiers -/

abbrev ProblemSetId := Nat
abbrev ProblemId    := Nat
abbrev ObjectiveId  := Nat
abbrev LearningPathId := Nat
abbrev LearnerId    := Nat

/-! ## Educational content -/

structure Objective where
  id          : ObjectiveId
  title       : String
  description : String
  deriving Repr, DecidableEq

structure Problem where
  id          : ProblemId
  title       : String
  description : String
  objectives  : List ObjectiveId
  deriving Repr, DecidableEq

/-! ## Knowledge dependencies

An edge (a, b) means that objective a is a
prerequisite for objective b.
-/

abbrev Prerequisite := ObjectiveId × ObjectiveId

/-! ## Learning paths

A learning path is an optional, author-curated
directed graph over objectives.

Its edges express recommended progression,
NOT mandatory knowledge dependencies.
-/

structure LearningPath where
  id          : LearningPathId
  title       : String
  description : String
  objectives  : List ObjectiveId
  edges       : List (ObjectiveId × ObjectiveId)
  deriving Repr, DecidableEq

/-! ## Problem sets -/

structure ProblemSet where
  id            : ProblemSetId
  title         : String
  description   : String
  version       : String
  problems      : List Problem
  objectives    : List Objective
  prerequisites : List Prerequisite
  paths         : List LearningPath
  deriving Repr

/-! ## Graph properties -/

inductive Reaches
    (edges : List (ObjectiveId × ObjectiveId)) :
    ObjectiveId → ObjectiveId → Prop where
  | edge {a b} :
      (a, b) ∈ edges →
      Reaches edges a b
  | trans {a b c} :
      Reaches edges a b →
      Reaches edges b c →
      Reaches edges a c

def Acyclic
    (edges : List (ObjectiveId × ObjectiveId)) : Prop :=
  ∀ x, ¬ Reaches edges x x

/-! ## Problem-set validity -/

def ProblemSet.WellFormed (ps : ProblemSet) : Prop :=
  -- Unique identifiers
  (ps.problems.map Problem.id).Nodup ∧
  (ps.objectives.map Objective.id).Nodup ∧
  (ps.paths.map LearningPath.id).Nodup ∧

  -- Every problem references existing objectives
  (∀ p ∈ ps.problems,
    ∀ o ∈ p.objectives,
      o ∈ ps.objectives.map Objective.id) ∧

  -- Every prerequisite references existing objectives
  (∀ e ∈ ps.prerequisites,
    e.1 ∈ ps.objectives.map Objective.id ∧
    e.2 ∈ ps.objectives.map Objective.id) ∧

  -- Prerequisite graph must be acyclic
  Acyclic ps.prerequisites ∧

  -- Learning paths reference existing objectives
  (∀ path ∈ ps.paths,
    (∀ o ∈ path.objectives,
      o ∈ ps.objectives.map Objective.id) ∧
    (∀ e ∈ path.edges,
      e.1 ∈ path.objectives ∧
      e.2 ∈ path.objectives) ∧
    Acyclic path.edges)

/-! ## Learner state -/

structure LearnerState where
  learner              : LearnerId
  masteredObjectives   : List ObjectiveId
  completedProblems    : List ProblemId
  deriving Repr

def Mastered
    (learner : LearnerState)
    (objective : ObjectiveId) : Prop :=
  objective ∈ learner.masteredObjectives

/-! ## Readiness and progression -/

/-- An objective is ready when all its
    prerequisite objectives have been mastered. -/
def ReadyObjective
    (ps : ProblemSet)
    (learner : LearnerState)
    (objective : ObjectiveId) : Prop :=
  objective ∈ ps.objectives.map Objective.id ∧
  ¬ Mastered learner objective ∧
  ∀ (before after : ObjectiveId),
    (before, after) ∈ ps.prerequisites →
    after = objective →
    Mastered learner before

/-- A problem is eligible when it addresses at
    least one objective that is ready to learn. -/
def EligibleProblem
    (ps : ProblemSet)
    (learner : LearnerState)
    (problem : Problem) : Prop :=
  problem ∈ ps.problems ∧
  ∃ objective ∈ problem.objectives,
    ReadyObjective ps learner objective

/-! ## Learning-path applicability -/

/-- A learning path can be selected independently
    of the learner's mastery state.

    Applicability and recommendation policies
    will be specified separately.
-/

def ContainsObjective
    (path : LearningPath)
    (objective : ObjectiveId) : Prop :=
  objective ∈ path.objectives

end Syntra

