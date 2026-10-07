"""Controlled field variants: two familiarity items, never generated on request."""
from .blueprints import q

# Each pair is independently written for its education level. Unknown fields
# use general academic reasoning, not an LLM guess about a student's major.
VARIANTS = {
    'computing': {
        'high_school': [
            ('An instruction repeats once for each of 5 names. How many times does it run?', ['1', '5', '10'], 1),
            ('Which is safest for keeping an account private?', ['A long unique password', 'Sharing the password', 'Using your name as the password'], 0),
        ],
        'college': [
            ('A condition is true only when A AND B are true. A is true, B is false. The condition is:', ['True', 'False', 'Undefined'], 1),
            ('Why test software with an empty input as well as ordinary input?', ['To check an edge case', 'To change the requirements', 'To guarantee no bugs remain'], 0),
        ],
        'undergraduate': [
            ('Binary search halves a sorted search range each step. Its comparison count grows approximately as:', ['log n', 'n squared', 'n factorial'], 0),
            ('A database transaction should either apply all its changes or none. This is:', ['Atomicity', 'Compression', 'Caching'], 0),
        ],
        'graduate': [
            ('A model uses test-set labels to tune features. Why is its reported test performance unreliable?', ['Data leakage', 'Insufficient training accuracy', 'Too much documentation'], 0),
            ('In distributed systems, a network partition complicates simultaneously guaranteeing:', ['Strong consistency and availability', 'File naming and indentation', 'Local arithmetic and syntax'], 0),
        ],
    },
    'stem': {
        'high_school': [
            ('When testing temperature effects on dissolving, which should be held constant?', ['The amount and type of solute', 'The water temperature', 'The result'], 0),
            ('An object travels 30 metres in 10 seconds. Its average speed is:', ['3 m/s', '10 m/s', '300 m/s'], 0),
        ],
        'college': [
            ('Which unit is appropriate for energy?', ['Joule', 'Metre', 'Second'], 0),
            ('A measured value is reported with an uncertainty. The uncertainty describes:', ['Limits on measurement precision', 'Proof that the measurement is useless', 'A different physical quantity'], 0),
        ],
        'undergraduate': [
            ('Dimensional analysis is useful for checking whether an equation has:', ['Consistent physical units', 'A guaranteed correct physical model', 'No experimental uncertainty'], 0),
            ('If measurement errors are independent, averaging repeated measurements primarily reduces:', ['Random error', 'All systematic bias', 'The true value'], 0),
        ],
        'graduate': [
            ('A parameter is identifiable when:', ['Distinct parameter values can be distinguished from the observations under the model', 'Every fit has a low error', 'Its symbol is unique'], 0),
            ('A sensitivity analysis changes assumptions to examine:', ['How conclusions depend on those assumptions', 'How to remove disagreeing data', 'Whether the hypothesis has a catchy name'], 0),
        ],
    },
    'business': {
        'high_school': [
            ('An item costs $8 to make and sells for $12. Before other costs, the profit per item is:', ['$4', '$8', '$20'], 0),
            ('A budget helps compare expected income with:', ['Expected spending', 'Only the business name', 'Only customer ages'], 0),
        ],
        'college': [
            ('Revenue rises but costs rise by more. Profit will:', ['Necessarily rise', 'Fall, all else equal', 'Stay the same'], 1),
            ('Opportunity cost is:', ['The value of the next-best alternative forgone', 'Every past expense', 'Only a cash payment'], 0),
        ],
        'undergraduate': [
            ('A sunk cost has already been incurred and cannot be recovered. For a new decision it should generally:', ['Not determine the choice between future alternatives', 'Always justify continuing', 'Count as future revenue'], 0),
            ('Why discount future cash flows?', ['To account for timing and the time value of money', 'To make every project profitable', 'To ignore risk'], 0),
        ],
        'graduate': [
            ('An observational estimate of a price change may be biased if prices respond to unobserved demand. This is:', ['Endogeneity', 'Guaranteed random assignment', 'A formatting error'], 0),
            ('A credible counterfactual is needed to estimate:', ['What would have happened without the intervention', 'Only the observed revenue', 'The company logo'], 0),
        ],
    },
    'humanities': {
        'high_school': [
            ('Which is a primary source for studying an event?', ['A diary written by a witness at the time', 'A modern summary of several books', 'A fictional retelling'], 0),
            ('To support an interpretation of a passage, use:', ['Relevant words and details from the passage', 'Only your preference', 'The longest sentence regardless of meaning'], 0),
        ],
        'college': [
            ('A source can be useful even if biased, provided its perspective and context are examined.', ['True', 'False'], 0),
            ('An argument attacks the speaker instead of addressing their claim. This is:', ['An ad hominem move', 'Direct evidence for the claim', 'A controlled comparison'], 0),
        ],
        'undergraduate': [
            ('Corroborating an historical claim means:', ['Comparing it with independent relevant evidence', 'Repeating its wording', 'Ignoring its context'], 0),
            ('A defensible textual interpretation should account for:', ['Supporting details and plausible counterevidence', 'Only one convenient quotation', 'Only the author’s popularity'], 0),
        ],
        'graduate': [
            ('A historiographical analysis primarily examines:', ['How historians have interpreted and debated the past', 'Only a timeline of dates', 'Only the age of a document'], 0),
            ('Reflexivity in qualitative research involves examining:', ['How the researcher’s position and choices influence the inquiry', 'How to eliminate all interpretation', 'Only participant counts'], 0),
        ],
    },
    'health': {
        'high_school': [
            ('Which best reduces the spread of many infections?', ['Appropriate hand hygiene', 'Sharing drinking cups', 'Ignoring symptoms'], 0),
            ('Health advice supported by several careful studies is stronger evidence than one personal story.', ['True', 'False'], 0),
        ],
        'college': [
            ('A preventive measure aims primarily to:', ['Reduce the chance of illness before it occurs', 'Guarantee nobody becomes ill', 'Replace all treatment'], 0),
            ('Why compare similar treated and untreated groups?', ['To help separate treatment effects from other differences', 'To avoid recording outcomes', 'To ensure groups get identical outcomes'], 0),
        ],
        'undergraduate': [
            ('A highly sensitive screening test is especially useful for:', ['Reducing missed cases', 'Guaranteeing no false positives', 'Replacing diagnostic confirmation in all cases'], 0),
            ('Blinding outcome assessors can reduce:', ['Assessment bias', 'Every source of confounding', 'The need for consent'], 0),
        ],
        'graduate': [
            ('Intention-to-treat analysis keeps participants in their originally assigned groups to help preserve:', ['Benefits of randomization', 'Perfect treatment adherence', 'Absence of missing data'], 0),
            ('A statistically significant effect is not necessarily clinically important.', ['True', 'False'], 0),
        ],
    },
}


def domain_questions(level, domain):
    return [q(f'{level}-{domain}-d{index + 1}', 'domain_familiarity', prompt, options, correct,
              .45 + .08 * ['high_school', 'college', 'undergraduate', 'graduate'].index(level))
            for index, (prompt, options, correct) in enumerate(VARIANTS[domain][level])]
