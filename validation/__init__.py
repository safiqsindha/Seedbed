"""Validation harness for Seedbed's difficulty score.

Lives outside `seedbed/` on purpose: the library's stated non-goal is "no
LLM calls, no prose generation" (see README), and this package's whole job
is to drive a solver-under-test (an LLM) through recovery tasks and
correlate its accuracy against `difficulty`. It imports `seedbed` as a
library; `seedbed` never imports it back.
"""
