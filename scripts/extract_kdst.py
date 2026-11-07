"""data/kdst_pdf/*.pdf(한국어판)에서 문항을 뽑아 data/kdst/{월령}.json으로 저장한다.

저장되는 파일에는 문항 원문이 들어가므로 커밋되지 않는다(.gitignore).
PDF는 줄바꿈 때문에 단어가 끊겨 있어, 조사·어미로 끝난 줄만 띄어쓰기로 잇는다.
"추가 질문"은 예/아니오 문항이라 0~3점 문항에 넣지 않는다.
"""

import json
import re
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from moru.config import DATA_DIR, KDST_DIR  # noqa: E402
from moru.schemas import KdstItem  # noqa: E402

PDF_DIR = DATA_DIR / "kdst_pdf"
HEADINGS = {
    "대근육운동": "gross_motor",
    "소근육운동": "fine_motor",
    "인지": "cognition",
    "언어": "language",
    "사회성": "social",
    "자조": "self_care",
    "추가 질문": None,
}
COLUMN_X = 300  # 문항은 좌우 2단이다. 오른쪽 단의 번호는 x≈312에서 시작한다.
CIRCLE_X = 400  # 체크칸은 왼쪽 단 x≈225, 오른쪽 단 x≈499
WORD_END = "을를은는이가에의로고며면서게도와과나등때해아어록음,.)]?”’"
SKIP = re.compile(r"^(잘 할 수 있다|할 수 있는 편이다|하지 못하는 편이다|전혀 할 수 없다)\s*[③②①⓪]?$|^✣|^(통과|실패)$")


def join_lines(lines: list[str]) -> str:
    text = lines[0]
    for line in lines[1:]:
        text += (" " if text[-1] in WORD_END else "") + line
    return re.sub(r"\s+", " ", text).strip()


def page_lines(page: pymupdf.Page) -> list[dict]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                x0, y0, x1, y1 = line["bbox"]
                lines.append({"text": text, "x0": x0, "x1": x1, "y": (y0 + y1) / 2})
    return lines


def parse_items(pdf: Path) -> dict[str, list[str]]:
    """{영역: 문항 8개}를 돌려준다.

    일부 PDF는 텍스트 순서가 뒤섞여 있어 좌표로 복원한다. 체크칸(③②①) 한 줄이
    문항 한 행이고, 영역은 그 위에 있는 가장 가까운 영역 제목에서 가져온다.
    """
    found: dict[str, dict[int, str]] = {}
    domain = None
    for page in pymupdf.open(pdf):
        lines = page_lines(page)
        headings = sorted(
            (l for l in lines if l["text"] in HEADINGS and l["x0"] < COLUMN_X), key=lambda l: l["y"]
        )
        numbers = [l for l in lines if re.fullmatch(r"[1-8]", l["text"])]
        circles = [l for l in lines if re.match(r"③\s*②\s*①", l["text"])]

        rows = []
        for circle in circles:
            same = [n for n in numbers if (n["x0"] > COLUMN_X) == (circle["x0"] > CIRCLE_X)]
            number = min(same, key=lambda n: abs(n["y"] - circle["y"]), default=None)
            if number is not None and abs(number["y"] - circle["y"]) <= 30:
                rows.append({"y": circle["y"], "number": number, "circle": circle, "words": []})

        taken = {id(r["number"]) for r in rows} | {id(r["circle"]) for r in rows}
        for line in lines:
            if id(line) in taken or line["text"] in HEADINGS or SKIP.search(line["text"]):
                continue
            column = [
                r for r in rows
                if line["x0"] >= r["number"]["x1"] - 2 and line["x1"] <= r["circle"]["x0"] + 8
            ]
            if column:
                row = min(column, key=lambda r: abs(r["y"] - line["y"]))
                if abs(row["y"] - line["y"]) < 40:
                    row["words"].append(line)

        marks = [(h["y"], HEADINGS[h["text"]]) for h in headings]
        for row in sorted(rows, key=lambda r: r["y"]):
            above = [name for y, name in marks if y < row["y"]]
            row["domain"] = above[-1] if above else domain
        if marks:
            domain = marks[-1][1]

        for row in rows:
            if row["domain"] is None:  # 추가 질문
                continue
            words = sorted(row["words"], key=lambda l: l["y"])
            if not words:
                raise ValueError(f"{pdf.name} p{page.number + 1}: 본문 없음 {row['number']}")
            num = int(row["number"]["text"])
            found.setdefault(row["domain"], {})[num] = join_lines([w["text"] for w in words])

    return {
        name: fix_wraps([texts[n] for n in sorted(texts)]) for name, texts in found.items()
    }


ENDINGS = (".", ")", "]", "?", "”", "다")


def fix_wraps(texts: list[str]) -> list[str]:
    """세 줄짜리 문항의 첫 줄이 앞 문항에 붙는 경우를 고친다.

    앞 문항이 문장으로 끝나지 않으면, 마지막 문장 뒤에 남은 조각을 다음 문항 앞으로 옮긴다.
    예: "뒷걸음질할 수 있다. 난간을 붙잡고 ... 모은 뒤 한" + "발씩 한발씩 계단을 올라간다."
    """
    texts = list(texts)
    for i in range(len(texts) - 1):
        text = texts[i]
        if text.endswith(ENDINGS):
            continue
        cut = max(text.rfind(". "), text.rfind(".) "), text.rfind("] "))
        head, tail = (text[: cut + 1].rstrip(), text[cut + 1 :].strip()) if cut >= 0 else ("", text)
        if not head:
            continue
        texts[i] = head
        texts[i + 1] = join_lines([tail, texts[i + 1]])
    return texts


def main() -> None:
    KDST_DIR.mkdir(exist_ok=True)
    pdfs = sorted(PDF_DIR.glob("*.pdf"), key=lambda p: int(p.stem.split("-")[0]))
    for pdf in pdfs:
        band = pdf.stem
        domains = parse_items(pdf)
        wrong = {name: len(texts) for name, texts in domains.items() if len(texts) != 8}
        if wrong:
            raise ValueError(f"{band}: 영역별 8문항이 아닙니다 {wrong}")
        items = [
            KdstItem(item_id=f"{band}_{name}_{i:02d}", age_band=band, domain=name, text=text)
            for name, texts in domains.items()
            for i, text in enumerate(texts, 1)
        ]
        out = KDST_DIR / f"{band}.json"
        data = [item.model_dump() for item in items]
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{band}: {len(domains)}개 영역, {len(items)}문항")


if __name__ == "__main__":
    main()
