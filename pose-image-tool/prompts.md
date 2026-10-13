# 테스트에 쓴 프롬프트 모음

공통 설정: `seed = 1234`, `768 x 1024`, `pose_strength = 0.7`
(비교 실험에서는 **한 번에 한 가지만** 바꿉니다. 시드를 고정해야 변화가 프롬프트/포즈 때문인지 우연 때문인지 구분됩니다.)

## 기준 프롬프트 (output_01)
```
a young woman standing in a sunlit library, wearing a beige trench coat,
natural light, 35mm photo, sharp focus, full body
```

## 실험 1 — 포즈 고정, 프롬프트만 변경
| 파일 | 프롬프트 | 관찰 |
|---|---|---|
| a1_astronaut.png | `an astronaut in a white spacesuit on a red desert planet, cinematic lighting, full body` | |
| a2_ink.png | `traditional korean ink painting of a scholar in hanbok, minimal background, full body` | |
| a3_3d.png | `cute 3d pixar style character, pastel colors, soft studio lighting, full body` | |

## 실험 2 — 프롬프트 고정, 포즈만 변경
| 파일 | 포즈 | 관찰 |
|---|---|---|
| output_01.png | pose_01 (정면 차렷) | |
| output_02.png | pose_02 (양팔 위로) | |

## 실험 3 — pose_strength 변경
| 파일 | 값 | 관찰 |
|---|---|---|
| strength_0.4.png | 0.4 | |
| strength_0.7.png | 0.7 | |
| strength_1.0.png | 1.0 | |

## 네거티브 프롬프트 (SDXL / SD1.5 등급에서만 사용)
```
lowres, bad anatomy, extra limbs, deformed hands, watermark, text
```

## 프롬프트를 쓸 때 지킨 원칙
- `full body` 를 넣습니다. 빼면 모델이 상반신만 그려 포즈가 잘립니다.
- 자세를 말로 다시 설명하지 않습니다(`raising arms` 같은 표현). 자세는 ControlNet이 맡고, 프롬프트는 **인물·의상·배경·화풍**만 담당하게 역할을 나눕니다.
- 화풍 단어(`35mm photo`, `ink painting`, `3d pixar style`)를 한 개만 넣습니다. 여러 개를 섞으면 서로 상쇄됩니다.
