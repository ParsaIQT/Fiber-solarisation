"""Minimal S-expression parser/printer for KiCad files."""
import re

class Sym(str):
    pass

_tok = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))', re.S)

def parse(text):
    stack = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _tok.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("parse error at %d: %r" % (pos, text[pos:pos+40]))
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            lst = stack.pop()
            stack[-1].append(lst)
        elif m.group(3) is not None:
            s = m.group(3)[1:-1]
            s = s.replace('\\"', '"').replace('\\\\', '\\')
            stack[-1].append(s)
        else:
            stack[-1].append(Sym(m.group(4)))
    return stack[0]

def q(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

def dump(x, indent=0):
    if isinstance(x, list):
        if not x:
            return "()"
        simple = all(not isinstance(e, list) for e in x)
        if simple:
            return "(" + " ".join(dump(e) for e in x) + ")"
        out = "(" + dump(x[0])
        for e in x[1:]:
            if isinstance(e, list):
                out += "\n" + "\t" * (indent + 1) + dump(e, indent + 1)
            else:
                out += " " + dump(e)
        out += "\n" + "\t" * indent + ")"
        return out
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        if isinstance(x, float):
            s = ("%.6f" % x).rstrip("0").rstrip(".")
            return s if s not in ("-0", "") else "0"
        return str(x)
    return q(x)

def find(lst, key):
    for e in lst:
        if isinstance(e, list) and e and e[0] == key:
            yield e

def first(lst, key):
    for e in find(lst, key):
        return e
    return None
