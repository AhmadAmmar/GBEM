"""BibTeX entries from DOIs, verified on Crossref: a reference is written only if its DOI resolves.

    python doi_bib.py <out.bib> key=doi [key=doi ...]
    e.g. python doi_bib.py refs.bib roberts2017=10.1111/ecog.02881 meyer2021=10.1111/2041-210X.13650

Each DOI is looked up in the Crossref API (title, journal and year are printed for checking) and the BibTeX record is
taken from doi.org by content negotiation. The entry key is replaced by the given key; dashes are kept as -- / ---;
month fields are removed (month names break several BibTeX styles); the text is converted to ASCII (BibTeX 0.99 is
not UTF-8 safe). Unresolved DOIs are reported and left out. An existing output file is archived (safeio.keep).
"""
import json, pathlib, re, sys, unicodedata, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

HDR = {"User-Agent": "research-bibliography/1.0"}


def entry(key, doi):
    m = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://api.crossref.org/works/{doi}", headers=HDR), timeout=60).read())["message"]
    bib = urllib.request.urlopen(urllib.request.Request(f"https://doi.org/{doi}", headers={**HDR, "Accept": "application/x-bibtex"}), timeout=60).read().decode("utf-8")
    bib = re.sub(r"@(\w+)\{[^,]+,", lambda x: f"@{x.group(1)}{{{key},", bib, count=1)
    bib = bib.replace("–", "--").replace("—", "---").replace("‐", "-").replace("‑", "-")
    bib = re.sub(r",\s*month\s*=\s*\{?\w+\}?", "", bib)
    bib = unicodedata.normalize("NFKD", bib).encode("ascii", "ignore").decode()
    print("OK", key, "|", m.get("title", [""])[0][:90], "|", (m.get("container-title") or [""])[0], m.get("issued", {}).get("date-parts", [[None]])[0][0])
    return bib.strip()


def main():
    out, pairs = pathlib.Path(sys.argv[1]), [a.split("=", 1) for a in sys.argv[2:]]
    entries = []
    for key, doi in pairs:
        try:
            entries.append(entry(key, doi))
        except Exception as e:
            print("NOT FOUND", key, doi, e)
    keep(out).write_text("\n\n".join(entries) + "\n", encoding="ascii")
    print(f"{len(entries)} of {len(pairs)} references -> {out}")


if __name__ == "__main__":
    main()
