# TRACEABILITY MATRIX

| § Спецификации | Описание | Модуль / Функция | Тест | Статус |
|---|---|---|---|---|
| §1.1 | Палитра слоев C00..C29, T1, T2 | openburn.palette | test_palette | done |
| §1.2 | Подбор цвета (Евклидово расстояние) | openburn.palette | test_palette | done |
| §2.1 | Чтение/запись .lbrn (XML) | openburn.project | test_v14_lbrn_lbrn2 | done |
| §2.2 | Чтение/запись .lbrn2 (JSON) | openburn.project | test_v14_lbrn_lbrn2 | done |
| §2.3 | Семантика XForm и Group | openburn.geometry | test_v01_v02 | done |
| §3 | Импорт SVG | openburn.svg | test_v11_svg | done |
| §4 | Реестр CutSetting | openburn.project | test_project | done |
| §5 | Профиль станка DeviceProfile | openburn.profile | test_profile | done |
| §6.1 | Правила формата G-code GRBL | openburn.gcode | test_v01_v02 | done |
| §6.2 | Геометрия контуров и обход CCW/CW, эллипсы, Cr | openburn.geometry, gcode | test_v01, test_v02, test_v03 | done |
| §6.3 | Заливка Scan/Fill, overscan, разрывы <= 5мм | openburn.fill | test_v04, test_v05, test_v06 | done |
| §6.4 | Управление осью Z, numPasses, zStep, zOffset | openburn.gcode | test_v08_passes_z | done |
| §6.5 | Модальность F и восстановление после Z | openburn.gcode | test_v08_passes_z | done |
| §7 | Растровая обработка, Grayscale, дизеринги | openburn.raster | test_v10_raster | done |
| §8 | Сетевой REST API и SSE | openburn.api | test_api | done |
| §10 V01 | Rect 20x10 Line, C00, F6000 S200 | openburn.gcode | test_v01_v02 | done |
| §10 V02 | Rect 20x10 rotated 30 deg | openburn.geometry | test_v01_v02 | done |
| §10 V03 | Эллипс + Окружность (G2/G3, chord <= 0.05) | openburn.geometry | test_v03_ellipse | done |
| §10 V04 | 10x10 с отверстием 4x4, Fill, gap<=5mm S0 | openburn.fill | test_v04_fill | done |
| §10 V05 | Overscan 2.5 mm | openburn.fill | test_v05_overscan | done |
| §10 V06 | Scan angle 45 deg | openburn.fill | test_v06_angle | done |
| §10 V07 | 3 квадрата Inner-to-Outer | openburn.gcode | test_v07_inner_first | done |
| §10 V08 | Слои по приоритету + Z заглубление + восстановление F | openburn.gcode | test_v08_passes_z | done |
| §10 V09 | Режим Scan+Cut | openburn.gcode | test_v09_scan_cut | done |
| §10 V10 | Растр Grayscale 4x4 px | openburn.raster | test_v10_raster | done |
| §10 V11 | SVG с прямоугольником в группе c transform | openburn.svg | test_v11_svg | done |
| §10 V12 | Режимы начала координат Absolute, Current, Top-Left | openburn.gcode | test_v12_origins | done |
| §10 V13 | Слой T1 исключен из генерации G-code | openburn.gcode | test_v13_tool_layer | done |
| §10 V14 | Эквивалентность .lbrn и .lbrn2 | openburn.project | test_v14_lbrn_lbrn2 | done |
