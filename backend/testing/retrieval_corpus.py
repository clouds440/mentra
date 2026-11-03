"""Versioned synthetic study judgments; no LLM-generated or private data.

Topic splits keep translations and paraphrases together. This covers learning
workflow failure modes, not the unknown distribution of real learner uploads.
"""
FACTS = [
('math','triangle area','How is triangle area calculated?','Triangle area equals one half times base times perpendicular height.'),
('math','circle area','How is circle area calculated?','Circle area equals pi times the square of its radius.'),
('math','Pythagorean theorem','What is the Pythagorean theorem?','In a right triangle the square of the hypotenuse equals the sum of the squares of the other two sides.'),
('math','arithmetic mean','How is an arithmetic mean calculated?','Add all values and divide their sum by the number of values.'),
('math','median','What is the median?','The median is the middle ordered value; for an even count it is the mean of the two middle values.'),
('physics','Newton second law','How are force mass and acceleration related?','Net force equals mass times acceleration for constant mass.'),
('physics','kinetic energy','What is the formula for kinetic energy?','Translational kinetic energy equals one half times mass times speed squared.'),
('physics','Ohm law','How are voltage current and resistance related?','For an ohmic conductor voltage equals current times resistance.'),
('physics','wave speed','How do frequency and wavelength determine wave speed?','Wave speed equals frequency multiplied by wavelength.'),
('physics','momentum','What is linear momentum?','Linear momentum equals mass multiplied by velocity.'),
('chemistry','atomic number','What determines atomic number?','Atomic number is the number of protons in the atomic nucleus.'),
('chemistry','isotopes','What are isotopes?','Isotopes of an element share the same proton number and have different neutron numbers.'),
('chemistry','covalent bond','What is a covalent bond?','A covalent bond involves atoms sharing electron pairs.'),
('chemistry','ionic bond','What is an ionic bond?','An ionic bond is electrostatic attraction between oppositely charged ions.'),
('chemistry','catalyst','What does a catalyst do?','A catalyst increases reaction rate through an alternative pathway and is regenerated overall.'),
('biology','mitochondria','What happens in mitochondria?','Mitochondria carry out major stages of aerobic respiration and generate ATP.'),
('biology','ribosomes','What do ribosomes do?','Ribosomes translate messenger RNA to synthesize proteins.'),
('biology','osmosis','What is osmosis?','Osmosis is net water movement across a selectively permeable membrane down a water potential gradient.'),
('biology','DNA pairing','Which bases pair in DNA?','In DNA adenine pairs with thymine and cytosine pairs with guanine.'),
('biology','photosynthesis','What does photosynthesis convert?','Photosynthesis converts light energy into chemical energy stored in organic molecules.'),
('computing','binary search','What precondition does binary search require?','Binary search requires ordered data and repeatedly halves the search interval.'),
('computing','stack','How does a stack remove items?','A stack follows last in first out order, abbreviated LIFO.'),
('computing','queue','How does a queue remove items?','A queue follows first in first out order, abbreviated FIFO.'),
('computing','database primary key','What does a database primary key identify?','A primary key uniquely identifies each row and cannot contain null values.'),
('computing','database foreign key','What is a foreign key?','A foreign key constrains values to reference a key in another or the same table.'),
('computing','SQLSTATE 23505','What does SQLSTATE 23505 mean?','PostgreSQL SQLSTATE 23505 denotes a unique constraint violation.'),
('computing','C++ language','What is the C++ language?','C++ is a programming language with classes, templates and deterministic object destruction.'),
('computing','C# language','What is the C# language?','C# is a programming language commonly used with the .NET runtime.'),
('computing','Python decorator','What does a Python decorator do?','A Python decorator wraps or replaces a function or class to add reusable behavior.'),
('computing','Python dictionary','What does a Python dictionary store?','A Python dictionary maps hashable keys to values.'),
('statistics','variance','What does variance measure?','Variance measures squared deviations of values from their mean.'),
('statistics','standard deviation','How is standard deviation related to variance?','Standard deviation is the nonnegative square root of variance.'),
('statistics','independent probability','How are independent joint probabilities calculated?','For independent events the joint probability is the product of their probabilities.'),
('statistics','sample population','How does a sample differ from a population?','A sample is a subset of the population being studied.'),
('statistics','correlation','Does correlation prove causation?','Correlation alone does not establish causation.'),
('geometry','rectangle perimeter','How is rectangle perimeter calculated?','Rectangle perimeter equals twice the sum of length and width.'),
('geometry','cube volume','How is cube volume calculated?','Cube volume equals the cube of its side length.'),
('geometry','parallel lines','What are parallel lines in Euclidean geometry?','Coplanar parallel straight lines never intersect.'),
('geometry','diameter radius','How is diameter related to radius?','A circle diameter is twice its radius.'),
('geometry','triangle angle sum','What is the angle sum of a Euclidean triangle?','Interior angles of a Euclidean triangle sum to 180 degrees.'),
('computing','HTTP 404','What does HTTP 404 indicate?','HTTP 404 indicates that the requested resource was not found.'),
('computing','HTTP 401','What does HTTP 401 indicate?','HTTP 401 indicates that the request lacks valid authentication credentials.'),
('computing','HTTP 403','What does HTTP 403 indicate?','HTTP 403 indicates that the server refuses to fulfill the request.'),
('computing','merge sort','How does merge sort work?','Merge sort divides a sequence, sorts the parts and merges sorted sequences.'),
('computing','hash collision','What is a hash collision?','A hash collision occurs when distinct inputs map to the same hash value.'),
('physics','density','How is density calculated?','Density equals mass divided by volume.'),
('physics','pressure','How is pressure calculated?','Pressure equals perpendicular force divided by area.'),
('physics','power','How is power calculated?','Power is the rate of energy transfer per unit time.'),
('physics','frequency period','How are frequency and period related?','Frequency is the reciprocal of period.'),
('physics','acceleration','What is acceleration?','Acceleration is the rate of change of velocity with time.'),
('language','noun','What is a noun?','A noun names a person, place, thing or concept.'),
('language','verb','What is a verb?','A verb commonly expresses an action, occurrence or state.'),
('language','adjective','What does an adjective modify?','An adjective commonly modifies a noun or noun phrase.'),
('language','adverb','What can an adverb modify?','An adverb can modify a verb, adjective, another adverb or a clause.'),
('language','pronoun','What is a pronoun?','A pronoun can stand in for a noun phrase in a sentence.'),
('urdu','تکون کا رقبہ','تکون کا رقبہ کیسے نکالتے ہیں؟','تکون کا رقبہ بنیاد اور عمودی اونچائی کے حاصل ضرب کا نصف ہوتا ہے۔'),
('urdu','برقی مزاحمت','وولٹیج اور برقی رو کا تعلق کیا ہے؟','اوہم کے قانون کے مطابق وولٹیج برقی رو اور مزاحمت کے حاصل ضرب کے برابر ہے۔'),
('arabic','مساحة المثلث','كيف تحسب مساحة المثلث؟','مساحة المثلث تساوي نصف حاصل ضرب القاعدة في الارتفاع العمودي.'),
('arabic','قانون أوم','ما العلاقة بين الجهد والتيار والمقاومة؟','وفق قانون أوم يساوي الجهد حاصل ضرب التيار في المقاومة.'),
('mixed','FIFO قطار','FIFO قطار میں کون سا عنصر پہلے نکلتا ہے؟','FIFO queue میں پہلے داخل ہونے والا عنصر پہلے نکلتا ہے۔'),
]


def corpus():
    documents, queries = [], []
    for index, (course, topic, question, support) in enumerate(FACTS):
        split = 'calibration' if index < 5 else 'heldout'
        identifier = f'study-{index:02d}'
        # Distinct course IDs ensure no source/course is shared between splits.
        text = f'{topic}\n{support}\nStudy the definition carefully. Check the original notes before using a formula.'
        documents.append(dict(id=identifier, course=f'{split}:{course}', split=split, text=text,
            support=dict(start=len(topic)+1, end=len(topic)+1+len(support)), language=course if course in ('urdu','arabic','mixed') else 'english'))
        for variant, prefix in enumerate(('', 'In these course notes: ', 'Find the supporting explanation: ', 'Use the study material to answer: ')):
            queries.append(dict(id=f'{identifier}-q{variant}', query=prefix+question,
                relevant_source_ids=[identifier], support_span=documents[-1]['support'], split=split,
                course=documents[-1]['course'], language=documents[-1]['language']))
        queries.append(dict(id=f'{identifier}-none', query=f'What is the exact publication date of the original discovery of {topic}?',
            relevant_source_ids=[], split=split, course=documents[-1]['course'], language='english'))
    return documents, queries
