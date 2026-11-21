"""One seeded pack runs the public workflow in isolation."""

import unittest

from rom_support import needs_rom
from language_workflow import SeededWorkflow

@needs_rom
class SeededWorkflowTest(SeededWorkflow, unittest.TestCase):
    def test_workflow_es(self):
        self.workflow("es")
