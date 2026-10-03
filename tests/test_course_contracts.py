"""Check interface boundaries, not model output quality."""
import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1] / 'modules/course_planning'

class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / 'contracts.schema.json').read_text())
        cls.examples = json.loads((ROOT / 'contracts.examples.json').read_text())

    def validate(self, name, data):
        Draft202012Validator({**self.schema, '$ref': '#/$defs/' + name}).validate(data)

    def test_examples(self):
        Draft202012Validator.check_schema(self.schema)
        for name, data in self.examples.items():
            with self.subTest(name=name):
                self.validate(name, data)

    def test_reject_multiple_primary_targets(self):
        data = copy.deepcopy(self.examples['TeachingAssignment'])
        data['target_ids'].append('ARRANGE.A2.s3')
        with self.assertRaises(ValidationError):
            self.validate('TeachingAssignment', data)

    def test_approved_requires_audio(self):
        data = copy.deepcopy(self.examples['LessonPackage'])
        del data['learning_materials'][0]['audio_ref']
        with self.assertRaises(ValidationError):
            self.validate('LessonPackage', data)

    def test_draft_cannot_be_learner_ready(self):
        data = copy.deepcopy(self.examples['LessonPackage'])
        data['quality']['status'] = 'draft'
        data['learner_ready'] = True
        with self.assertRaises(ValidationError):
            self.validate('LessonPackage', data)

    def test_reject_unknown_job_state(self):
        data = copy.deepcopy(self.examples['GenerationJob'])
        data['state'] = 'invented'
        with self.assertRaises(ValidationError):
            self.validate('GenerationJob', data)

if __name__ == '__main__':
    unittest.main()
