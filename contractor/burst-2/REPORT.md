# Рывок 2 — сдача SHOT_001 v01 (2026-09-21)

| Поле | Значение |
|---|---|
| Файл шота | `deliverables/shots/SHOT_001_v01.blend`, sha256 `7b2153198c9d5fb0a284212234c6bd27a9afd9ba7cefe916cf175ac4df2cb376` |
| Персонаж | не тронут: 15 из 15 меш-данных и 11 из 11 материалов побитово совпадают с принятой v03 (`logs/hash.json`) |
| T | **140 °/с** (указание владельца 21.09): MEDIUM ≤ 112, `fast_movement` ≥ 210 — в `deliverables/state_map.json` (копия `slice/state_map.json` + поле `head_angular_velocity_threshold_deg_s`) |
| Пики SHOT_001 | смех 99,5 °/с, удивление 36,2 °/с |
| Часы | ~11,5 из кап 30 |

## Сборка одной командой

    blender -b character_v03.blend --python-exit-code 2 -P make_shot_001.py -- --out SHOT_001_v01.blend
    blender -b SHOT_001_v01.blend  --python-exit-code 2 -P animate_shot_001.py -- --out SHOT_001_v01.blend

## Что сделано по указаниям 21.09

1. **Мячик целиком в кадре.** `PROP_A` (радиус 2,8 см, на тонком штырьке) стоит у правого края кадра на
   всех 120 кадрах (x 0,77–0,96, y 0,11–0,36 доли кадра), с силуэтом головы не пересекается ни на одном
   кадре, взгляд попадает в него с промахом 0,2° (замер: ось глаза против направления на мячик, кадр 1024).
   Штырёк уходит за нижний край — в кадре только мячик.
2. **Полный ролик одним прогоном из сдаваемого файла.** `playblasts/SHOT_001_v01_full.mp4`: 120 кадров за
   один запуск (182 с), sha256 файла до и после рендера одинаковый — `playblasts/SOURCE.txt`. Впредь так же.
3. **T = 140.**
4. **Прыжок тазом в шотах с ногами** — принято для SHOT_002/003. В SHOT_001 ноги не в кадре, отскок корнем
   оставлен. План для ног в кадре: IK-ограничения в риг не добавляю (персонаж заморожен) — таз подпрыгивает,
   а бедро и голень получают ключи из аналитического решения двухзвенной цепи на каждый кадр, так что стопы
   стоят на полу. Ключи остаются FK, детерминированными.

## Быстрая самопроверка на сдаваемом файле (`logs/quick.log`)

```
check_scene        checks_failed: []
check_silhouette   SILHOUETTE_OK 80 views
export             EXPORT_OK SHOT_001 120 frames
check_exports      checks_failed: []
check_alembic      checks_failed: []
check_states T=140 STATES_OK SHOT_001 windows=6 pass=23 fail=0 not_evaluated=0
pick_frames        1001,1090,1094
```

Полные прогоны `check_asset.sh` на 25 % и 100 % — на вашей стороне (Q24.5).

## LICENSES — добавляется к рывку 1

| Элемент | Источник | Лицензия | Где |
|---|---|---|---|
| Окружение `ENV_FLOOR`, `ENV_WALL`, материал `ENV_GREY`; `PROP_A` (мячик на штырьке), материал `PROP_A_RED`; свет `KEY_001`/`FILL_001`, камера | своё — `make_shot_001.py` | — | `C_ENV`, `C_LIGHTS`, `CAM_001` |
| Анимация `FACE_CTRL` и костей `RIG_HERO` | своё — `animate_shot_001.py` | — | action'ы `FACE_CTRL`, `RIG_HERO` |
