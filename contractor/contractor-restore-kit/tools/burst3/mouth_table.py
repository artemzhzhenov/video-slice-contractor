import json, glob, os
rows = []
for f in sorted(glob.glob("/home/claude/shots/teethfix/mouth_??_SHOT_00?.json")):
    n, s = os.path.basename(f)[6:8], os.path.basename(f)[9:17]
    d = json.load(open(f)); R = d["rows"]
    o = sum(sum(r["outside"].values()) for r in R); h = sum(sum(r.get("hidden_by_sack", {}).values()) for r in R)
    x = sum(r.get("sack_skin_crossings", 0) for r in R); fo = sum(1 for r in R if sum(r["outside"].values()) + sum(r.get("hidden_by_sack", {}).values()) + r.get("sack_skin_crossings", 0))
    pk = max(sum(r["outside"].values()) for r in R)
    rows.append((n, s, "MOUTH_OK" if fo == 0 else "MOUTH_FAIL", fo, o, pk, h, x))
print("| Ребёнок | Шот | Итог | Кадров с провалом | «Вне губ», сэмплов (макс. на кадр) | Скрыто мешком | Мешок × кожа |")
print("| --- | --- | --- | --- | --- | --- | --- |")
for r in rows: print(f"| {r[0]} | {r[1]} | `{r[2]}` | {r[3]} | {r[4]} ({r[5]}) | {r[6]} | {r[7]} |")
