# 원하는 포즈로 이미지 만드는 도구

## 도구 설명
- 참조 사진에서 OpenPose로 **관절(자세)만** 뽑아내고, 그 자세를 유지한 채 프롬프트로 지정한 **전혀 다른 인물·의상·배경**의 이미지를 만듭니다.
- ControlNet의 Pose 조건을 사용하며, GPU 사정에 따라 FLUX 계열 → SDXL → SD1.5 순으로 자동으로 내려가며 실행됩니다.

## 사용법
1. `pose_tool.ipynb` 를 클릭한 뒤 상단의 **"Open in Colab"** 배지(또는 [colab.research.google.com](https://colab.research.google.com) → GitHub 탭에 저장소 주소 붙여넣기)로 엽니다.
2. `런타임` → `런타임 유형 변경` → **GPU(T4)** 로 설정한 뒤, 셀 0부터 **위에서 아래로 순서대로** 실행합니다.
   - 셀 3에서 참조 사진을 업로드합니다. 사진이 없으면 업로드 창을 닫으면 되고, 저장소에 들어 있는 합성 스켈레톤(`samples/pose_01.png`)이 대신 쓰입니다.
   - 셀 6(모델 로드)이 가장 오래 걸립니다(5~15분).
3. 결과 이미지는 Colab의 `/content/pose-image-tool/samples/` 에 저장되고, 마지막 셀에서 `samples.zip` 으로 내려받을 수 있습니다.

## 테스트 결과
- 포즈 1: 정면으로 서 있는 자세 → 프롬프트: `a young woman standing in a sunlit library, beige trench coat` → 결과: [잘 됨/어긋남]
- 포즈 1(동일) + 프롬프트 변경: `astronaut on a red desert planet` → 결과:
- 포즈 1(동일) + 프롬프트 변경: `korean ink painting of a scholar in hanbok` → 결과:
- 포즈 2: 양팔을 위로 든 자세 → 프롬프트는 포즈 1과 동일 → 결과:
- 포즈 강도(`pose_strength`) 0.4 / 0.7 / 1.0 비교 → 적정값:

> 위 항목은 노트를 실제로 돌린 뒤 본인의 관찰로 채우세요. 상세 기록은 노트 마지막 마크다운 셀에 있습니다.

## 한계
- **손·발가락**은 OpenPose 기본 설정에서 관절을 뽑지 않아 자주 뭉개집니다. 셀 4의 `include_hand=True` 로 개선되지만 느려집니다.
- **옆모습, 팔다리가 겹친 자세, 앉은 자세**는 관절 추정 자체가 흔들려 결과가 어긋나기 쉽습니다.
- `pose_strength` 가 1.0에 가까우면 자세는 정확해지지만 인물이 뻣뻣해지고 프롬프트 반영이 약해집니다.
- FLUX 계열은 모델 저장소 이름·게이팅 정책이 바뀔 수 있어 실패할 수 있습니다. 그 경우 노트가 자동으로 SDXL/SD1.5로 내려가며, 셀 5의 `FLUX_BASE_CANDIDATES` 를 최신 모델 카드 이름으로 고치면 다시 A등급으로 돌아갑니다.
- 참조 사진에 **사람이 둘 이상**이면 포즈 맵도 여러 명으로 나와 결과가 복잡해집니다. 한 명만 나온 전신 사진을 권합니다.

## 폴더 구조
```
pose-image-tool/
├── README.md
├── pose_tool.ipynb     # Colab 튜토리얼 노트 (핵심)
├── prompts.md          # 테스트에 쓴 프롬프트 모음
└── samples/
    ├── pose_01.png     # 참조 포즈 (차렷 자세, 합성 스켈레톤)
    ├── pose_02.png     # 참조 포즈 (양팔 든 자세)
    ├── output_01.png   # ← 노트 실행 후 여기에 추가
    └── output_02.png   # ← 노트 실행 후 여기에 추가
```
