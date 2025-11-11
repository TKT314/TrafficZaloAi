# ===============================
# 🟩 GIAI ĐOẠN 0: INVENTORY & GẮN NHÃN
# ===============================
import os
from pathlib import Path

# Folder chứa file luật
INPUT_DIR = Path("luat_duong_bo")

# Gán nhãn cho các file luật/nghị định trong thư mục luat_duong_bo
source_map = {
    # Luật (QH15)
    "35-2024-qh15.pdf":        "luat35_2024_qh15",
    "36-2024-qh15.pdf":        "luat36_2024_qh15_p1",
    "36-2024-qh15_tiep.pdf":   "luat36_2024_qh15_p2",

    # Nghị định (CP / ND-CP / ND)
    "119-cp.signed.pdf":       "nghidinh119_cp",
    "130-cp.signed.pdf":       "nghidinh130_cp",
    "140nd.signed.pdf":        "nghidinh140_nd",
    "144-ndcp.signed.pdf":     "nghidinh144_ndcp",
    "168-nd-cp.signed.pdf":    "nghidinh168_ndcp",
    "170-nd.signed.pdf":       "nghidinh170_nd",
    "176-nd.signed.pdf":       "nghidinh176_nd",
    "184-nd.signed.pdf":       "nghidinh184_nd",
}

# Kiểm tra sự tồn tại file
for file, key in source_map.items():
    if not (INPUT_DIR / file).exists():
        print(f"⚠️ File {file} không tồn tại trong thư mục {INPUT_DIR}/")
    else:
        print(f"✅ {file} → SOURCE_KEY = {key}")

print("\n➡️ Tiếp tục sang GIAI ĐOẠN 1: PDF → TEXT")


# ===============================
# 🟦 GIAI ĐOẠN 1: PDF → TEXT (LOOP TOÀN BỘ FILE)
# ===============================
import pdfplumber
from tqdm import tqdm

Path("outputs").mkdir(exist_ok=True)

for fname, SOURCE_KEY in source_map.items():
    input_pdf_path = INPUT_DIR / fname
    if not input_pdf_path.exists():
        print(f"⚠️ Bỏ qua (không tìm thấy): {fname}")
        continue

    OUTPUT_TXT = Path("outputs") / f"raw_{SOURCE_KEY}.txt"
    text_all = []

    with pdfplumber.open(str(input_pdf_path)) as pdf:
        for page in tqdm(pdf.pages, desc=f"Đang xử lý {SOURCE_KEY}"):
            text = page.extract_text()
            if text:
                # Làm sạch header/footer
                lines = text.split("\n")
                cleaned = [l for l in lines if not l.strip().startswith(("Trang", "BỘ", "CỘNG HÒA"))]
                text_all.append("\n".join(cleaned))

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(text_all))

    print(f"✅ Đã tạo file TEXT: outputs/{OUTPUT_TXT.name}")


# ===============================
# 🟨 GIAI ĐOẠN 2: TÁCH THEO “ĐIỀU” & GÁN SUFFIX
# ===============================
import re, json
from collections import defaultdict

for SOURCE_KEY in source_map.values():
    INPUT_TXT = f"outputs/raw_{SOURCE_KEY}.txt"
    OUTPUT_JSON = f"outputs/structured_{SOURCE_KEY}.json"

    if not Path(INPUT_TXT).exists():
        print(f"⚠️ Bỏ qua vì chưa có file: {INPUT_TXT}")
        continue

    text = Path(INPUT_TXT).read_text(encoding="utf-8")

    pattern = r"(Điều\s+\d+[\w]*\..*?)(?=Điều\s+\d+[\w]*\.|$)"
    matches = re.findall(pattern, text, flags=re.DOTALL)

    laws = []
    count_per_article = defaultdict(int)

    for i, match in enumerate(matches, 1):
        lines = match.strip().split("\n", 1)
        title = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""

        m = re.search(r"Điều\s+(\d+[\w]*)\.", title)
        base_id = m.group(1).lower() if m else f"unknown_{i}"

        count_per_article[base_id] += 1
        suffix = count_per_article[base_id]
        final_id = f"dieu{base_id}_{suffix}_{SOURCE_KEY}"

        laws.append({
            "id": final_id,
            "title": title,
            "content": content,
            "source": SOURCE_KEY
        })

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(laws, f, ensure_ascii=False, indent=2)

    print(f"✅ Tách xong {len(laws)} điều → {OUTPUT_JSON}")


# ===============================
# 🟧 GIAI ĐOẠN 3: CHUNK & LÀM SẠCH
# ===============================
import nltk
from nltk.tokenize import sent_tokenize

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt")
    nltk.download("punkt_tab")

MAX_WORDS = 1000

def chunk_text(text, max_words=MAX_WORDS):
    sents = sent_tokenize(text)
    chunks, cur, cnt = [], [], 0
    for s in sents:
        w = len(s.split())
        if cnt + w > max_words and cur:
            chunks.append(" ".join(cur))
            cur, cnt = [s], w
        else:
            cur.append(s)
            cnt += w
    if cur:
        chunks.append(" ".join(cur))
    return chunks

for SOURCE_KEY in source_map.values():
    INPUT_JSON = f"outputs/structured_{SOURCE_KEY}.json"
    OUTPUT_JSONL = f"outputs/chunked_{SOURCE_KEY}.jsonl"

    if not Path(INPUT_JSON).exists():
        print(f"⚠️ Bỏ qua (chưa có file): {INPUT_JSON}")
        continue

    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))

    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
        for d in data:
            content = d.get("content", "") or ""
            if not content.strip():
                continue

            for i, c in enumerate(chunk_text(content), 1):
                record = {
                    "id": f"{d['id']}_chunk{i}",
                    "title": d["title"],
                    "content": c,
                    "source": d["source"]
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"✅ Chunk hoàn tất → {OUTPUT_JSONL}")


# ===============================
# 🟥 GIAI ĐOẠN 4: MERGE & DEDUP
# ===============================
import hashlib
from glob import glob

OUTPUT_FINAL = "outputs/knowledge_base.jsonl"
INPUT_FILES = glob("outputs/chunked_*.jsonl")

def content_hash(title, content):
    return hashlib.sha1((title.strip() + content.strip()).encode("utf-8")).hexdigest()

seen = set()
kept, skipped = 0, 0

with open(OUTPUT_FINAL, "w", encoding="utf-8") as fout:
    for file in INPUT_FILES:
        with open(file, "r", encoding="utf-8") as fin:
            for line in fin:
                obj = json.loads(line)
                h = content_hash(obj["title"], obj["content"])
                if h in seen:
                    skipped += 1
                    continue
                seen.add(h)
                fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                kept += 1

print(f"✅ Merge hoàn tất → {OUTPUT_FINAL}")
print(f"📊 Giữ lại: {kept} | Bỏ trùng: {skipped} | File đầu vào: {len(INPUT_FILES)}")
