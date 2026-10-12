"""Copy to local_settings.py (git-ignored) and edit for your machine.

Any value left out falls back to the default project layout described in config.py.
Environment variables GBEM_PROJECT_ROOT, GBEM_LIT_DIR, GBEM_REVIEW_DIR, GBEM_TEMPLATE_DIR and GBEM_ZOTERO_DIR override these.
"""
# PROJECT_ROOT = r"D:\path\to\project"                 # folder containing code/, Lit/, Manuscripts/
# LIT_DIR = r"D:\path\to\project\Lit"                  # database exports (Lit/Scopus, Lit/WoS) and PDF library
# REVIEW_DIR = r"D:\path\to\project\Manuscripts\01_Review"   # iterations/ are created here
# TEMPLATE_DIR = r"D:\path\to\project\Manuscripts\01_Review\pipeline\template"   # LaTeX manuscript template
# ZOTERO_DIR = r"D:\path\to\Zotero"                 # Zotero data folder (zotero.sqlite, storage/); used by collect_fulltexts.py
# ELSEVIER_API_KEY = "..."                            # optional: key from dev.elsevier.com for fetch_open_access.py (never commit a key)
# ELSEVIER_INSTTOKEN = "..."                          # optional: institutional token from the library, for use off campus
