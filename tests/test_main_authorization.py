"""Static checks for owner-only legacy management commands."""

from pathlib import Path
import ast
import unittest


OWNER_ONLY_COMMANDS = {
    "change_hunt",
    "forget_hunt",
    "forget_hunter",
    "remove_hunter",
    "who_added",
}


class MainAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "main.py"
        cls.tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))

    def test_sensitive_commands_require_tide44_first(self):
        functions = {
            node.name: node
            for node in self.tree.body
            if isinstance(node, ast.AsyncFunctionDef)
        }
        for name in OWNER_ONLY_COMMANDS:
            with self.subTest(command=name):
                function = functions[name]
                guard = function.body[0]
                self.assertIsInstance(guard, ast.If)
                self.assertIsInstance(guard.test, ast.UnaryOp)
                awaited = guard.test.operand
                self.assertIsInstance(awaited, ast.Await)
                self.assertEqual(awaited.value.func.id, "require_tide44")


if __name__ == "__main__":
    unittest.main()
