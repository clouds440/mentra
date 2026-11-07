"""Bounded factual scaffolding for Arabic orthography, never a semantic verdict.

Basic-letter joining types follow Unicode 17 ArabicShaping.txt:
https://www.unicode.org/Public/17.0.0/ucd/ArabicShaping.txt
This deliberately abstains on joining controls and unsupported letter ranges.
"""
import re
import unicodedata

RIGHT=set('آأؤإاةدذرزوٱ')
DUAL=set('ئبتثجحخسشصضطظعغفقكلمنهيى')
REFERENCE=('In Arabic reading order, a pair joins only if the first letter can join onward '
    'AND the second can receive a preceding join. ا د ذ ر ز و and ة receive preceding '
    'joins but cannot join onward. ب ت ث ج ح خ س ش ص ض ط ظ ع غ ف ق ك ل م ن ه ي '
    'join on both sides. Thus باب has ب–ا joined and ا–ب separated; درس has both '
    'pairs separated; بيت has both pairs joined. The last letter has no next letter. '
    'ب has one dot below, ت two above, ث three above, ن one above, ي two below. '
    'Name only vowel marks actually present in the written example; an unmarked '
    'final consonant must not be assigned an imaginary vowel or sukun.')


def word_facts(text):
    facts=[];seen=set()
    for token in re.findall(r'[\u0621-\u065f\u0670\u0671\u200c\u200d]+',text):
        if '\u200c' in token or '\u200d' in token:continue
        written=unicodedata.normalize('NFKC',token)
        letters=''.join(c for c in written if unicodedata.category(c)!='Mn')
        if not 2<=len(letters)<=24 or written in seen or any(c not in RIGHT|DUAL|{'ء'} for c in letters):continue
        seen.add(written);marks=[]
        for character in written:
            if unicodedata.category(character)=='Mn':
                if marks:marks[-1]['marks'].append(unicodedata.name(character,'UNKNOWN MARK'))
            else:marks.append(dict(letter=character,marks=[]))
        facts.append(dict(text=letters,written=written,letters=list(letters),marks=marks,
            adjacent_joins=[a in DUAL and b in RIGHT|DUAL for a,b in zip(letters,letters[1:])]))
        if len(facts)==20:break
    return facts
