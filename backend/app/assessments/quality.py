"""High-precision admission checks. Unsupported semantics remain unverified.

The evaluator interprets a small data-only AST; it never execs/evals model code,
imports model-selected modules, calls arbitrary functions or accesses attributes.
"""
import ast
import operator
import math
import re
import unicodedata
from array import array

POLICY = 'assessment-admission-v1'


class UnsupportedCheck(ValueError): pass


def normalized(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def literal(node, names):
    if isinstance(node, ast.Constant) and type(node.value) in (str, int, float, bool, type(None)):
        value = node.value
    elif isinstance(node, ast.Name) and node.id in names:
        value = names[node.id]
    elif isinstance(node, (ast.List, ast.Tuple)) and len(node.elts)<=256:
        values = [literal(child, names) for child in node.elts]
        value = tuple(values) if isinstance(node, ast.Tuple) else values
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        child = literal(node.operand, names)
        if type(child) not in (int, float): raise UnsupportedCheck()
        value = -child if isinstance(node.op, ast.USub) else child
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left, right = literal(node.left,names), literal(node.right,names)
        if not (type(left) in (int,float) and type(right) in (int,float)):
            if not isinstance(node.op,ast.Add) or type(left) is not type(right) or not isinstance(left,(list,tuple,str,array)) or len(left)+len(right)>1024:
                raise UnsupportedCheck()
        value = {ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}[type(node.op)](left,right)
    elif isinstance(node, ast.Subscript) and isinstance(node.slice, (ast.Constant,ast.UnaryOp)):
        target, index = literal(node.value,names), literal(node.slice,names)
        if not isinstance(target,(list,tuple,str,array)) or type(index) is not int: raise UnsupportedCheck()
        value = target[index]
    elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='array' and len(node.args)==2 and not node.keywords:
        code, values = [literal(child,names) for child in node.args]
        if code not in ('b','B','h','H','i','I','l','L','q','Q','f','d') or not isinstance(values,(list,tuple)) or len(values)>256:
            raise UnsupportedCheck()
        value = array(code,values)
    else: raise UnsupportedCheck()
    if isinstance(value,(str,list,tuple,array)) and len(value)>1024: raise UnsupportedCheck()
    if type(value) in (int,float) and (abs(value)>1e12 or not math.isfinite(value)): raise UnsupportedCheck()
    return value


def executable_choice_check(question):
    from app.langchain.generation_recovery import GenerationMismatch
    blocks = re.findall(r'```python\s*\n(.*?)```',question.prompt,re.S)
    if len(blocks)!=1 or len(blocks[0])>5000 or question.answer_mode!='single_choice': return False
    try:
        tree=ast.parse(blocks[0])
        if sum(1 for _ in ast.walk(tree))>256: return False
        names={}; value=None; assigned=False; last_name=None
        for statement in tree.body:
            if isinstance(statement,ast.ImportFrom) and statement.module=='array' and statement.level==0 and len(statement.names)==1 and statement.names[0].name=='array' and not statement.names[0].asname:
                continue
            if not isinstance(statement,ast.Assign) or len(statement.targets)!=1 or not isinstance(statement.targets[0],ast.Name):
                return False
            value=literal(statement.value,names)
            names[statement.targets[0].id]=value; assigned=True
            last_name=statement.targets[0].id
        if not assigned: return False
        # Execution proves a value, not what a natural-language task asks for.
        # Admit this check only when public prose names that single result.
        prose=re.sub(r'```.*?```','',question.prompt,flags=re.S)
        references=set(re.findall(r'(?<!`)`([A-Za-z_][A-Za-z_0-9]*)`(?!`)',prose))
        if references!={last_name}: return False
        choices={}
        for option in question.options:
            label=option.label.strip().strip('`')
            choices[option.id]=literal(ast.parse(label,mode='eval').body,{})
        matches=[key for key,item in choices.items() if type(item) is type(value) and item==value]
        if len(matches)!=1: return False  # Unrecognized task/labels are not a proof.
        if matches[0]!=question.correct_option_id:
            raise GenerationMismatch('executable_choice_key_mismatch')
        return True
    except GenerationMismatch:
        raise
    except (UnsupportedCheck,SyntaxError,TypeError,ValueError,OverflowError,IndexError,ZeroDivisionError):
        return False


def check_question(question, *, planned_context=''):
    from app.langchain.generation_recovery import GenerationMismatch
    labels=[normalized(option.label) for option in question.options]
    if len(labels)!=len(set(labels)): raise GenerationMismatch('duplicate_option_labels')
    if len(question.options)>6: raise GenerationMismatch('too_many_choice_options')
    answer=normalized(question.model_answer)
    if len(answer)>=24 and any(answer in normalized(context) for context in (question.context,planned_context) if context):
        raise GenerationMismatch('answer_leaked_in_question_context')
    return dict(policy=POLICY,state='admitted',checks=['shape','unique_choices','context_leak',
        *(['executable_key'] if executable_choice_check(question) else [])],semantic_review='unverified')


def answerable(assessment):
    if any(question.get('validation',{}).get('state')=='invalidated' for question in assessment['questions']):
        from app.core.exceptions import AppError
        raise AppError('ASSESSMENT_REVIEW_REQUIRED','A question needs review. Your saved answers are preserved.',409)


def stored_question(question, identifier):
    return dict(question.model_dump(mode='json'), id=identifier, validation=check_question(question))


def public_validation(question):
    value=question.get('validation',{})
    return {key:value[key] for key in ('state','policy','checks','semantic_review') if key in value} or dict(state='legacy',semantic_review='unverified')
