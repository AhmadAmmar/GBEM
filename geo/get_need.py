"""National Energy Efficiency Data-Framework (NEED), anonymised 2024 release (DESNZ, England and Wales; Open Government
Licence v3.0): property-level gas and electricity consumption 2005-2022 with property characteristics and installed
energy-efficiency measures, as a 4 million property sample (and a 50,000 sample) with metadata.

    python get_need.py

Raw files are kept unchanged in data/national/need_2024/raw/ (SOURCE.txt, SHA256SUMS.txt); an existing download is
never replaced. analysis/need_check.py uses them.
"""
import datetime, hashlib, pathlib, urllib.request

PHD = pathlib.Path(__file__).resolve().parents[2]
RAW = PHD / "data/national/need_2024/raw"
FILES = {"anonymised-NEED-data-2024-4million.zip": "https://assets.publishing.service.gov.uk/media/669fa8cace1fd0da7b592b01/anonymised-NEED-data-2024-4million.zip",
         "anonymised-NEED-data-2024-50k.csv": "https://assets.publishing.service.gov.uk/media/669fa8880808eaf43b50d4f8/anonymised-NEED-data-2024-50k.csv",
         "NEED-2024-anonymised-dataset-metadata.ods": "https://assets.publishing.service.gov.uk/media/669fa92949b9c0597fdb0296/NEED-2024-anonymised-dataset-metadata.ods"}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dest = RAW / name
        if dest.exists():
            print("already downloaded:", name); continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(url, timeout=1800) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 22)
                if not b:
                    break
                f.write(b)
        tmp.rename(dest)
        print("downloaded:", name, round(dest.stat().st_size / 1e6, 1), "MB")
    (RAW / "SOURCE.txt").write_text(
        "Department for Energy Security and Net Zero, National Energy Efficiency Data-Framework (NEED): anonymised data "
        "2024. Contains public sector information licensed under the Open Government Licence v3.0.\n"
        + "".join(f"{n}: {u}\n" for n, u in FILES.items()) + f"Downloaded {datetime.date.today()}\n", encoding="utf-8")
    sums = []
    for name in FILES:
        h = hashlib.sha256()
        with open(RAW / name, "rb") as f:
            for b in iter(lambda: f.read(1 << 22), b""):
                h.update(b)
        sums.append(f"{h.hexdigest()}  {name}\n")
    (RAW / "SHA256SUMS.txt").write_text("".join(sums), encoding="utf-8")


if __name__ == "__main__":
    main()
