# Отчёт по рывку 1

Обновляй при каждом коммите. Статусы: `NOT STARTED` / `IN PROGRESS` / `DONE` / `BLOCKED`.
Дата в формате 2026-09-15. Часы — фактические.

## Сводка

| Поле | Значение |
|---|---|
| Текущая версия сдачи | **v03** — `deliverables/character_v03.blend` (v02 принята технически 2026-09-17; v03 = Д1 + Д2) |
| Общий статус | DONE (ждёт приёмки v03: `check_asset.sh` со шагом 1b, пересборка по п. 5, п. 2 глазами) |
| Часов потрачено | 22,1 нарастающим итогом (v01 6,2 · v02 13,0 · v03 **2,9** — в утверждённых ~3 ч) |
| Blender | 5.2.1 LTS, build `9e2066aef7ef` (модуль `bpy==5.2.1`, Python 3.13.13, Linux x86_64, 1 ядро, Cycles CPU; `OpenImageIO 3.1.17` с PyPI для шагов 6–8) |
| Шаблон | `scene_template.py` @ `da77bac` (не менялся с `27d06be`), `--shot SHOT_001` |
| Хэш содержимого v03 | `d2084c91c4a2341050fe5896fef6c3609a63e4f088596aa571914414ee29dc71` (`blend_content_hash.py`; две независимые сборки из двух шаблонов совпали) |
| MPFB2 | `v2.0.17` = `80919fa`, модуль `bl_ext.<repo>.mpfb` (см. шаг 0) |

## Пересборка одной командой (ACCEPTANCE п. 5)

Шаг 0 — MPFB2 как extension (один раз):

    git clone --branch v2.0.17 https://github.com/makehumancommunity/mpfb2.git && cd mpfb2/src && zip -r mpfb.zip mpfb
    blender -b --command extension install-file mpfb.zip --repo user_default --enable

Сборка:

    blender -b --python-exit-code 2 -P slice/scene_template.py -- --out template.blend --shot SHOT_001
    blender -b template.blend --python-exit-code 2 -P contractor/burst-1/deliverables/scripts/build_character.py -- --out character_v03.blend

Ожидаемый хвост: `BUILD_OK … height=1.4 ring=42 ring_z=1.1973 body_verts=5701 head_verts=4200 hair_verts=6928 bones=102 blender=5.2.1 LTS`.
Флаг `--keep-env` оставляет пол и стену шаблона (Q16) — **по умолчанию выключен** до рывка 2 (решение по Q23).
Ручной геометрии нет: всё строит скрипт. Случайности нет.

## Пункты

| # | Пункт | Статус | Дата | Комментарий |
|---|---|---|---|---|
| 1 | Репозиторий установлен, шаблон собран, `check_scene.py` проходит | DONE | 2026-09-15 | |
| 2 | Персонаж (тело, одежда, руки) в `C_BODY` / `C_HAND_FG` | DONE (v02) | 2026-09-17 | **Одежда отдельной геометрией:** `HERO_DRESS` — параметрическая труба по сечениям тела (48×30, воротник над ключицей → подол над коленом, расклешение ниже талии, «юбка не сужается вниз»), `HERO_SLEEVE_L/R` — трубы вдоль плечевой кости до локтя, закрытые со стороны плеча; веса от ближайшей вершины тела (numpy, детерминированно), один Armature, `HERO_CLOTH_01`. **Тело под одеждой удалено** (2188 граней из 7600, запас 3 см под воротником, подолом и манжетами; шар плеча оставлен под платьем). Открыты: шея, предплечья, кисти, ноги ниже подола. Превью поворота на 60°: дыр нет. **v03 / Д1:** горловина смыкается на шее — кокетка из 6 колец от верха платья к линии выреза (спереди +2,0 см над прежним краем, по бокам +3,0, сзади +4,2), линия выреза замеряется ray-cast'ом от оси шеи по коже и **заходит внутрь шеи на 5 мм спереди → 9 мм сзади** (вариант В; 2,5 мм не хватило: на повороте кожа затылка уходит от воротника на 4 мм). Радиус сглажен 1-2-1 и зажат снизу (кожа − заход) — самопересечения и складок нет. Веса всей одежды, включая горловину, только от торса: `head`/`neck` исключены, сборка падает, если они появятся. Стойки и подкладки нет. Замер `collar_penetration.log`: нейтраль 4,4–8,4 мм внутри кожи, макс. поворот 1,1–13,4 мм — снаружи 0 вершин |
| 3 | Дефолтная голова в `C_HEAD`, кольцо `SOCKET_BOUNDARY` | DONE (v02) | 2026-09-17 | как в v01 + **веко Q19/Q21** и **зрачок геометрией** (сфера с полюсом на оси взгляда, зрачок 10° и радужка 25° — точные кольца вершин). `HERO_BROWS` — отдельный меш: параметрическая дуга над каждым глазом, спроецированная на кожу, сужается к внешнему концу, шейпкеи `brow_*` от ближайшей вершины оболочки; рендерится, без кольца |
| 4 | Волосы мешем в `C_HAIR` | DONE (v02) | 2026-09-17 | каре прядями: шлем-подложка (два эллипсоидных слоя, 1,8 см) + 61 прядь явной генерацией (44 бок/затылок до линии челюсти/затылка, 14 чёлки, 3 на левом виске); пряди идут по поверхности до широты 105°, дальше строго вниз. **Жёстко** на `SOCKET_HEAD`, без шейпкеев и драйверов; экспорт `default_head_deformed`: волосы в допуске. **Глаза, брови и рот открыты на фронте, ¾ и профиле** (`previews/head|three_quarter|side.png`); прядь на виске кончается у наружного угла глаза и **не двигается на повороте** (Q22) |
| 5 | Риг `RIG_HERO`, скиннинг, `SOCKET_HEAD` на `head` | DONE (v02) | 2026-09-17 | **веса шеи (Q17):** четыре ряда рёбер под кольцом с `head` 0,78 → 0,52 → 0,28 → 0,10 (обход топологии от шовного loop'а), кольцо ровно 100 % `head`. Превью 60° (`neck` 25° + `head` 35° + кивок 8°), ¾ и сбоку: без защипа, шов сварен. Preserve Volume **не понадобился**, выключен |
| 6 | Лицевая механика `FACE_CTRL` (26 каналов) | DONE (v02) | 2026-09-17 | **веко:** `lid_aperture −1` = полное смыкание — скрипт измеряет зазор между краем верхнего века и статичным нижним по колонке зрачка и масштабирует юнит MakeHuman (×1,402 на этой голове), закрытое веко проецируется на сферу глаза; in-between на −0,5 (те же вершины, вытолкнутые из сферы). Драйверы по `combination_rules`: `c = max(max(0,−lid), blink)`, full = `max(0,2c−1)`, mid = `1−|2c−1|`, widen = `max(0,lid)·(1−blink)`. Серия `previews/lid_*.png`: −1 сомкнуто, −0,5 полуприкрыто без среза склеры, +1 расширено, −1+blink и +1+blink сомкнуты |
| 7 | Прокси `NECK_PROXY`, `COLLISION_PROXY` | DONE | 2026-09-16 | без изменений |
| 8 | Ray visibility головы/волос | DONE | 2026-09-16 | все объекты `C_HEAD` ∪ `C_HAIR` (7 + брови) |
| 9 | `check_asset.sh` проходит | DONE* | 2026-09-18 | *пошагово той же обёрткой (`blender`-бинаря нет), **все 9 шагов включая 1b, на 64 spp / 25 %** — хвост ниже |
| 10 | `LICENSES.md` | DONE | 2026-09-18 | Д2: строка «своё» под фактическое содержимое v03 |

## Журнал

- 2026-09-15 … 2026-09-16 — v01, см. историю. 6,2 ч.
- 2026-09-17 — v02 по списку Q22, 13,0 ч. Что оказалось нетривиальным:
  - **Веко:** юнит закрытия MakeHuman на увеличенных стилизацией глазах оставлял щель; первая попытка
    измерять зазор только по движущимся вершинам дала «зазора нет» (нижнее веко в юните не двигается) —
    зазор считается против статичного нижнего края.
  - **Одежда:** «платье как смещённые грани тела» отброшено (лохматый край, две трубы ног вместо юбки);
    параметрическая труба по сечениям + монотонная юбка. Плечи: три итерации, чтобы рукав начинался
    внутри платья и не было видно внутрь трубы (закрыт торец, старт за 6 см до сустава).
  - **Волосы:** пряди по меридиану эллипсоида не достигали линии челюсти (дно эллипсоида выше неё) и
    оборачивались вокруг головы через лицо; исправлено уходом с поверхности вниз после 105°.
  - **Брови:** три версии по полосе вершин оболочки давали разрыв дуги (z-окно ловило складку века и
    гребень); итог — параметрическая дуга, спроецированная на кожу.
  - **Q23 (окружение):** см. ниже; окружение также делает рендер в 4–5 раз дольше (215 с vs 46 с на стилл).
  - Среда: 1 ядро CPU, лимит 300 с на команду, фон убивается — шаг 5 без окружения укладывается
    (video 3 кадра 246 с, still 119 с), с окружением — нет.

- 2026-09-18 — v03 (Д1, Д2), 2,9 ч. Первый вариант (кокетка + стойка) закрыл гейт, но стойка
  просвечивала сама через себя — остановился и показал; владелец выбрал В. Причина складок
  подтвердилась: кольца кокетки строились вне `polar_tube`, без сглаживания и без клэмпа. Второй
  дефект нашёл сам: веса горловины брались от вершин шеи (`head`/`neck`) — воротник частично шёл за
  головой; исправлено и защищено проверкой в сборке. Замер захода в обеих позах — числом, не
  глазом (`collar_penetration_measure.py`, nearest-surface по BVH). Задние ракурсы гейта смотрел.

## Q23 — окружение роняет `composite.py` (ЗАКРЫТ 2026-09-17: дело в 24 сэмплах, на 64 — PASS)

С `PLACEHOLDER_ENV_*` (Q16) гейт precomp reproduction падает: `inside_band_within_5e-2` 0,879 на стилле,
0,890 на видео; без окружения 0,969; v01 (контроль, те же 24 spp) 0,966; пряди ни при чём (0,883 без
них). Round-trip с окружением **проходит** (p95 0,25 px, iou 0,9995). Полоса включает стык стены и пола
на всю ширину кадра — там `FRONT over (HEAD over BACK)` расходится с beauty > 0,05. Это формула D5 при
наличии окружения, не персонаж. Мой вывод был неверным — гейт не сходится ниже 64 spp; на 64 с окружением 0,931 PASS (замер владельца). `--keep-env` остаётся выключенным до рывка 2 по решению владельца. Лог экспериментов —
`deliverables/logs/q23_env_experiments.log`. Побочно: round-trip требует масштаба с целыми пикселями
(16 % падает: `holdout is 614x345`), 20 % и 25 % работают.

Косметические ограничения (на решение владельца): текстур нет (процедурные Principled); пряди —
гладкие трубки одного цвета; платье без складок и рисунка.

## Последний прогон `check_asset.sh`

2026-09-18, пошагово через `bpy_module_runner.py`, `character_v03.blend`, `SHOT_001`, 64 spp / 25 %,
кадры `pick_frames` = 1001,1090,1102 + стилл 1050 (шаг 5: video 284 с, still 138 с на одном ядре):

```
=== 1 check_scene
  "checks_failed": []
}
=== 1b check_silhouette
SILHOUETTE_OK 14 views, no enclosed background region ≥ 50 px within 0.15 m of SOCKET_HEAD -> <out>
=== 2 export
EXPORT_OK SHOT_001 120 frames -> <out>/exports
=== 3 check_exports
 "checks_failed": []
}
=== 4 check_alembic
 "checks_failed": []
}
=== pick_frames: 1001,1090,1102
== split_bundles video rc=0
SPLIT_OK {"HEAD_RENDER_BUNDLE": {"frames": 3, "bytes_per_frame_mean": 6714.0}, "COMPOSITE_BUNDLE": {"frames": 3, "bytes_per_frame_mean": 1929011.3333333333}}
== composite video rc=0
COMPOSITE_FRAME 1001 PASS outside_band_within_1e-3=1.0000 inside_band_within_5e-2=0.970 band=0.0047 max_err=0.8107
COMPOSITE_FRAME 1090 PASS outside_band_within_1e-3=1.0000 inside_band_within_5e-2=0.970 band=0.0050 max_err=0.8624
COMPOSITE_FRAME 1102 PASS outside_band_within_1e-3=1.0000 inside_band_within_5e-2=0.976 band=0.0050 max_err=0.797
COMPOSITE_OK 3 frames -> <out>/renders/video/COMPOSITE_BUNDLE
== roundtrip video rc=0
ROUNDTRIP_FRAME 1001 PASS p95=0.25px centroid=0.028px iou=0.9987 band_mean_abs=0.0219 excluded=0.0004 rest_head=passes | ctrl translation=fails scale=fails rotation=fails
ROUNDTRIP_FRAME 1090 PASS p95=0.25px centroid=0.010px iou=0.9991 band_mean_abs=0.0196 excluded=0.0008 rest_head=passes | ctrl translation=fails scale=fails rotation=fails
ROUNDTRIP_FRAME 1102 PASS p95=0.25px centroid=0.004px iou=0.9994 band_mean_abs=0.0196 excluded=0.0006 rest_head=fails | ctrl translation=fails scale=fails rotation=fails
ROUNDTRIP_OK video 3 frames rotation_control=VALIDATED positive_control=NOT_DISCRIMINATING on every frame — the sub-frame data is exercised but not tested (no frame moves across the shutter) -> /tmp
== split_bundles still rc=0
SPLIT_OK {"HEAD_RENDER_BUNDLE": {"frames": 1, "bytes_per_frame_mean": 8609.0}, "COMPOSITE_BUNDLE": {"frames": 1, "bytes_per_frame_mean": 4078914.0}}
== composite still rc=0
COMPOSITE_FRAME 1050 PASS outside_band_within_1e-3=1.0000 inside_band_within_5e-2=0.967 band=0.0041 max_err=0.9394
COMPOSITE_OK 1 frames -> <out>/renders/still/COMPOSITE_BUNDLE
== roundtrip still rc=0
ROUNDTRIP_FRAME 1050 PASS p95=0.25px centroid=0.006px iou=0.9991 band_mean_abs=0.0200 excluded=0.0038 rest_head=passes | ctrl translation=fails scale=fails rotation=fails
ROUNDTRIP_OK still 1 frames rotation_control=VALIDATED positive_control=n/a (still) -> <out>/renders/still/roundtrip_report.still.json
```

## Блокеры

- нет.
