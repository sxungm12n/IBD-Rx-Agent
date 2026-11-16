# 보관 (2026-11-15)

지금 연구 결과를 만드는 데 쓰지 않는 파일을 **지우지 않고** 옮겨 둔 곳이다. 예전 결과를 똑같이 다시 만들 수 있게 남겨 둔다. 다른 스크립트는 이 폴더의 파일을 불러 쓰지 않는다.

| 파일 | 원래 위치 | 옮긴 이유 |
| --- | --- | --- |
| `scripts/compare_v2.py` | `STAGE1/` | v1과 v2·v2.1 채점 비교 (2026-11-10). 결과는 `eval_out/regrade_v2_compare.txt`, `eval_out/regrade_v21_compare.txt` |
| `scripts/rebuild_20261110_state.py` | 새로 만듦 | 위 비교를 다시 돌리기 위한 11-10 상태 복원 (아래) |
| `scripts/progress.py` | `STAGE1/` | 2026-11-12 실행의 진행 상황 확인용 일회용 스크립트. 없는 `run_*.sh`를 찾고 문항 수가 그때 값으로 고정됨 |
| `backup_20261112_scripts/` | `STAGE1/output/_backup_20261112/scripts/` | 2026-11-12 시점 스크립트 사본 (지금은 없는 `generate.py` 포함). 같은 폴더의 문항 백업은 그대로 둠 |
| `eval_out/test/` | `STAGE1/eval_out/test/` | 2026-10-27 형식 시험 실행 결과 |
| `README_STAGE1_20261027.md` | `STAGE1/README.md` | 2026-10-27판 설명서 (v1 채점 기준). 2026-11-15에 지금 방법으로 새로 씀 |

## 11-10 채점 비교 다시 만들기 (API 없음)

`compare_v2.py`는 지금 파일만 읽어서, 2026-11-12에 A형 31문항(질문 변경 24, 열쇠 변경 7)을 다시 받은 뒤로는 그대로 돌리면 `KeyError`로 멈춘다(옮기기 전에도 같음). 그때 옛 답·채점은 `eval_out/<run>/superseded_*.jsonl`로 남겨 두었으므로, 11-10 상태를 따로 폴더에 복원해서 돌린다.

```bash
# IBD보험가이드북 폴더에서
python3 STAGE1/_archive/scripts/rebuild_20261110_state.py STAGE1 /tmp/stage1_20261110
python3 STAGE1/_archive/scripts/compare_v2.py /tmp/stage1_20261110 v21
python3 STAGE1/_archive/scripts/compare_v2.py /tmp/stage1_20261110 v2
```

2026-11-15 확인: v21은 저장된 결과와 글자 하나까지 같다. v2는 숫자가 모두 같고, 표기만 '교정'이 'Claude 검토'로 바뀌었다(11-10에 스크립트 표기를 고친 뒤 v2 결과 파일은 다시 쓰지 않았음).
