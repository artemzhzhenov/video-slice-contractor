# Обновление contractor-restore-kit (2026-10-30, конец сессии)
Положить поверх `contractor/contractor-restore-kit/` (существующие restore_env.sh, bpy_module_runner.py, финальные
скрипты шотов — остаются). Обновлено: `scripts/burst3/` — build_character.py и hair_on_head.py (= сданные в
pair_08_09_v01, без eval, кудрявая чёлка), subject_01…09.json, subjects_plan.json, controls/*.json; `tools/` —
blender_bpy_shim, build_shots.sh, pair_queue.sh, preview.py, crop.py, glow.py, crop_nosack.py; `tools/burst3/` —
check_plan.py, sculpt_bumps.py, face_measure.py (v2), plan/ (face_basis_v2.npz, bump_data.npz, pick_bumps.py, model.py …).
HANDOFF.md = contractor/HANDOFF-contractor.md (одна версия).
Пути в plan/*.py и очередях — рабочие папки сессии (/home/claude/…); поправить под свою раскладку.
