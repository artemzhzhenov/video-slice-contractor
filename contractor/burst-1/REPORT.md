# Отчёт по рывку 1

Обновляй при каждом коммите. Статусы: `NOT STARTED` / `IN PROGRESS` / `DONE` / `BLOCKED`.
Дата в формате 2026-09-15. Часы — фактические.

## Сводка

| Поле | Значение |
|---|---|
| Текущая версия сдачи | — |
| Общий статус | IN PROGRESS |
| Часов потрачено | 2,2 |
| Blender | 5.2.1 LTS, build `9e2066aef7ef` (модуль `bpy==5.2.1` с PyPI, Python 3.13.13, Linux x86_64, Cycles CPU — Metal недоступен, см. журнал) |

## Пункты

| # | Пункт | Статус | Дата | Комментарий |
|---|---|---|---|---|
| 1 | Репозиторий установлен, шаблон собран, `check_scene.py` на шаблоне проходит | DONE | 2026-09-15 | коммит `b6a90fd`; `checks_failed: []`, scene_linear ACEScg, OCIO из репозитория |
| 2 | Персонаж (тело, одежда, руки) в `C_BODY` / `C_HAND_FG`, материалы по именам | IN PROGRESS | 2026-09-15 | база MPFB2 (Q9); базовый меш ребёнка генерируется headless, см. журнал |
| 3 | Дефолтная голова в `C_HEAD`, кольцо `SOCKET_BOUNDARY`, заканчивается на кольце | NOT STARTED | | |
| 4 | Волосы мешем в `C_HAIR` | NOT STARTED | | сплошные пряди, непрозрачный `HERO_HAIR` (Q4) |
| 5 | Риг `RIG_HERO` с обязательными костями, скиннинг, `SOCKET_HEAD` на `head` | NOT STARTED | | |
| 6 | Лицевая механика от свойств `FACE_CTRL` (26 каналов) | NOT STARTED | | |
| 7 | Прокси `NECK_PROXY`, `COLLISION_PROXY` подогнаны | NOT STARTED | | |
| 8 | Ray visibility головы/волос по TASK §6 | NOT STARTED | | |
| 9 | `check_asset.sh` проходит (хвост лога ниже) | NOT STARTED | | |
| 10 | `LICENSES.md` заполнен | DONE | 2026-09-15 | MPFB2 + своё; дополняется, если появятся новые сторонние элементы |

## Журнал

- 2026-09-15 — Q10: архив blender.org из среды недоступен (`download.blender.org` и зеркало —
  HTTP 403 от egress-прокси; открыты только github.com и pypi.org), остаюсь на обёртке над
  `bpy` того же build hash; финальный прогон `check_asset.sh` дословно — на стороне владельца.
  Пункт 10 → DONE. 0,2 ч.

- 2026-09-15 — Q9 → MPFB2. Add-on поставлен в среду как extension (`bl_ext.user_default.mpfb`,
  исходники GitHub `makehumancommunity/mpfb2` @ `437dd51`, манифест 2.0.17, min Blender 4.2).
  Проверено headless: `HumanService.create_human()` + макросы `gender=0`, `age`, `height`,
  `reapply_macro_details` → девочка; рост по `age`: 0.13 → 1.08 м, 0.1875 → 1.27 м (целевой
  диапазон 1.2–1.4 м достижим макросами age/height без референсов). Базовый меш 19 158 вершин
  с helper-геометрией (152 vertex groups — helpers удаляются перед сдачей); встроенный риг
  `default` ставится, имена костей не по контракту — `RIG_HERO` буду собирать переименованием
  и досборкой. Волосы MPFB — alpha-полосы (не по Q4); план: сплошная шапка из helper-hair +
  пряди. 1 ч.

- 2026-09-15 — прочитан контракт (TASK, ACCEPTANCE, conventions/channel_map, check_scene,
  export_shot, check_exports, roundtrip, REBUILD); заданы Q2–Q8, ответы получены, скрипты
  обновлены до `b6a90fd`. Среда: Blender 5.2.1 LTS как Python-модуль (`bpy` с PyPI, тот же
  build hash `9e2066aef7ef`), Linux x86_64, Cycles на CPU; скрипты `slice/*.py` запускаются
  через обёртку, эмулирующую `blender -b … -P … --` (`sys.argv` + `wm.open_mainfile`).
  Шаблон `template.blend` собран (`TEMPLATE_OK`), `check_scene.py` — 0 ошибок.
  Не получилось: `blender`-бинарь в среде отсутствует, поэтому `check_asset.sh` целиком
  запускаю не через bash-скрипт, а по шагам той же обёрткой; хвост лога буду вставлять из
  каждого шага. 1 ч.

## Последний прогон `check_asset.sh`

Команда, дата, последние строки вывода:

```
2026-09-15  step 1 check_scene  (template.blend, не ассет)
{ "blender": "5.2.1 LTS", "device": "CPU", "scene_linear": "ACEScg", "checks_failed": [] }
(остальные шаги на ассете ещё не запускались)
```

## Блокеры

- нет (канал записи в репозиторий — коммитит владелец, пока не решено иное)
