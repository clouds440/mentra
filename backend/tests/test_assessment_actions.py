import unittest
from uuid import uuid4
from app.langchain.assessment_actions import difficulty_action


class DifficultyActionTests(unittest.TestCase):
    def test_only_the_exact_action_and_matching_target_are_recognized(self):
        identifier=str(uuid4())
        for kind,field in [('chat draft','draft_id'),('assessment','assessment_id')]:
            for direction in ['easier','harder']:
                text=f'Make {kind} {identifier} {direction}. Keep the topic, question count and delivery, and preserve the original.'
                self.assertEqual(difficulty_action(text,**{field:identifier}),direction)
                self.assertIsNone(difficulty_action(text,**{field:str(uuid4())}))
                self.assertIsNone(difficulty_action(text+' Also change the topic.',**{field:identifier}))
        self.assertIsNone(difficulty_action('Make it harder',draft_id=identifier))
