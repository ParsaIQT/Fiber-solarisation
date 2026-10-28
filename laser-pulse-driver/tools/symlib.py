"""Load KiCad symbols (flattening 'extends') and report pins."""
import os, sys, copy
sys.path.insert(0, os.path.dirname(__file__))
from sexp import parse, find, first, Sym
SYMDIR = "/usr/share/kicad/symbols"
_cache = {}

def load_lib(lib):
    if lib not in _cache:
        txt = open(os.path.join(SYMDIR, lib + ".kicad_sym")).read()
        root = parse(txt)[0]
        d = {}
        for s in find(root, "symbol"):
            d[s[1]] = s
        _cache[lib] = d
    return _cache[lib]

def get_symbol(lib_id):
    lib, name = lib_id.split(":")
    d = load_lib(lib)
    s = copy.deepcopy(d[name])
    ext = first(s, "extends")
    if ext is not None:
        parent = get_symbol(lib + ":" + ext[1])
        # flatten: take parent's graphics/pins units (renamed), child's properties
        newsym = [Sym("symbol"), name]
        props = {p[1]: p for p in find(s, "property")}
        for e in parent[2:]:
            if isinstance(e, list) and e and e[0] == "property":
                newsym.append(props.pop(e[1], e))
            elif isinstance(e, list) and e and e[0] == "symbol":
                sub = copy.deepcopy(e)
                sub[1] = sub[1].replace(ext[1] + "_", name + "_", 1)
                newsym.append(sub)
            else:
                newsym.append(e)
        for p in props.values():
            newsym.append(p)
        s = newsym
    return s

def pins(lib_id):
    s = get_symbol(lib_id)
    out = []
    for sub in find(s, "symbol"):
        # name like NAME_<unit>_<style>
        parts = sub[1].rsplit("_", 2)
        unit = int(parts[-2]); style = int(parts[-1])
        for p in find(sub, "pin"):
            at = first(p, "at"); num = first(p, "number")[1]; nm = first(p, "name")[1]
            ln = first(p, "length")[1]
            out.append(dict(unit=unit, style=style, num=num, name=nm, x=float(at[1]), y=float(at[2]),
                            ang=float(at[3]) if len(at) > 3 else 0.0, etype=str(p[1]), len=float(ln)))
    return out

if __name__ == "__main__":
    for lid in sys.argv[1:]:
        print("==", lid)
        for p in pins(lid):
            print(f"  u{p['unit']} s{p['style']} {p['num']:>3} {p['name']:12s} ({p['x']:7.2f},{p['y']:7.2f}) ang={p['ang']:5.0f} {p['etype']}")
