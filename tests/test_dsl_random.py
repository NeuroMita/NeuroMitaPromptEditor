import unittest
from types import SimpleNamespace
from unittest.mock import patch

from logic import dsl_primitives
from logic.dsl_engine import DslError, DslInterpreter
from logic.dsl_parser import parse_script
from logic.dsl_runner import DslAstRunner


class RandomTests(unittest.TestCase):
    def evaluators(self):
        character = SimpleNamespace(
            char_id="Test", variables={"low": -3, "high": 7}, app_vars={}
        )
        interpreter = DslInterpreter(character, None)
        runner = DslAstRunner()
        runner.variables.update(character.variables)
        return (
            (
                "interpreter",
                lambda expr: interpreter._eval_expr(expr, "random.script", 12, expr),
                DslError,
            ),
            ("node runner", runner._eval_expr, ValueError),
        )

    def test_fraction_and_inclusive_bounds_in_both_evaluators(self):
        for name, evaluate, _ in self.evaluators():
            with self.subTest(evaluator=name):
                with patch.object(dsl_primitives._random, "random", return_value=0.125):
                    self.assertEqual(evaluate("random()"), 0.125)
                    self.assertTrue(evaluate("random() < 0.25"))
                with patch.object(
                    dsl_primitives._random, "randint", side_effect=[-3, 7]
                ) as rng:
                    self.assertEqual(evaluate("random(low, high)"), -3)
                    self.assertEqual(evaluate('f"roll={random(low, high)}"'), "roll=7")
                    self.assertEqual(rng.call_args_list[0].args, (-3, 7))
                    self.assertEqual(rng.call_args_list[1].args, (-3, 7))

    def test_invalid_calls_explain_the_problem_without_drawing(self):
        cases = (
            ("random(1)", "no arguments or two integer bounds"),
            ("random(1, 2, 3)", "no arguments or two integer bounds"),
            ("random(5, 1)", "min <= max"),
            ("random(1.5, 3)", "integer bounds"),
            ("random(True, 3)", "booleans are not accepted"),
            ("random('1', 3)", "integer bounds"),
        )
        for name, evaluate, error in self.evaluators():
            for expression, message in cases:
                with self.subTest(evaluator=name, expression=expression):
                    with patch.object(dsl_primitives._random, "randint") as rng:
                        if name == "interpreter":
                            with self.assertLogs("dsl_script", level="ERROR"):
                                with self.assertRaisesRegex(error, message):
                                    evaluate(expression)
                        else:
                            with self.assertRaisesRegex(error, message):
                                evaluate(expression)
                        rng.assert_not_called()

    def test_real_ranges_and_equal_bounds(self):
        for _ in range(100):
            self.assertTrue(0 <= dsl_primitives.random() < 1)
            roll = dsl_primitives.random(-2, 2)
            self.assertIsInstance(roll, int)
            self.assertTrue(-2 <= roll <= 2)
        self.assertEqual(dsl_primitives.random(4, 4), 4)

    def test_scripts_store_one_roll_and_skip_the_other_branch(self):
        source = "\n".join(
            [
                "SET LOCAL roll = random(1, 3)",
                "IF roll == 2 THEN",
                'RETURN "selected=" + str(roll)',
                "ELSE",
                "RETURN str(random(10, 20))",
                "ENDIF",
            ]
        )
        resolver = SimpleNamespace(
            resolve_path=lambda path: path,
            get_dirname=lambda path: "",
            load_text=lambda path, context: source,
        )
        character = SimpleNamespace(char_id="Test", variables={}, app_vars={})
        with patch.object(dsl_primitives._random, "randint", return_value=2) as rng:
            text, _ = DslInterpreter(character, resolver).process_script(
                "random.script"
            )
            self.assertEqual(text, "selected=2")
            self.assertEqual(character.variables, {})
            rng.assert_called_once_with(1, 3)

        script, errors = parse_script(source)
        self.assertEqual(errors, [])
        with patch.object(dsl_primitives._random, "randint", return_value=2) as rng:
            report = DslAstRunner().run(script)
            self.assertEqual(report.final_text, "selected=2")
            self.assertTrue(
                all(info.error is None for info in report.node_results.values())
            )
            rng.assert_called_once_with(1, 3)


if __name__ == "__main__":
    unittest.main()
