from uuid import NAMESPACE_URL, uuid5


def learner_id(name):
    return str(uuid5(NAMESPACE_URL, 'mentra:test:' + name))


TEST_LEARNERS = ('alice', 'bob', 's', 'student', 'student-a', 'student-b', 'chat-only', 'other', 'spaced',
                 'strong', 'novice', 'learning', 'regression', 'mixed', 'guided', 'easy-only', 'repeated-item')
