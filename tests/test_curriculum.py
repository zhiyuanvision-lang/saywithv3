import hashlib,json,tempfile,unittest
from pathlib import Path
from modules.curriculum import CurriculumRepository
from modules.curriculum.packaging import verify_release

ROOT=Path(__file__).resolve().parents[1]

class CurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.repo=CurriculumRepository(ROOT)

    def test_generation_uses_reviewed_contract_and_no_legacy_candidates(self):
        t=self.repo.get_target('ARRANGE.A2.s2')
        self.assertEqual(t['outcome'],'提出可行替代时间')
        self.assertNotIn('gse_candidate_links',t)
        self.assertEqual(t['generation_contract']['target_version'],self.repo.version)
        for r in t['reviewed_standard_references']:
            self.assertFalse(r['official_equivalence'])
            self.assertFalse(r['learner_score_authority'])

    def test_returned_contract_cannot_mutate_repository(self):
        t=self.repo.get_target('ARRANGE.A2.s2');t['generation_contract']['main_outcome']='changed'
        self.assertEqual(self.repo.get_target('ARRANGE.A2.s2')['generation_contract']['main_outcome'],'提出可行替代时间')

    def test_missing_target_fails_instead_of_selecting_a_neighbor(self):
        with self.assertRaises(KeyError):self.repo.get_target('MISSING')

    def test_path_cannot_escape_workspace(self):
        with self.assertRaises(ValueError):self.repo.resolve('../../../outside.json')

    def test_candidate_lookup_excludes_known_sense_and_child_audience(self):
        rows=self.repo.query_senses(query='time',limit=10)
        self.assertTrue(rows)
        self.assertTrue(all(r['audience'] in ['GL','SSGL'] for r in rows))
        excluded=rows[0]['id'];more=self.repo.query_senses(query='time',limit=10,excluded_ids=(excluded,))
        self.assertNotIn(excluded,{r['id'] for r in more})

    def test_percent_is_literal_and_not_a_wildcard(self):
        rows=self.repo.query_senses(query='%',limit=100)
        self.assertTrue(all('%' in r['expression'] for r in rows))

    def test_data_is_not_modified_by_reads(self):
        path=self.repo.resolve(self.repo.map['lexicon']['database'])
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        self.repo.query_senses(query='hello')
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_source_integrity_and_references(self):
        self.assertEqual(self.repo.validate()['status'],'passed')

if __name__=='__main__':unittest.main()
