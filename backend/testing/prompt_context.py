"""Extract server-owned JSON data alongside personality/protocol instructions."""
import json

def context_data(text):
    decoder=json.JSONDecoder()
    for index,char in enumerate(text):
        if char!='{':continue
        try:value,_=decoder.raw_decode(text[index:])
        except ValueError:continue
        if isinstance(value,dict):return value
    raise ValueError('No structured context found in the server prompt')
