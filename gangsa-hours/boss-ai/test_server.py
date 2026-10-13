import unittest, json
from unittest.mock import patch
import server
class Tests(unittest.TestCase):
    def test_input_limits(self):
        for d in ({'stage':'bad','problem':'1234567890'}, {'stage':'report','problem':'short'}, {'stage':'report','problem':'x'*3001}):
            with self.assertRaises(ValueError): server.validate(d)
    def test_missing_key_never_returns_example(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(RuntimeError): server.diagnose({'stage':'questions','problem':'매출 감소 원인을 아직 모릅니다.'})
    def test_structured_response_and_no_actions_in_question_stage(self):
        result={'summary':'확인 필요','facts':['자기보고'],'hypotheses':[],'questions':['비교 기간은?'],'actions':['부적절한 조기 행동'],'limits':['원인 미확인']}
        raw={'status':'completed','model':'test-model','output':[{'content':[{'type':'output_text','text':json.dumps(result)}]}]}
        class Response:
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def read(self): return json.dumps(raw).encode()
        with patch('urllib.request.urlopen',return_value=Response()) as mock:
            out=server.diagnose({'stage':'questions','problem':'매출 감소 원인을 아직 모릅니다.'},key='test-only')
        self.assertEqual(out['result']['actions'],[])
        payload=json.loads(mock.call_args.args[0].data)
        self.assertFalse(payload['store']); self.assertTrue(payload['text']['format']['strict'])
    def test_checkin_validation(self):
        valid={'stage':'report','problem':'오늘 어떤 일을 먼저 해야 할지 모르겠습니다.','context':{'emotion':'답답함','intensity':7,'start_time':'14:00','previous_review':'시간이 부족했습니다.'}}
        self.assertEqual(server.validate(valid)['context']['intensity'],7)
        for v in (0,11,True,'5'):
            with self.assertRaises(ValueError):server.validate({**valid,'context':{'intensity':v}})
    def test_malformed_result_rejected(self):
        with self.assertRaises(ValueError):server.check_result({'summary':'잘못된 결과'})
    def test_example_labels_and_shape(self):
        cases=json.loads((server.ROOT/'examples.json').read_text())
        for c in cases:
            server.check_result(c['result']);self.assertIn('예시',c['result']['summary'])
if __name__=='__main__':unittest.main()
