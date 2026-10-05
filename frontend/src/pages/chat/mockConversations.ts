export interface ChatMessageData {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export interface MockConversation {
  id: string;
  title: string;
  messages: ChatMessageData[];
}

export const sampleConversations: MockConversation[] = [
  {
    id: 'database-normalization',
    title: 'Database normalization',
    messages: [
      {
        id: 'normalization-question',
        role: 'user',
        content: 'Can you explain database normalization with a simple example?',
      },
      {
        id: 'normalization-answer',
        role: 'assistant',
        content: `## Start with the goal

Normalization is a way to organize relational data so each fact has a clear home. It helps reduce duplicated information and prevents update anomalies.

Imagine keeping students and the courses they take in one table:

| student | course | instructor |
| --- | --- | --- |
| Ana | Biology | Dr. Lee |
| Ana | Chemistry | Dr. Park |

If Dr. Lee's name changes, every Biology row needs an update. With many rows, copies can drift apart.

## Separate facts by what they describe

Store students, courses, and enrollments as separate related records:

\`\`\`text
Students(student_id, name)
Courses(course_id, title, instructor_id)
Enrollments(student_id, course_id)
\`\`\`

Now a student's name is stored once, and course details live with the course. The enrollment table connects the two without repeating either set of details.

**A useful way to think about it:** each table should describe one kind of thing, and each non-key fact should depend on that table's key.

Would you like to work through a second example together?`,
      },
    ],
  },
  {
    id: 'newtons-laws',
    title: "Newton's laws",
    messages: [
      {
        id: 'newton-question',
        role: 'user',
        content: "What's the intuition behind Newton's second law?",
      },
      {
        id: 'newton-answer',
        role: 'assistant',
        content: `## Force changes motion

Newton's second law connects the **net force** on an object to how quickly its velocity changes:

\`\`\`text
F = m × a
\`\`\`

For the same object, more net force means more acceleration. For the same force, a heavier object accelerates less.

Think of pushing an empty cart and then the same cart loaded with books: the loaded cart needs a stronger push to speed up at the same rate.`,
      },
    ],
  },
  {
    id: 'python-decorators',
    title: 'Python decorators',
    messages: [
      {
        id: 'decorator-question',
        role: 'user',
        content: 'What does a Python decorator do?',
      },
      {
        id: 'decorator-answer',
        role: 'assistant',
        content: `A decorator wraps a function to add behavior while keeping the original function focused on its main job.

\`\`\`python
@timer
def calculate_total(items):
    return sum(items)
\`\`\`

The \`@timer\` syntax is shorthand for passing \`calculate_total\` through a decorator function and binding the wrapped result back to the same name.`,
      },
    ],
  },
];

export const conversations = sampleConversations.map(({ id, title }) => ({ id, title }));

export const sampleReply =
  'This is a local interface preview, so there is no AI response yet. In the finished experience, Mentra will help you work through the question one step at a time.';
