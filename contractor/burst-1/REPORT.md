# Отчёт по рывку 1

Обновляй при каждом коммите. Статусы: `NOT STARTED` / `IN PROGRESS` / `DONE` / `BLOCKED`.
Дата в формате 2026-09-15. Часы — фактические.

## Сводка

| Поле | Значение |
|---|---|
| Текущая версия сдачи | **v01** — `deliverables/character_v01.blend` |
| Общий статус | DONE (ждёт приёмки владельца: дословный `check_asset.sh` на M4 + пересборка по п. 5) |
| Часов потрачено | 6,2 (нарастающим итогом) |
| Blender | 5.2.1 LTS, build `9e2066aef7ef` (модуль `bpy==5.2.1` с PyPI, Python 3.13.13, Linux x86_64, Cycles CPU) |
| Шаблон | `scene_template.py` @ `5c24679`, `--shot SHOT_001` |
| Хэш содержимого v01 | `499694b91e1c17523c1f6ae74e88c59bf7997206c8397833f2e9ba55eee1bb7e` (`blend_content_hash.py`; две независимые сборки из двух шаблонов дают один хэш) |

## Пересборка одной командой (ACCEPTANCE п. 5)

Шаг 0 — MPFB2 `v2.0.17` (коммит `80919fa`) как extension:

    git clone --branch v2.0.17 https://github.com/makehumancommunity/mpfb2.git && cd mpfb2/src && zip -r mpfb.zip mpfb
    blender -b --command extension install-file mpfb.zip --repo user_default --enable

Скрипт ищет модуль под любым репозиторием (`bl_ext.user_default.mpfb` из исходников, `bl_ext.blender_org.mpfb` из Blender Extensions) и останавливается, если версия в `blender_manifest.toml` не 2.0.17.

Сборка:

    blender -b --python-exit-code 2 -P slice/scene_template.py -- --out template.blend --shot SHOT_001
    blender -b template.blend --python-exit-code 2 -P contractor/burst-1/deliverables/scripts/build_character.py -- --out character_v01.blend

Ожидаемый хвост: `ring: 42 vertices, centre [-0.0, -0.0245, 1.1973] …` и
`BUILD_OK … height=1.4 ring=42 ring_z=1.1973 body_verts=7633 head_verts=4200 hair_verts=2202 bones=102 blender=5.2.1 LTS`.
Случайности в сборке нет; всё, что имело недетерминированный порядок (bmesh solidify), заменено явной генерацией — см. журнал.

## Пункты

| # | Пункт | Статус | Дата | Комментарий |
|---|---|---|---|---|
| 1 | Репозиторий установлен, шаблон собран, `check_scene.py` на шаблоне проходит | DONE | 2026-09-15 | коммит `5c24679` |
| 2 | Персонаж (тело, одежда, руки) в `C_BODY` / `C_HAND_FG`, материалы по именам | DONE | 2026-09-16 | `HERO_BODY` (MakeHuman base mesh, девочка, рост 1,40 м, 7633 вершин, один модификатор Armature); одежда — регионы материала `HERO_CLOTH_01` (воротник над ключицей, рукава до локтя, леггинсы), обувь `HERO_SHOES`; шея, предплечья, кисти — `HERO_SKIN_BODY`; `HERO_HAND_FG` — левая кисть, отделённая по запястью с теми же весами (шов сварен) |
| 3 | Дефолтная голова в `C_HEAD`, кольцо `SOCKET_BOUNDARY`, заканчивается на кольце | DONE | 2026-09-16 | `HERO_HEAD` — оболочка (`HERO_SKIN_HEAD` + полоса бровей `HERO_BROW`), кольцо = существующий edge-loop шеи, 42 вершины, веса `(i+1)/N` по углу, `rest_gap max 0.0 / mean 0.0`; отдельные `HERO_EYE_L/R`, `HERO_TEETH_UPPER/LOWER`, `HERO_TONGUE`; envelope в socket-space x ±0,103, y −0,016…0,238, z −0,109…0,120 м |
| 4 | Волосы мешем в `C_HAIR` | DONE | 2026-09-16 | `HERO_HAIR` — сплошное каре (два эллипсоидных слоя, толщина 2,5 см, обрез по линии волос/затылку, рёбра закрыты), непрозрачный `HERO_HAIR`, без alpha |
| 5 | Риг `RIG_HERO` с обязательными костями, скиннинг, `SOCKET_HEAD` на `head` | DONE | 2026-09-16 | скелет MakeHuman default, 102 кости (лицевые удалены, их веса → `head`); `spine_01..05`, `neck`, `head` (основание = центр кольца), `shoulder_l/r`; кольцо тела 100 % на `head`; `SOCKET_HEAD` и `FACE_CTRL` перепривязаны, не пересозданы; экспортируемая цепочка строго осевая (см. Q14) |
| 6 | Лицевая механика от свойств `FACE_CTRL` (26 каналов) | DONE | 2026-09-16 | шейпкеи из expression-таргетов MakeHuman (набор `caucasian`), двусторонние каналы разделены маской по X, `jaw_lateral` процедурный, `gaze_yaw/pitch` — драйверы поворота глаз; драйверы `max(±v,0)`; soft-лимиты шаблона не тронуты; нижние зубы и язык следуют за `jaw_open`; тест — `previews/face_channels_test.png` |
| 7 | Прокси `NECK_PROXY`, `COLLISION_PROXY` подогнаны | DONE | 2026-09-16 | цилиндр по шее (ключица→кольцо, r = 1,08·r кольца) → `neck`; бокс плеч/груди → `spine_03`; `hide_render` |
| 8 | Ray visibility головы/волос по TASK §6 | DONE | 2026-09-16 | все 7 объектов `C_HEAD` ∪ `C_HAIR` |
| 9 | `check_asset.sh` проходит (хвост лога ниже) | DONE* | 2026-09-16 | *по шагам той же обёрткой (`blender`-бинаря в среде нет), все 8 шагов PASS; дословный прогон — владелец |
| 10 | `LICENSES.md` заполнен | DONE | 2026-09-15 | тег `v2.0.17` |

## Журнал

- 2026-09-15 — контракт прочитан, Q2–Q13, среда (см. выше). 2,2 ч.
- 2026-09-16 — `build_character.py`, сборка v01 и все проверки. Что оказалось нетривиальным:
  - **ring через bisect отброшен** в пользу существующего edge-loop (обход по топологии от
    вершины на середине шеи, валентность 4) — бисекция интерполирует шейпкеи и портит
    порядок; loop даёт побитовое совпадение колец.
  - **Масштаб костей в float32:** наклонные кости MakeHuman декомпозируются с ошибкой
    ~1,3e-6, `export_shot.py` требует 1e-6 → экспортируемая цепочка сделана строго
    осевой (`root`, `spine_*`, `neck`, `head` — вертикально на оси кольца; плечи — по X). Q14.
  - **bmesh solidify недетерминирован** (порядок по хэшу указателей): у двух сборок
    расходились координаты волос до 12 см. Волосы генерируются явно (u×v сетка, два слоя,
    рёбра по boundary-edge'ам) — хэши совпали.
  - Камера шаблона держит анимацию: мои превью первое время рендерились с её позиции;
    `preview_render.py` снимает анимацию во временной сцене.
  - Шаг 5 (Cycles CPU, 64 spp, 25 %): video 99 с, still 129 с. Шаги 6–8 потребовали
    `OpenImageIO` — в pip-`bpy` его нет, поставлен `OpenImageIO 3.1.17` с PyPI.
  4,0 ч.

Известные косметические ограничения (не по контракту, на решение владельца): брови —
блочная полоса граней оболочки (разрешение базового меша); волосы — гладкий «шлем»-каре без
прядей; одежда — материал по регионам, без отдельной геометрии; глаза — зрачок из граней
сферы; текстур нет, всё процедурные Principled.

## Последний прогон `check_asset.sh`

Команда и дата: 2026-09-16, пошагово через `bpy_module_runner.py` (эмулирует
`blender -b <file> -P <script> -- …`), `character_v01.blend`, 64 spp / 25 %.

```
=== 1 check_scene       {"blender": "5.2.1 LTS", "device": "CPU", "scene_linear": "ACEScg", "checks_failed": []}
=== 2 export SHOT_001   EXPORT_OK SHOT_001 120 frames
=== 3 check_exports     "checks_failed": []
=== 4 check_alembic     "checks_failed": []
=== 5 render video      RENDER_OK video 1 frames   (99 s CPU)
=== 5 render still      RENDER_OK still 1 frames   (129 s CPU)
=== 6 split video       SPLIT_OK {"HEAD_RENDER_BUNDLE": {"frames": 1}, "COMPOSITE_BUNDLE": {"frames": 1}}
=== 7 composite video   COMPOSITE_FRAME 1001 PASS outside_band_within_1e-3=1.0000 inside_band_within_5e-2=0.969 band=0.0044
=== 8 round-trip video  ROUNDTRIP_FRAME 1001 PASS p95=0.25px centroid=0.002px iou=0.9992 band_mean_abs=0.0201 | ctrl translation=fails scale=fails rotation=fails
                        ROUNDTRIP_OK video rotation_control=VALIDATED positive_control=NOT_DISCRIMINATING
=== 6 split still       SPLIT_OK
=== 7 composite still   COMPOSITE_FRAME 1050 PASS outside_band_within_1e-3=1.0000 inside_band_within_5e-2=0.966 band=0.0038
=== 8 round-trip still  ROUNDTRIP_FRAME 1050 PASS p95=0.25px centroid=0.004px iou=0.9989 band_mean_abs=0.0201 deformed=True
                        ROUNDTRIP_OK still rotation_control=VALIDATED
```

Заметка: rotation_control на настоящей голове **VALIDATED** (на манекене-сфере он не
валидировался — см. conventions.roundtrip.negative_control.rotation).

## Блокеры

- нет. Открыты Q14 (допуск масштаба костей) и Q15 (высота кольца vs камера) — на v01 не влияют.
