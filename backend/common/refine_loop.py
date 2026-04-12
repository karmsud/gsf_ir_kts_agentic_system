"""
GenerateEvaluateRefineLoop — Iterative extraction with convergence check.
Pattern H2: Generate → Evaluate → Refine until quality converges.
"""

from __future__ import annotations

from typing import Any, Callable

from backend.abs.config.constants import GER_MAX_ITERATIONS, GER_CONVERGENCE_THRESHOLD


class GenerateEvaluateRefineLoop:
    """
    Runs a generate-evaluate-refine loop until the output converges
    or max iterations is reached.

    Usage:
        loop = GenerateEvaluateRefineLoop()
        result, iterations = loop.run(
            generator=my_extraction_fn,
            evaluator=my_quality_fn,
            context={"text": section_text},
        )
    """

    MAX_ITERATIONS = GER_MAX_ITERATIONS           # 3
    CONVERGENCE_THRESHOLD = GER_CONVERGENCE_THRESHOLD  # 0.5

    def __init__(
        self,
        max_iterations: int | None = None,
        convergence_threshold: float | None = None,
    ):
        if max_iterations is not None:
            self.MAX_ITERATIONS = max_iterations
        if convergence_threshold is not None:
            self.CONVERGENCE_THRESHOLD = convergence_threshold

    def run(
        self,
        generator: Callable[[dict], Any],
        evaluator: Callable[[Any], float],
        context: dict,
        refiner: Callable[[Any, float, dict], dict] | None = None,
    ) -> tuple[Any, int]:
        """
        Run generate-evaluate-refine until convergence.

        Args:
            generator: Function(context) -> output
            evaluator: Function(output) -> score (0-10)
            context: Initial context dict passed to generator
            refiner: Optional Function(output, score, context) -> updated_context
                    If not provided, uses default refiner that adds feedback

        Returns:
            (final_output, iterations_used)
        """
        best_output = None
        best_score = -1.0
        prev_score = -1.0

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            # Generate
            output = generator(context)

            # Evaluate
            score = evaluator(output)

            # Track best
            if score > best_score:
                best_score = score
                best_output = output

            # Check convergence: if score barely improved, stop
            if iteration > 1:
                improvement = score - prev_score
                if improvement < self.CONVERGENCE_THRESHOLD and score >= 8.0:
                    return best_output, iteration

            # Check if already passing
            if score >= 8.0 and iteration > 1:
                return best_output, iteration

            prev_score = score

            # Refine: update context for next iteration
            if refiner:
                context = refiner(output, score, context)
            else:
                context = self._default_refiner(output, score, context)

        return best_output, self.MAX_ITERATIONS

    @staticmethod
    def _default_refiner(output: Any, score: float, context: dict) -> dict:
        """Default refiner: add feedback to context."""
        updated = dict(context)
        updated["_previous_output"] = output
        updated["_previous_score"] = score
        updated["_feedback"] = (
            f"Previous attempt scored {score:.1f}/10. "
            f"Improve completeness, accuracy, and citations."
        )
        return updated
