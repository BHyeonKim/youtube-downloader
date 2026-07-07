# YouTube Downloader (Desktop GUI)

[PRD.md](PRD.md)에 따라 구현한 개인/학습용 유튜브 다운로더입니다.

> 개인적으로 저작권을 보유했거나, 저작권자가 다운로드를 허용했거나(CC 라이선스 등),
> 개인적 학습 목적의 사적 이용 범위 내에서만 사용하세요. 비공개/멤버십 전용 영상,
> DRM 우회 등은 지원 범위에서 제외됩니다.

## 실행 방법

### Windows: run.bat 더블클릭 (권장)

`youtube-downloader/run.bat` 파일을 더블클릭하면 가상환경 생성, 의존성 설치,
앱 실행을 한 번에 처리합니다. (venv가 없으면 새로 만들고, 있으면 그대로 사용)

### 수동 실행

```bash
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt
./.venv/Scripts/python -m app.main
```

> 주의: 시스템 Python(`python -m app.main`)으로 직접 실행하면 `PySide6`,
> `yt-dlp` 등이 설치되어 있지 않아 `ModuleNotFoundError`가 발생합니다.
> 반드시 위 가상환경(`.venv`)의 Python으로 실행하거나 `run.bat`을 사용하세요.

## 사용법

1. 상단 입력창에 유튜브 영상 / 재생목록 / 채널 URL을 붙여넣고 "조회" 클릭
2. 결과 테이블에서 다운로드할 항목 체크 (기본 전체 선택)
3. 포맷(mp4/mp3), 화질, 동시 다운로드 개수, 저장 경로 지정
4. "다운로드 시작" 클릭 → 하단 큐 테이블에서 진행률 확인
5. "이력" 탭에서 완료된 다운로드 목록 확인, 행 더블클릭 시 저장 폴더 열기

## 프로젝트 구조

```
app/
  models.py         # VideoInfo, QueueItem, 상태/enum 정의
  downloader.py      # yt-dlp 래퍼 (URL 판별, 메타데이터 조회, 다운로드)
  history.py          # JSON 기반 다운로드 이력 저장소
  gui/
    workers.py         # QThreadPool 기반 조회/다운로드 백그라운드 작업
    main_window.py    # 메인 윈도우 (PySide6)
  main.py              # 진입점
tests/
  test_models.py
  test_downloader.py            # yt-dlp를 모킹한 단위 테스트
  test_history.py
  smoke_gui.py                       # 헤드리스(offscreen) GUI 스모크 테스트
  integration_real_download.py  # 실제 네트워크로 검증하는 통합 테스트(수동 실행)
```

## 테스트

```bash
# 단위 테스트 (네트워크 불필요, mock 사용)
./.venv/Scripts/python -m pytest tests/

# GUI 헤드리스 스모크 테스트
QT_QPA_PLATFORM=offscreen ./.venv/Scripts/python tests/smoke_gui.py

# 실제 네트워크로 다운로드 파이프라인 검증 (약 20초 분량 공개 테스트 영상 사용)
./.venv/Scripts/python tests/integration_real_download.py
```

모두 통과 확인됨 (단위 테스트 33개, GUI 스모크 7단계, 실제 다운로드 통합 검증 4단계).

## 참고

- 다운로드 엔진: [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- ffmpeg: `imageio-ffmpeg` 패키지로 번들 제공 (별도 설치 불필요)
- 다운로드 이력 파일 위치: `~/.youtube_downloader/history.json`
- 기본 저장 경로: `~/Downloads/YouTubeDownloader`
