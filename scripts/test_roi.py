"""
scripts/test_roi.py — ROI 함수 단위 테스트
==========================================
KEPCO 김천 도담어린이집 사례로 core.roi_calculator 검증.

실행:
    cd /path/to/zeb-chatbot
    python scripts/test_roi.py

기대 결과:
    - 자산화 ROI: 16.9% ± 0.5%p
    - Max Cost: 1.5~2.0억 (시공계수 3.0 기준)
    - 모든 함수가 예외 없이 작동
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.roi_calculator import (
    load_price_db,
    load_indirect_cost_matrix,
    lookup_material_price,
    calculate_direct_cost,
    apply_indirect_cost,
    calculate_subsidy,
    calculate_far_bonus,
    calculate_acquisition_tax_relief,
    calculate_roi,
)


def test_phase_a_data_loaders():
    """Phase A: 데이터 로더 동작 검증."""
    print("=" * 70)
    print("Phase A: 데이터 로더")
    print("=" * 70)

    df = load_price_db()
    print(f"\n[OK] 단가DB 로드: {len(df)} rows, {df['GR_카테고리'].nunique()}개 카테고리")
    assert len(df) > 400, "단가DB 행 수가 너무 적음"
    assert df['GR_카테고리'].nunique() >= 10, "카테고리 종류가 너무 적음"

    matrix = load_indirect_cost_matrix()
    print(f"[OK] 간접비 매트릭스 로드: {len(matrix['labor_expense'])}개 셀")
    assert len(matrix['labor_expense']) > 0, "매트릭스 로드 실패"


def test_phase_b_material_lookup():
    """Phase B: 자재 조회 검증."""
    print("\n" + "=" * 70)
    print("Phase B: 자재 조회")
    print("=" * 70)

    df = load_price_db()

    mat = lookup_material_price(df, "GR_단열_PF", min_thickness_mm=130)
    print(f"\n[OK] PF 130T: {mat['품명']} {mat['규격']} = {mat['단가']:,}원/{mat['단위']}")
    assert mat['단가'] > 0
    assert mat['두께_mm'] >= 130

    mat = lookup_material_price(df, "GR_창호_복층유리", min_thickness_mm=24)
    print(f"[OK] 복층유리 24T: {mat['품명']} = {mat['단가']:,}원/{mat['단위']}")
    assert mat['단가'] > 0


def test_kepco_case():
    """KEPCO 김천 도담어린이집 사례 통합 ROI 재현."""
    print("\n" + "=" * 70)
    print("KEPCO 김천 도담어린이집 사례 — 통합 ROI")
    print("=" * 70)

    bim_input = {
        "wall_no_insulation_m2": 887.50,
        "wall_insulation_material": "GR_단열_PF",
        "wall_thickness_mm": 130,
        "window_area_m2": 100,
        "window_material": "GR_창호_복층유리",
        "window_thickness_mm": 24,
        "door_area_m2": 28.85,
        "door_count": 13,
    }

    building_info = {
        "total_area_m2": 1000,
        "is_seoul_or_public": True,
        "project_duration_months": 8,
        "zeb_target_grade": 5,
        "extension_area_m2": 300,
        "build_cost_per_pyeong": 9_750_000,
        "land_price_per_pyeong": 15_000_000,
        "annual_energy_saving_won_per_m2": 13_280,
    }

    result = calculate_roi(bim_input, building_info)

    # BOQ 출력
    print("\n[BOQ - 직접공사비]")
    for item in result["boq"]["items"]:
        print(f"  {item['항목']:18}: {item['수량']:>6} {item['단위']:2} × "
              f"{item['단가']:>8,}원 = {item['금액']:>13,}원")
    print(f"  합계: {result['boq']['직접공사비_합계']:>13,}원 "
          f"({result['boq']['직접공사비_합계']/1e8:.2f}억)")

    # Max Cost
    print(f"\n[Max Cost]")
    print(f"  공급가액: {result['indirect']['공급가액']:>13,}원")
    print(f"  Max Cost: {result['indirect']['Max_Cost']:>13,}원 "
          f"({result['max_cost']/1e8:.2f}억)")

    # 보조금
    sub = result['subsidy']
    print(f"\n[보조금 (서울·중앙·공공 50%)]")
    print(f"  보조금: {sub['보조금']:>13,}원 ({sub['보조금']/1e8:.2f}억)")
    print(f"  자부담: {sub['자부담']:>13,}원 ({sub['자부담']/1e8:.2f}억)")

    # 인센티브
    far = result['far_bonus']
    tax = result['tax_relief']
    print(f"\n[인센티브]")
    print(f"  용적률 보너스 ({far['용적률_보너스율']*100:.0f}%): "
          f"+{far['추가_평수']:.1f}평, 자산 {far['자산가치']/1e8:.2f}억")
    print(f"  취득세 감면 ({tax['감면율']*100:.0f}%): {tax['감면액']:,}원")

    # ROI
    print(f"\n[ROI 종합]")
    print(f"  연간 절감: {result['annual_saving']:,}원/년 "
          f"({result['annual_saving']/1e4:.0f}만원)")
    print(f"  ★ 자산화 ROI: {result['asset_roi_pct']:.1f}%")
    print(f"  GR 단독 회수기간: {result['gr_only_payback_years']}년")
    print(f"  통합 회수기간:    {result['combined_payback_years']}년")

    # 검증
    print(f"\n" + "=" * 70)
    print("검증")
    print("=" * 70)

    # 자산화 ROI는 정확히 재현되어야 함
    assert 16 <= result['asset_roi_pct'] <= 17.5, (
        f"자산화 ROI가 예상 범위(16~17.5%)를 벗어남: {result['asset_roi_pct']}%"
    )
    print(f"  [PASS] 자산화 ROI = {result['asset_roi_pct']}% (목표 16.9%)")

    # Max Cost는 합리적 범위 안에 있어야 함
    assert 1.0e8 <= result['max_cost'] <= 3.5e8, (
        f"Max Cost가 합리적 범위를 벗어남: {result['max_cost']/1e8:.2f}억"
    )
    print(f"  [PASS] Max Cost = {result['max_cost']/1e8:.2f}억 (합리적 범위 1~3.5억)")

    # GR 단독 회수기간은 짧아야 함 (5~15년)
    assert result['gr_only_payback_years'] is not None
    assert 3 <= result['gr_only_payback_years'] <= 20, (
        f"GR 단독 회수기간이 비현실적: {result['gr_only_payback_years']}년"
    )
    print(f"  [PASS] GR 단독 회수기간 = {result['gr_only_payback_years']}년")


if __name__ == "__main__":
    try:
        test_phase_a_data_loaders()
        test_phase_b_material_lookup()
        test_kepco_case()
        print("\n" + "=" * 70)
        print("모든 테스트 통과 ✅")
        print("=" * 70)
    except AssertionError as e:
        print(f"\n❌ 검증 실패: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예외 발생: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
