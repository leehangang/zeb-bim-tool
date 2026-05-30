"""
scripts/test_bim.py — BIM 진단 단위 테스트
==========================================
KEPCO 도담어린이집 가상 BIM JSON 샘플로 core.bim_diagnoser 검증.

실행:
    python scripts/test_bim.py

기대 결과:
    - 외벽 단열보강: 부분적용 (43%) — 4점 (10점 만점)
    - 바닥 단열: 적용 — 3점
    - 신재생: 적용 (자립률 약 5.6%) — 2점
    - 환기: 부분적용
    - 11개 항목 중 약 4~5개 적용 확인
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.bim_diagnoser import (
    parse_bim_json,
    map_to_gr_elements,
    score_compliance,
    check_u_value,
    generate_diagnosis_report,
    diagnose_from_json,
    build_reinforcement_plan,
    optimize_within_budget,
    optimize_for_target_grade,
    format_optimization_report,
)


def test_full_pipeline():
    """KEPCO 가상 JSON 전체 파이프라인."""
    sample_path = PROJECT_ROOT / "data" / "sample_bim" / "doam_archi_sample.json"

    print("=" * 70)
    print("BIM 진단 파이프라인 검증")
    print("=" * 70)
    print(f"\n입력: {sample_path.name}")

    result = diagnose_from_json(str(sample_path))

    # 매핑 결과 출력
    print("\n[11개 GR 매핑 결과]")
    for key, info in result["gr_mapping"].items():
        status = info.get("status", "?")
        ratio = info.get("적용비율")
        ratio_str = f"{ratio*100:.0f}%" if ratio is not None else "-"
        print(f"  {key}: {status} ({ratio_str})")

    # 점수 분해
    print("\n[점수 분해]")
    bd = result["score"]["breakdown"]
    print(f"  단열 (벽/지붕/바닥):  {bd['단열']['소계']:>2}/20점")
    print(f"  창호 (창/문/일사):    {bd['창호']['소계']:>2}/16점")
    print(f"  설비 (냉/난/급):      {bd['설비']['소계']:>2}/15점")
    print(f"  신재생 (자립률):      {bd['신재생']['점수']:>2}/5점")
    print(f"  환기 (폐열회수):      {bd['환기']['점수']:>2}/5점")
    print(f"  LED:                  {bd['LED']['점수']:>2}/2점")
    print(f"  BEMS:                 {bd['BEMS']['점수']:>2}/2점")
    print(f"  에너지절감률:         {bd['에너지절감률']['점수']:>2}/10점")
    print(f"  사업여건:             {bd['사업여건']['소계']:>2}/20점")
    print(f"  ────────────────────")
    print(f"  총점:                 {result['score']['total_score']:>2}/100점")
    print(f"  등급:                 {result['score']['grade']}")

    # 검증 어설션
    print("\n[검증]")

    mapping = result["gr_mapping"]

    # 외벽 단열보강: 43% 적용
    wall = mapping["3_외벽단열보강"]
    assert 0.40 <= wall["적용비율"] <= 0.50, (
        f"외벽 적용비율이 예상 범위(40~50%) 벗어남: {wall['적용비율']*100:.1f}%"
    )
    assert wall["status"] == "부분적용"
    print(f"  [PASS] 외벽 단열: {wall['적용비율']*100:.0f}% (부분적용)")

    # 바닥 단열: 100% 적용
    floor = mapping["4_바닥단열난방"]
    assert floor["status"] == "적용"
    print(f"  [PASS] 바닥 단열·난방: 적용 (XL 배관)")

    # 신재생: 적용
    pv = mapping["10_신재생태양광"]
    assert pv["status"] == "적용"
    assert pv["용량_kW"] == 5.4
    print(f"  [PASS] 신재생: {pv['용량_kW']}kW, 자립률 {pv['자립률_추정']*100:.1f}%")

    # 환기: 부분적용 (covered 800 / total 1251)
    vent = mapping["6_폐열회수환기"]
    assert vent["status"] in ("부분적용", "적용")
    print(f"  [PASS] 폐열회수환기: {vent['status']}")

    # 창호: 일반 단창 → u=3.6 vs 기준 1.0 → 미적용
    win = mapping["1_고성능창호"]
    assert win["status"] == "미적용"
    print(f"  [PASS] 고성능창호: 미적용 (u={3.6} > {win['기준_U값']})")

    # 단열문: 미적용
    door = mapping["2_고기밀성단열문"]
    assert door["status"] == "미적용"
    print(f"  [PASS] 단열문: 미적용")

    # 점수 합리적 범위
    total = result["score"]["total_score"]
    assert 20 <= total <= 50, f"총점이 예상 범위(20~50점)를 벗어남: {total}"
    print(f"  [PASS] 총점: {total}점 (예상 범위)")


def test_u_value_check():
    """열관류율 적합성 판정 검증."""
    print("\n" + "=" * 70)
    print("열관류율 적합성 검증")
    print("=" * 70)

    # 외벽 0.156 vs 중부2 기준 0.170 → 적합
    r = check_u_value("외벽", 0.156, region="중부2", facing="direct")
    assert r["compliant"] is True
    print(f"  [PASS] 외벽 u=0.156 (중부2 직접) - 적합 (기준 {r['limit']}, 여유 {r['margin_pct']}%)")

    # 외벽 0.62 vs 중부2 0.170 → 부적합
    r = check_u_value("외벽", 0.62, region="중부2", facing="direct")
    assert r["compliant"] is False
    print(f"  [PASS] 외벽 u=0.62 (중부2 직접) - 부적합 (기준 {r['limit']})")

    # 창 u=3.6 vs 중부2 1.0 → 부적합
    r = check_u_value("창", 3.6, region="중부2", facing="direct")
    assert r["compliant"] is False
    print(f"  [PASS] 창 u=3.6 (중부2 직접) - 부적합 (기준 {r['limit']})")

    # 측정값 없음
    r = check_u_value("외벽", None, region="중부2")
    assert r["compliant"] is None
    print(f"  [PASS] u값 없음 - 'None' 처리")


def test_roi_integration():
    """진단 ↔ ROI 연계 보강 계획 검증 (Step 3-A)."""
    print("\n" + "=" * 70)
    print("진단 ↔ ROI 연계 보강 계획 검증")
    print("=" * 70)

    sample_path = PROJECT_ROOT / "data" / "sample_bim" / "doam_archi_sample.json"

    # with_roi=True로 호출
    result = diagnose_from_json(str(sample_path), with_roi=True, duration_months=8)

    # roi_plan 존재 확인
    assert "roi_plan" in result, "결과에 roi_plan 키 없음"
    plan = result["roi_plan"]
    assert plan is not None, "roi_plan이 None"
    assert isinstance(plan, list), "roi_plan은 list여야 함"
    assert len(plan) > 0, "보강 계획이 비어있음"
    print(f"  [PASS] 보강 계획 {len(plan)}개 항목 생성")

    # 각 항목의 필수 필드 검증
    required_keys = {
        "key", "label", "수량", "단위", "자재",
        "직접공사비", "Max_Cost",
        "현재점수", "보강후점수", "점수상승", "점수만점",
        "효율_점수당억",
    }
    for i, p in enumerate(plan):
        missing = required_keys - set(p.keys())
        assert not missing, f"plan[{i}] '{p.get('label','?')}' 필수 필드 누락: {missing}"
    print(f"  [PASS] 모든 항목이 필수 필드 보유")

    # 효율 내림차순 정렬 확인
    효율_list = [p["효율_점수당억"] for p in plan]
    assert 효율_list == sorted(효율_list, reverse=True), (
        f"효율 내림차순 정렬 안 됨: {효율_list}"
    )
    print(f"  [PASS] 효율 내림차순 정렬")

    # 단열문 비용이 0이 아닌지 (GR_문_금속문 카테고리 매핑 확인)
    door_plan = next((p for p in plan if "단열문" in p["label"]), None)
    if door_plan:
        assert door_plan["Max_Cost"] > 0, (
            f"단열문 Max_Cost가 0이면 카테고리 매핑 실패 가능"
        )
        print(f"  [PASS] 단열문 자재 조회: {door_plan['Max_Cost']:,}원")

    # 도담어린이집 검증: 미적용 항목이 11개 중 8개 이상이어야 함
    assert len(plan) >= 8, (
        f"미적용 항목이 너무 적음 (도담어린이집은 11개 중 대부분 미적용): {len(plan)}"
    )
    print(f"  [PASS] 미적용/부분적용 {len(plan)}개 항목")

    # 누적 점수 상승이 합리적 범위
    total_uplift = sum(p["점수상승"] for p in plan)
    total_cost = sum(p["Max_Cost"] for p in plan)
    assert 30 <= total_uplift <= 70, (
        f"점수상승이 예상 범위(30~70점) 벗어남: {total_uplift}"
    )
    print(f"  [PASS] 누적 점수상승 +{total_uplift}점 (현재 "
          f"{result['score']['total_score']} → 보강 후 "
          f"{result['score']['total_score'] + total_uplift})")

    # 누적 비용 합리적 범위 (도담 1251㎡, 종합공사 약 5~10억)
    assert 200_000_000 <= total_cost <= 1_500_000_000, (
        f"누적 비용이 예상 범위(2~15억) 벗어남: {total_cost:,}원"
    )
    print(f"  [PASS] 누적 보강 비용 {total_cost:,}원 ({total_cost/1e8:.2f}억)")

    # 1순위 출력 (가성비 최고)
    top = plan[0]
    print(f"\n  [상위 3개 항목]")
    for i, p in enumerate(plan[:3], 1):
        print(f"    {i}. {p['label']:35s} "
              f"비용 {p['Max_Cost']:>12,}원, +{p['점수상승']}점, "
              f"효율 {p['효율_점수당억']:.2f}")

    # 리포트에 ROI 섹션 포함 확인
    report = result["report"]
    assert "보강 계획 ROI 분석" in report, "리포트에 ROI 섹션 없음"
    assert "효율(점/억)" in report, "리포트에 효율 컬럼 없음"
    print(f"  [PASS] 리포트에 ROI 표 포함")


def test_backward_compatibility():
    """기존 호출(with_roi 미사용) 호환성 검증."""
    print("\n" + "=" * 70)
    print("하위 호환성 검증 (기존 호출 방식)")
    print("=" * 70)

    sample_path = PROJECT_ROOT / "data" / "sample_bim" / "doam_archi_sample.json"

    # 기존 방식: with_roi 매개변수 없이 호출
    result = diagnose_from_json(str(sample_path))

    assert "gr_mapping" in result
    assert "score" in result
    assert "report" in result
    assert result.get("roi_plan") is None, (
        "with_roi=False(기본)일 때 roi_plan은 None이어야 함"
    )
    print(f"  [PASS] 기존 호출 방식 정상 (roi_plan=None)")

    # 리포트에 ROI 섹션이 없어야 함
    assert "보강 계획 ROI 분석" not in result["report"], (
        "with_roi=False인데 리포트에 ROI 섹션이 들어감"
    )
    print(f"  [PASS] 리포트에 ROI 섹션 없음 (기본 모드)")


def test_report_generation():
    """리포트 자연어 생성 확인."""
    print("\n" + "=" * 70)
    print("진단 리포트 생성")
    print("=" * 70)

    sample_path = PROJECT_ROOT / "data" / "sample_bim" / "doam_archi_sample.json"
    result = diagnose_from_json(str(sample_path))

    report = result["report"]
    assert "# BIM 진단 리포트" in report
    assert "총점" in report
    assert "11개 GR 기술요소 현황" in report
    assert "보강 권장 사항" in report

    print(f"\n리포트 길이: {len(report)} chars")
    print("\n--- 리포트 첫 30줄 ---")
    for line in report.split("\n")[:30]:
        print(f"  {line}")
    print("  ...")


def test_optimization_budget():
    """예산 상한 보강 조합 최적화 검증 (Step 3-D)."""
    print("\n" + "=" * 70)
    print("최적화 검증: 예산 상한 모드")
    print("=" * 70)

    sample_path = PROJECT_ROOT / "data" / "sample_bim" / "doam_archi_sample.json"
    result = diagnose_from_json(str(sample_path), with_roi=True)
    plan = result["roi_plan"]
    current = result["score"]["total_score"]

    # 2억 예산
    opt = optimize_within_budget(plan, budget_won=200_000_000, current_score=current)

    assert opt["사용예산"] <= 200_000_000, "예산 초과"
    assert len(opt["selected"]) > 0, "선택된 항목 없음"
    assert opt["누적점수상승"] > 0, "점수 상승 없음"
    print(f"  [PASS] 2억 예산: {opt['사용예산']:,}원 사용, "
          f"+{opt['누적점수상승']}점 ({opt['현재등급']} → {opt['예상등급']})")

    # 예산 0
    opt0 = optimize_within_budget(plan, budget_won=0, current_score=current)
    assert opt0["사용예산"] == 0
    assert opt0["누적점수상승"] == 0
    assert opt0["예상총점"] == current
    print(f"  [PASS] 예산 0: 빈 조합 정상 처리")

    # 충분히 큰 예산 (10억) - 전 항목 채택 가능
    opt_big = optimize_within_budget(plan, budget_won=1_000_000_000, current_score=current)
    valid_plans = [p for p in plan if p.get("Max_Cost", 0) > 0]
    assert len(opt_big["selected"]) == len(valid_plans), (
        "예산 충분 시 모든 유효 항목 채택"
    )
    print(f"  [PASS] 충분한 예산: {len(opt_big['selected'])}개 전 항목 채택")


def test_optimization_target_grade():
    """목표 등급 보강 조합 최적화 검증 (Step 3-D)."""
    print("\n" + "=" * 70)
    print("최적화 검증: 목표 등급 모드")
    print("=" * 70)

    sample_path = PROJECT_ROOT / "data" / "sample_bim" / "doam_archi_sample.json"
    result = diagnose_from_json(str(sample_path), with_roi=True)
    plan = result["roi_plan"]
    current = result["score"]["total_score"]   # 도담 = 25점

    # B등급 (65점) - 도달 가능해야
    opt_b = optimize_for_target_grade(plan, "B", current)
    assert opt_b["achievable"], "B등급 달성 가능해야 함"
    assert opt_b["달성점수"] >= 65
    print(f"  [PASS] B등급(65점): {opt_b['필요비용']:,}원, "
          f"{opt_b['달성점수']}점 달성")

    # A+ (85점) - 도달 불가능 (도담 데이터로는 75점이 한계)
    opt_a = optimize_for_target_grade(plan, "A+", current)
    assert not opt_a["achievable"], (
        f"A+ 달성 불가여야 함 (도담은 75점 한계): {opt_a['달성점수']}"
    )
    print(f"  [PASS] A+ 불가 감지 (최대 {opt_a['달성점수']}점, 목표 85점)")

    # 잘못된 등급
    try:
        optimize_for_target_grade(plan, "Z", current)
        assert False, "잘못된 등급에 ValueError 안 던짐"
    except ValueError:
        print(f"  [PASS] 잘못된 등급 거부")


def test_optimization_report_format():
    """최적화 결과 마크다운 리포트 검증."""
    print("\n" + "=" * 70)
    print("최적화 리포트 포맷 검증")
    print("=" * 70)

    sample_path = PROJECT_ROOT / "data" / "sample_bim" / "doam_archi_sample.json"
    result = diagnose_from_json(str(sample_path), with_roi=True)
    plan = result["roi_plan"]
    current = result["score"]["total_score"]

    opt_b = optimize_for_target_grade(plan, "B", current)
    report = format_optimization_report(opt_b, mode="target")
    assert "목표 등급 B" in report or "달성 보강 조합" in report
    assert "채택 항목" in report
    assert "필요 비용" in report
    print(f"  [PASS] 목표 등급 리포트 ({len(report)} chars)")

    opt_budget = optimize_within_budget(plan, 200_000_000, current)
    report_b = format_optimization_report(opt_budget, mode="budget")
    assert "예산 상한" in report_b
    assert "채택 항목" in report_b
    assert "예산 초과로 제외된 항목" in report_b
    print(f"  [PASS] 예산 모드 리포트 ({len(report_b)} chars)")


if __name__ == "__main__":
    try:
        test_full_pipeline()
        test_u_value_check()
        test_report_generation()
        test_backward_compatibility()
        test_roi_integration()
        test_optimization_budget()
        test_optimization_target_grade()
        test_optimization_report_format()
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
