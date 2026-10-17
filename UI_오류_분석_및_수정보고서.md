# Sunrise Image 최종 UI 마감 · 텍스트 정렬 · 공간 효율성 최적화 보고서

## 1. 최종 마무리 보완 요약
요청하신 **3가지 핵심 마감 사항(라인 끊김 해소, 드롭박스 내 텍스트 정렬 위치, 레이아웃 공간 효율성 극대화)**을 전수 반영하여 최종 정리를 완료했습니다.

| 보완 항목 | 원인 분석 | 최종 해결 및 마감 내역 |
| :--- | :--- | :--- |
| **1. 라인이 중간중간 끊기는 현상 수정 및 전체 UI 라인 마감** | • `border: 1.5px solid` 소수점 두께가 Windows 배율(100%/125%)에서 모서리 반올림 오차로 두께 불균일 유발<br>• `QComboBox::drop-down` 및 `QSpinBox::up/down-button`에 `margin: 1~2px`와 상하 패딩(`padding-top/bottom: 2px`)이 들어가 내부 세로 구분선이 상·하단 외곽선에 닿지 않고 공중에 떠서 끊어져 보임<br>• 테이블 행(`QTreeWidget::item`)에 연속 하단 구분선이 없어 컬럼 사이에서 선이 끊겨 보임 | • 모든 카드·입력창·버튼·테이블 외곽선을 **정수 `1px solid`로 통일**하여 모서리 계단 현상 및 끊김 제거<br>• `QComboBox` 및 `QSpinBox`의 상하 패딩을 `0px`로 두고 서브컨트롤 `margin: 0px; subcontrol-origin: padding; background: transparent;`를 적용하여 **내부 세로·가로 구분선이 외곽 테두리 내벽에 1px 오차 없이 끝까지 직결**되도록 수정<br>• `#docTable::item` 및 `#imageTree::item`에 `border-bottom: 1px solid`, 헤더에 `border-right: 1px solid`를 부여해 표 내부 라인이 좌우 끝까지 끊김 없이 이어지도록 마감 |
| **2. 드롭박스(`QComboBox`) 및 입력창 내부 텍스트 정렬 위치** | • `QComboBox`와 `QSpinBox`에 상하 비대칭 패딩이 적용되어 텍스트가 박스 상단으로 치우쳐 보이거나 팝업 항목과 좌측 시작점(`X` 좌표)이 어긋남 | • `QComboBox { padding: 0px 28px 0px 10px; min-height: 25px; }` 및 `QComboBox QAbstractItemView::item { padding: 0px 10px; min-height: 25px; }`로 상하 패딩을 `0px`로 통일해 Qt 네이티브 수직 중앙 정렬(`AlignVCenter`)이 정확히 정중앙에 위치하도록 보정<br>• `SmartComboBox.addItem()`에서 모든 항목에 `Qt.AlignmentFlag.AlignLeft \| Qt.AlignmentFlag.AlignVCenter`를 강제 지정하고, 닫힌 박스와 열린 팝업 리스트의 텍스트 시작점(`좌측 10px`)을 수직 일직선으로 일치시킴 |
| **3. 레이아웃 공간 효율성 및 그리드 정렬선 통일** | • 우측 설정 카드 `02`(`저장 형식`), `03`(`해상도`), `04`(`JPG / WebP 품질`)의 좌측 라벨 폭이 카드마다 달라(`82px` vs `118px`), 입력 칸들의 시작 위치가 카드별로 들쭉날쭉하여 공간 낭비 및 시각적 산만함 발생 | • `ui_layout_groups.py`의 `_configure_unified_4col_grid()`를 통해 **카드 02·03·04 전체에 통일된 4열 그리드 축(`좌측 라벨 92px`, `우측 라벨 72px`)**을 적용하여, 3개 카드의 모든 드롭박스·스핀박스·입력창이 **동일한 수직 정렬선(`X`축)**에 맞춰 정렬되도록 개선<br>• 좌측 `01 문서 목록` 폭을 `420px`로 넓히고 카드 내부 여백을 `(12, 8, 12, 8)`로 컴팩트화하여 테이블 표시 행 수와 미리보기 캔버스 면적을 극대화 |

---

## 2. 레이아웃 그룹 모듈화 구조 (`ui_layout_groups.py` & `ui_theme.py`)

* **`ui_layout_groups.py`**: 8개 독립 레이아웃 그룹 빌더 함수(`build_header_group`, `build_document_list_group`, `build_collection_shared_group`, `build_format_settings_group`, `build_resolution_settings_group`, `build_capacity_settings_group`, `attach_progress_footer_group`, `build_preview_*_group`)로 분리하여 특정 영역 수정 시 다른 영역에 영향을 주지 않도록 격리했습니다.
* **`ui_theme.py`**: 7개 QSS 분기 함수(`_qss_base_containers`, `_qss_header_group`, `_qss_buttons_group`, `_qss_inputs_combos_spins_group`, `_qss_form_checkbox_group`, `_qss_tables_and_trees_group`, `_qss_progress_and_menus_group`)로 스타일 스코프를 분리했습니다.
